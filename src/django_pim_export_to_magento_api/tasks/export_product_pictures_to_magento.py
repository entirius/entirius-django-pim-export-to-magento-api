# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import base64

from celery import shared_task
from celery_once import QueueOnce
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Exists, OuterRef, Q
from django_pim.models import ProductAttribute
from django_pim.models.product_picture import PictureRoleApiLabel, ProductPicture
from django_pim.settings import SYSTEM_FEATURE_NAME_IDX
from magento2_sdk2.dto.media import Media, MediaContent
from magento2_sdk2.services.product import Product as MagentoProduct
from process_logger import ProcessLogger
from tqdm import tqdm

from django_pim_export_to_magento_api.exporter import MagentoExporter
from django_pim_export_to_magento_api.models import MagentoStore
from django_pim_export_to_magento_api.models.export_in_magento import (
    ExportInMagento,
    ExportType,
    Status,
    create_export_in_magento,
)
from django_pim_export_to_magento_api.settings import (
    PICTURE_POSITION_TO_MAGENTO,
    PICTURE_ROLE_TO_MAGENTO_TYPE,
    PICTURES_ONLY_LANGUAGE,
)


class ExportProductPicturesToMagento(MagentoExporter):
    products_names_cache: dict[str, str] = {}

    def __init__(self, *args, **kwargs):
        self.picture_roles = kwargs.pop("picture_roles", None)
        super().__init__(*args, **kwargs)

    def _cache_data(self, store: MagentoStore):
        print("Cache Product Names")
        language = store.language.iso2
        product_query = {"product__real_product__sku": self.product_id} if self.product_id else {}
        product_attributes = ProductAttribute.objects.filter(
            feature__idx=SYSTEM_FEATURE_NAME_IDX, product__shop__idx=store.channel.idx, **product_query
        ).prefetch_related("product__real_product")
        for pa in product_attributes:
            name = pa.value_txt_t9n[language] if language in pa.value_txt_t9n else None
            if not name:
                name = (
                    pa.value_txt_t9n[settings.T9N_DEFAULT_LANG]
                    if settings.T9N_DEFAULT_LANG in pa.value_txt_t9n
                    else None
                )
            self.products_names_cache[pa.product.real_product.sku] = name

    def _get_query_to_process(self, store: MagentoStore):
        product_query = {"product__real_product__sku": self.product_id} if self.product_id else {}
        picture_roles_id = [PictureRoleApiLabel.idFromText(each) for each in self.picture_roles]
        success_export = ExportInMagento.objects.filter(
            store=store,
            export_type=ExportType.PRODUCT_PICTURES,
            content_exported=ContentType.objects.get_for_model(ProductPicture),
            export_status__in=[Status.SUCCESS, Status.SKIP],
            object_id=OuterRef("pk"),
        )

        # Warunek dla języka: albo języka brak (is None), albo jest taki sam jak w store
        language_condition = Q(language=store.language) | Q(language__isnull=True)
        pp = (
            ProductPicture.objects.filter(
                product__shop__idx=store.channel.idx, **product_query, picture_role__in=picture_roles_id
            )
            .filter(language_condition)
            .exclude(Exists(success_export))
            .prefetch_related("product__real_product", "picture")
            .order_by("id")
        )
        return pp

    @staticmethod
    def get_base64_encoded_image(file_path):
        return base64.b64encode(file_path.read()).decode("utf-8")

    @create_export_in_magento(ExportType.PRODUCT_PICTURES, lambda self, product_pic, store: (product_pic, store))
    def process_object(self, product_pic: ProductPicture, store: MagentoStore):
        try:
            sku = product_pic.product.real_product.sku
            self.logger.add_log_param("sku", sku)
            self.logger.add_log_param("product_picture_id", product_pic.id)
            self.logger.add_log_param("picture_id", product_pic.picture.id)
            self.logger.add_log_param("picture_sha", product_pic.picture.sha1)

            picture_role = PictureRoleApiLabel.label(product_pic.picture_role)
            self.logger.add_log_param("picture_role", picture_role)

            file_name = product_pic.picture.image.path.split("/")[-1]
            file_path = product_pic.picture.image.path

            self.logger.add_log_param("file_name", file_name)
            self.logger.add_log_param("file_path", file_path)

            file_size = product_pic.picture.image.file.size
            self.logger.add_log_param("file_size_bytes", file_size)
            self.logger.add_log_param("file_size_mb", round(file_size / (1024 * 1024), 2))

        except AttributeError as e:
            self.logger.exception(e)
            if hasattr(self, "_current_export_status"):
                self._current_export_status.failed_message = (
                    "Failed to access product/picture attributes (AttributeError)"
                )
            raise

        except Exception as e:
            self.logger.exception(e)
            if hasattr(self, "_current_export_status"):
                self._current_export_status.failed_message = "Failed to read image metadata"
            raise

        if file_name.endswith(".jpg"):
            type = "image/jpeg"
        elif file_name.endswith(".png"):
            type = "image/png"
        elif file_name.endswith(".jpeg"):
            type = "image/jpeg"
        elif file_name.endswith(".gif"):
            type = "image/gif"
        else:
            error_msg = f"Unsupported file type: {file_name}"
            self.logger.error(error_msg)
            if hasattr(self, "_current_export_status"):
                self._current_export_status.failed_message = error_msg
            raise NotImplementedError(f"File type {file_name} not supported")
        self.logger.add_log_param("type", type)

        # Only one language will be send, because magento can't handle images per storeview (language)
        if product_pic.language and product_pic.language.iso2 != PICTURES_ONLY_LANGUAGE:
            self.logger.debug("Picture is not main and will not be sent to magento in this language. Skipping.")
            return Status.SKIP

        # Wyciaganie z PICTURE_ROLE_TO_MAGENTO_TYPE musi miec list() albo .copy() aby nie pobrać referencji do tablicy
        magento_types = list(PICTURE_ROLE_TO_MAGENTO_TYPE.get(picture_role, []))
        if magento_types is None:
            error_msg = f"Picture role not supported: {picture_role}"
            self.logger.error(error_msg)
            if hasattr(self, "_current_export_status"):
                self._current_export_status.failed_message = error_msg
            raise NotImplementedError("Picture role not supported")

        if not magento_types:
            warning_msg = f"Empty magento_types list for picture_role: {picture_role}"
            self.logger.warning(warning_msg)

        self.logger.add_log_param("magento_types", magento_types)

        label = self.products_names_cache.get(sku, None)
        self.logger.add_log_param("label", label)

        position = PICTURE_POSITION_TO_MAGENTO.get(picture_role, None)
        if position is None:
            position = product_pic.position
        self.logger.add_log_param("position", position)

        try:
            with product_pic.picture.image.open("rb") as f:
                base64_data = self.get_base64_encoded_image(f)
        except Exception as e:
            self.logger.exception(e)
            if hasattr(self, "_current_export_status"):
                self._current_export_status.failed_message = f"Failed to encode image to base64: {str(e)}"
            raise

        media: Media = Media(
            file=file_name,
            media_type="image",
            types=magento_types,
            position=position,
            disabled=False,
            content=MediaContent(
                base64_encoded_data=base64_data,
                type=type,
                name=file_name,
            ),
            label=label,
        )

        try:
            result, mag_picture_id = self.magento_sdk_class.save_product_picture(sku=sku, media=media)
            self.logger.add_log_param("magento_save_result", result)
        except Exception as e:
            self.logger.exception(e)
            if hasattr(self, "_current_export_status"):
                self._current_export_status.failed_message = f"Failed to save picture to Magento: {str(e)}"
            raise

        self.logger.add_log_param("magento_picture_id", mag_picture_id)
        self.logger.info(f"Image {picture_role}:{product_pic.position} saved into Magento for product: {sku}")
        return Status.SUCCESS

    def process_list_objects(self, store: MagentoStore, obj_list):
        product_pic_lists: list[list[ProductPicture]] = self.batch_iterate_query(obj_list)
        for product_pic_list in tqdm(product_pic_lists, desc=f"Processing {self.data_name}"):
            for product_pic in product_pic_list:
                try:
                    self.process_object(product_pic, store)
                except Exception as e:
                    self.logger.exception(e)
                finally:
                    self.logger.delete_few_log_param(
                        [
                            "sku",
                            "product_picture_id",
                            "picture_id",
                            "picture_sha",
                            "picture_role",
                            "position",
                            "file_name",
                            "file_path",
                            "file_size_bytes",
                            "file_size_mb",
                            "type",
                            "magento_types",
                            "label",
                            "magento_save_result",
                            "magento_picture_id",
                        ]
                    )

    def start(self):
        self.magento_sdk_class: MagentoProduct = MagentoProduct(self.client)
        super().start()


@shared_task(base=QueueOnce, queue="pim_push")
def export_product_pictures_to_magento(
    runned_at: str,
    channel_idx: str | None = None,
    product_id: str | None = None,
    bulk: bool = True,
    picture_roles: list[str] | None = None,
):
    logger = ProcessLogger("EXPORT_PICTURES_TO_MAGENTO", module="django_pim_export_to_magento_api")

    product_pictures_exporter = ExportProductPicturesToMagento(
        channel_idx, runned_at, product_id, bulk, picture_roles=picture_roles
    )
    product_pictures_exporter.set_logger(logger)
    product_pictures_exporter.set_magento_sdk_class(MagentoProduct)
    product_pictures_exporter.start()
