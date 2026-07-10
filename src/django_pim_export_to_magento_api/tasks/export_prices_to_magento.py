# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from celery import shared_task
from celery_once import QueueOnce
from django_pim.models import Product, ProductClassEnum
from django_pricemanager.models import Price as PricePM
from django_pricemanager.output import get_price_qs_by_latest_pricelist
from magento2_sdk2.dto.price import SpecialPrice as SpecialPriceDTO
from magento2_sdk2.dto.product import ProductPrice as ProductPriceDTO
from magento2_sdk2.services.product import Product as MagentoProduct
from process_logger import ProcessLogger
from tqdm import tqdm

from django_pim_export_to_magento_api.exporter import MagentoExporter
from django_pim_export_to_magento_api.models import MagentoStore


class ExportPricesToMagento(MagentoExporter):
    product_class: str | None = None

    products_class_cache: list[str] = []

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

    def _cache_data(self, store: MagentoStore):
        print("Cache Product Class")
        product_query = {"real_product__sku": self.product_id} if self.product_id else {}
        class_query = {"product_class": self._map_product_class()} if self.product_class else {}

        self.products_class_cache = list(
            Product.objects.filter(shop__idx=store.channel.idx, **product_query, **class_query)
            .prefetch_related("real_product")
            .values_list("real_product__sku", flat=True)
        )

    def _get_query_to_process(self, store):
        skus = [self.product_id] if self.product_id else []
        prices = (
            get_price_qs_by_latest_pricelist(
                store.channel.idx, currency=store.currency.iso3, country=store.country.iso2, skus=skus
            )
            .prefetch_related("product")
            .order_by("id")
        )
        return prices

    def process_object(self, price: PricePM, store: MagentoStore):
        sku = price.product.sku
        self.logger.add_log_param("sku", sku)

        if self.product_class and sku not in self.products_class_cache:
            self.logger.debug(f"Product {sku} wrong class: {self.product_class}. Skipping")
            return

        p = ProductPriceDTO(sku=sku, price=price.gross_value)

        if store.default:
            result, result_data = self.magento_sdk_class.save_product_price(product=p)
        else:
            result, result_data = self.magento_sdk_class.save_product_price(product=p, store_view=store.store_view_code)

        if result:
            self.logger.info(f"Product {sku} Price saved into Magento")
        else:
            self.logger.add_log_param("api_result", result_data)
            self.logger.error(f"Product {sku} Price not saved into Magento")

        if price.special_gross_value:
            s = SpecialPriceDTO(
                sku=sku,
                store_id=store.magento_pk,
                price=price.special_gross_value,
                price_from=price.special_from_date.strftime("%Y-%m-%d %H:%M:%S") if price.special_from_date else None,
                price_to=price.special_to_date.strftime("%Y-%m-%d %H:%M:%S") if price.special_to_date else None,
                extension_attributes={},
            )

            if store.default:
                result, result_data = self.magento_sdk_class.save_special_price(special_price=s)
            else:
                result, result_data = self.magento_sdk_class.save_special_price(
                    special_price=s, store_view=store.store_view_code
                )

            if result:
                self.logger.info(f"Product {sku} Special Price saved into Magento")
            else:
                self.logger.add_log_param("api_result", result_data)
                self.logger.error(f"Product {sku} Special Price not saved into Magento")

    def process_list_objects(self, store, obj_list):
        price_lists: list[list[PricePM]] = self.batch_iterate_query(obj_list)
        for price_list in tqdm(price_lists, desc=f"Processing {self.data_name}"):
            for price in price_list:
                try:
                    self.process_object(price, store)
                except Exception as e:
                    self.logger.exception(e)
                finally:
                    self.logger.delete_few_log_param(["sku", "name", "api_result"])

    def start(self):
        self.magento_sdk_class: MagentoProduct = MagentoProduct(self.client)
        super().start()


@shared_task(base=QueueOnce, queue="pim_push")
def export_prices_to_magento(
    runned_at: str,
    channel_idx: str | None = None,
    product_id: str | None = None,
    bulk: bool = True,
    product_class: str | None = None,
):
    logger = ProcessLogger("EXPORT_PRICES_TO_MAGENTO", module="django_pim_export_to_magento_api")

    product_pictures_exporter = ExportPricesToMagento(
        channel_idx, runned_at, product_id, bulk, product_class=product_class
    )
    product_pictures_exporter.set_logger(logger)
    product_pictures_exporter.set_magento_sdk_class(MagentoProduct)
    product_pictures_exporter.start()
