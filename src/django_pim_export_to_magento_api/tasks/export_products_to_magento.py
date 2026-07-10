# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
from decimal import Decimal

from celery import shared_task
from celery_once import QueueOnce
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Exists, OuterRef
from django_pim.models import Feature, FeatureTypeEnum, Product, ProductAttribute, ProductClassEnum
from django_pim.settings import SYSTEM_FEATURE_NAME_IDX, SYSTEM_FEATURE_URL_KEY_IDX
from django_pricemanager.models import Price as PricePM
from django_pricemanager.output import get_price_qs_by_latest_pricelist
from magento2_sdk2.dto.product import CustomAttribute, ProductExtensionAttributes, ProductType, ProductVisibility
from magento2_sdk2.dto.product import Product as ProductDTO
from magento2_sdk2.services.product import Product as MagentoProduct
from process_logger import ProcessLogger
from tqdm import tqdm

from django_pim_export_to_magento_api.exporter import MagentoExporter
from django_pim_export_to_magento_api.models import Channel, MagentoStore
from django_pim_export_to_magento_api.models.export_in_magento import (
    ExportInMagento,
    ExportType,
    Status,
    create_export_in_magento,
)
from django_pim_export_to_magento_api.settings import PRODUCT_DEFAULT_PRICE
from django_pim_export_to_magento_api.utils import generate_url_key


class ExportProductsToMagento(MagentoExporter):
    product_class: str | None = None

    products_names_cache: dict[str, str] = {}
    products_attributes_cache = {}
    products_prices_cache: dict[str, Decimal] = {}
    failed_export_products_cache: list[str] = []

    products_websites_full_cache: dict[str, list[int]] = {}

    def __init__(self, *args, **kwargs):
        self.product_class = kwargs.pop("product_class", None)
        super().__init__(*args, **kwargs)

    def _map_product_class(self):
        match self.product_class:
            case "simple":
                return ProductClassEnum.ProductSimple
            case "config":
                return ProductClassEnum.ProductConfigurable
            case "bundle":
                return ProductClassEnum.ProductBundle
            case "custom":
                return ProductClassEnum.ProductCustom
            case _:
                return None

    def _cache_failures(self, store: MagentoStore):
        failed_export = ExportInMagento.objects.filter(
            store=store,
            export_type=ExportType.PRODUCT,
            content_exported=ContentType.objects.get_for_model(Product),
            export_status=Status.FAILED,
        )

        for fe in failed_export:
            self.failed_export_products_cache.append(fe.object_id)

    def _cache_products_attributes(self, feature: Feature, store: MagentoStore):
        print(f"Cache Product {feature.idx}")
        self.logger.add_log_param("feature_idx", feature.idx)
        product_query = {"product__real_product__sku": self.product_id} if self.product_id else {}
        product_attributes = ProductAttribute.objects.filter(
            feature=feature, product__shop__idx=store.channel.idx, **product_query
        ).prefetch_related("product__real_product", "attribute")
        language = store.language.iso2
        all_skus = []
        all_sku_url_keys = []
        for pa in product_attributes:
            sku = pa.product.real_product.sku
            all_skus.append(sku)
            self.logger.add_log_param("sku", sku)
            if feature.idx == SYSTEM_FEATURE_URL_KEY_IDX and pa:
                all_sku_url_keys.append(sku)

            if feature.idx == SYSTEM_FEATURE_NAME_IDX:
                # Nazwa nie jest atrybutem w magento wiec leci normalnie
                name = pa.value_txt_t9n[language] if language in pa.value_txt_t9n else None
                if not name:
                    name = (
                        pa.value_txt_t9n[settings.T9N_DEFAULT_LANG]
                        if settings.T9N_DEFAULT_LANG in pa.value_txt_t9n
                        else None
                    )
                self.products_names_cache[sku] = name

            if (
                feature.idx == SYSTEM_FEATURE_URL_KEY_IDX
                and pa.product.pk in self.failed_export_products_cache
                and feature.feature_type == FeatureTypeEnum.VARCHAR255_T9N
                and (
                    not pa.value_txt_t9n
                    or (
                        (language in pa.value_txt_t9n and pa.value_txt_t9n[language] is None)
                        or language not in pa.value_txt_t9n
                    )
                )
            ):
                # Jeśli nie istnieje URL_KEY a próbowaliśmy wysłać do magento i był fail, to teraz próbujemy z wygenerowanym URL_KEY
                if sku not in self.products_attributes_cache:
                    self.products_attributes_cache[sku] = []

                name = self.products_names_cache[sku] if sku in self.products_names_cache else None
                if name:
                    url_key = generate_url_key(name, sku, append_idx=True)
                    ca = CustomAttribute(attribute_code=feature.idx, value=url_key)
                    self.products_attributes_cache[sku].append(ca)
                    self.logger.debug(f"Generated url_key {url_key} for {sku} to export into Magento2")
                else:
                    self.logger.warning(f"Product {sku} has no name. Can't generate url_key.")
            else:
                value = None
                match feature.feature_type:
                    case FeatureTypeEnum.BOOL:
                        value = "1" if pa.value_bool else "0"
                    case (
                        FeatureTypeEnum.DECIMAL
                        | FeatureTypeEnum.TEMPERATURE
                        | FeatureTypeEnum.LENGTH
                        | FeatureTypeEnum.MASS
                    ):
                        value = str(pa.value_decimal).rstrip("0").rstrip(".")
                    case FeatureTypeEnum.VARCHAR255 | FeatureTypeEnum.TEXT:
                        value = pa.value_txt
                    case FeatureTypeEnum.VARCHAR255_T9N | FeatureTypeEnum.TEXT_T9N:
                        value = (
                            pa.value_txt_t9n[language] if pa.value_txt_t9n and language in pa.value_txt_t9n else None
                        )
                    case FeatureTypeEnum.SELECT:
                        value = str(pa.attribute.magento_pk)
                    case FeatureTypeEnum.MULTISELECT:
                        value = str(pa.attribute.magento_pk)
                    case FeatureTypeEnum.DATETIME:
                        value = pa.value_datetime.isoformat(sep=" ")
                    case FeatureTypeEnum.JSON | FeatureTypeEnum.JSON_T9N:
                        try:
                            value = json.dumps(pa.value_json) if pa.value_json else None
                        except Exception as e:
                            self.logger.exception(e)
                            continue
                    case _:
                        self.logger.warning(f"Feature {feature.idx} has unknown type.")
                        continue

                if value is None:
                    self.logger.debug(f"Value {feature.idx} for {sku} is None.")
                    continue

                if sku not in self.products_attributes_cache:
                    self.products_attributes_cache[sku] = []

                if feature.feature_type != FeatureTypeEnum.MULTISELECT:
                    ca = CustomAttribute(attribute_code=feature.idx, value=value)
                    self.products_attributes_cache[sku].append(ca)
                else:
                    # Multiselect jest przekazywany po przecinku więc trzeba taki fikołek zrobić
                    exists = False
                    for ca in self.products_attributes_cache[sku]:
                        if ca.attribute_code == feature.idx:
                            exists = True
                            ca.value += f",{value}"
                            break
                    if not exists:
                        ca = CustomAttribute(attribute_code=feature.idx, value=value)
                        self.products_attributes_cache[sku].append(ca)

        for sku_missing_url_key in set(all_skus) - set(all_sku_url_keys):
            name = (
                self.products_names_cache[sku_missing_url_key]
                if sku_missing_url_key in self.products_names_cache
                else None
            )
            ca = CustomAttribute(
                attribute_code=SYSTEM_FEATURE_URL_KEY_IDX,
                value=generate_url_key(name, sku_missing_url_key, append_idx=True),
            )
            self.products_attributes_cache[sku_missing_url_key].append(ca)

        self.logger.delete_few_log_param(["sku", "feature_idx"])

    def _cache_all_product_websites(self):
        """
        Buduje cache wszystkich website_ids dla każdego produktu ze WSZYSTKICH kanałów.

        Produkty przypisane do danego channela/sklepu otrzymują wszystkie websity z tego channela.
        """
        print("Budowanie cache wszystkich websites dla produktów...")

        channels = Channel.objects.all().prefetch_related("magento_stores")

        product_query = {"real_product__sku": self.product_id} if self.product_id else {}
        class_query = {"product_class": self._map_product_class()} if self.product_class else {}

        for channel in channels:
            stores = channel.magento_stores.all()

            products = Product.objects.filter(shop__idx=channel.idx, **product_query, **class_query).select_related(
                "real_product"
            )

            for product in products:
                sku = product.real_product.sku

                if sku not in self.products_websites_full_cache:
                    self.products_websites_full_cache[sku] = []

                for store in stores:
                    if store.magento_pk and store.magento_pk not in self.products_websites_full_cache[sku]:
                        self.products_websites_full_cache[sku].append(store.magento_pk)

        for sku in self.products_websites_full_cache:
            self.products_websites_full_cache[sku] = sorted(self.products_websites_full_cache[sku])

        print(f"Cache zbudowany dla {len(self.products_websites_full_cache)} produktów")
        self.logger.info(f"Zbudowano cache websites dla {len(self.products_websites_full_cache)} produktów")

    def _cache_data(self, store: MagentoStore):
        features = store.channel.product_create_features.all()

        # Sortowanie features aby SYSTEM_FEATURE_NAME_IDX był przed SYSTEM_FEATURE_URL_KEY_IDX
        def sort_features_key(feature):
            if feature.idx == SYSTEM_FEATURE_NAME_IDX:
                return 0  # Najwyższy priorytet
            elif feature.idx == SYSTEM_FEATURE_URL_KEY_IDX:
                return 1  # Drugi priorytet
            else:
                return 2  # Pozostałe features

        features = sorted(features, key=sort_features_key)
        for feature in features:
            if feature.idx == SYSTEM_FEATURE_URL_KEY_IDX:
                self._cache_failures(store)
            self._cache_products_attributes(feature, store)

        print("Cache Product Prices")
        skus = [self.product_id] if self.product_id else []
        prices = get_price_qs_by_latest_pricelist(
            store.channel.idx, currency=store.currency.iso3, country=store.country.iso2, skus=skus
        ).prefetch_related("product")
        for price in prices:
            price: PricePM
            price_gross = (
                price.special_gross_value
                if price.is_egible_for_special_price and price.special_gross_value
                else price.gross_value
            )
            if price_gross:
                self.products_prices_cache[price.product.sku] = round(Decimal(price_gross), 2)

    def _get_query_to_process(self, store):
        product_query = {"real_product__sku": self.product_id} if self.product_id else {}
        success_export = ExportInMagento.objects.filter(
            store=store,
            export_type=ExportType.PRODUCT,
            content_exported=ContentType.objects.get_for_model(Product),
            export_status__in=[Status.SUCCESS, Status.SKIP],
            object_id=OuterRef("pk"),
        )

        class_query = {"product_class": self._map_product_class()} if self.product_class else {}

        pp = (
            Product.objects.filter(shop__idx=store.channel.idx, **product_query, **class_query)
            .exclude(Exists(success_export))
            .prefetch_related("real_product", "feature_set")
            .order_by("id")
        )
        return pp

    def map_product_type(self, product: Product) -> str:
        match product.product_class:
            case ProductClassEnum.ProductSimple:
                return ProductType.SIMPLE
            case ProductClassEnum.ProductConfigurable:
                return ProductType.CONFIGURABLE
            case ProductClassEnum.ProductBundle:
                return ProductType.BUNDLE
            case ProductClassEnum.ProductCustom:
                return ProductType.SIMPLE
            case _:
                return ProductType.SIMPLE

    def product_websites(self, product: Product, store: MagentoStore):
        """
        Zwraca PEŁNĄ listę wszystkich website_ids dla produktu ze WSZYSTKICH kanałów.

        Args:
            product: Produkt do eksportu
            store: Obecny store

        Returns:
            list[int]: Pełna lista wszystkich website_ids dla produktu
        """
        sku = product.real_product.sku

        if sku in self.products_websites_full_cache:
            return self.products_websites_full_cache[sku]
        else:
            self.logger.warning(f"SKU {sku} nie znaleziony w cache websites, używam tylko obecnego store")
            return [store.magento_pk] if store.magento_pk else []

    @create_export_in_magento(ExportType.PRODUCT, lambda self, product, store: (product, store))
    def process_object(self, product: Product, store: MagentoStore):
        sku = product.real_product.sku
        self.logger.add_log_param("sku", sku)

        name = self.products_names_cache.get(sku, None)
        self.logger.add_log_param("name", name)

        extension_attributes = {ProductExtensionAttributes.WEBSITE_IDS: self.product_websites(product, store)}

        p = ProductDTO(
            locale="",
            id=0,
            sku=product.real_product.sku,
            name=self.products_names_cache[sku] if sku in self.products_names_cache else sku,
            attribute_set_id=product.feature_set.magento_pk,
            status=1 if product.is_enabled else 0,
            visibility=ProductVisibility.CATALOG_AND_SEARCH,
            type_id=self.map_product_type(product),
            extension_attributes=extension_attributes,
            custom_attributes=self.products_attributes_cache[sku] if sku in self.products_attributes_cache else [],
            price=(
                self.products_prices_cache[sku] if sku in self.products_prices_cache else Decimal(PRODUCT_DEFAULT_PRICE)
            ),
            created_at=product.db_created.strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=product.db_modified.strftime("%Y-%m-%d %H:%M:%S"),
            weight=int(product.real_product.weight) if product.real_product.weight else 0,
        )

        if store.default:
            result, result_data = self.magento_sdk_class.save_product(product=p)
        else:
            result, result_data = self.magento_sdk_class.save_product(product=p, store_view=store.store_view_code)

        if result:
            self.logger.info(f"Product {sku} saved into Magento")
            return Status.SUCCESS
        else:
            self.logger.add_log_param("api_result", result_data)
            self.logger.error(f"Product {sku} not saved into Magento")
            return Status.FAILED

    def process_list_objects(self, store, obj_list):
        product_lists: list[list[Product]] = list(self.batch_iterate_query(obj_list))
        for product_list in tqdm(product_lists, desc=f"Processing {self.data_name}"):
            for product in product_list:
                try:
                    self.process_object(product, store)
                except Exception as e:
                    self.logger.exception(e)
                finally:
                    self.logger.delete_few_log_param(["sku", "name", "api_result"])

    def start(self):
        self.magento_sdk_class: MagentoProduct = MagentoProduct(self.client)

        # Zbuduj cache WSZYSTKICH websites dla WSZYSTKICH produktów przed rozpoczęciem eksportu
        # To gwarantuje, że każde wywołanie do Magento zawiera pełną listę websites,
        # niezależnie od tego czy eksportujemy jeden kanał czy wszystkie
        self._cache_all_product_websites()
        super().start()


@shared_task(base=QueueOnce, queue="pim_push")
def export_products_to_magento(
    runned_at: str,
    channel_idx: str | None = None,
    product_id: str | None = None,
    bulk: bool = True,
    product_class: str | None = None,
):
    logger = ProcessLogger("EXPORT_PRODUCTS_TO_MAGENTO", module="django_pim_export_to_magento_api")

    product_pictures_exporter = ExportProductsToMagento(
        channel_idx, runned_at, product_id, bulk, product_class=product_class
    )
    product_pictures_exporter.set_logger(logger)
    product_pictures_exporter.set_magento_sdk_class(MagentoProduct)
    product_pictures_exporter.start()
