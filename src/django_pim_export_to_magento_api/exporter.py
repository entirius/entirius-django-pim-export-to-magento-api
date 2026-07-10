# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from django.core.paginator import Paginator
from magento2_sdk2.services.client import Magento2Client
from process_logger import ProcessLogger, ProcessLoggerMixin

from django_pim_export_to_magento_api.models import Channel, MagentoStore
from django_pim_export_to_magento_api.settings import MAGENTO2_EXPORT_API_TOKEN, MAGENTO2_EXPORT_API_URL


class MagentoExporter(ProcessLoggerMixin):
    client: Magento2Client
    channel_idx: str | None
    runned_at: str
    channels: list[Channel]
    product_id: str | None
    magento_sdk_class: object | None
    is_bulk: int = False
    batch_size: int = 100
    data_name = "data"

    def __init__(
        self,
        channel_idx: str | None = None,
        runned_at: str = None,
        product_id: str | None = None,
        is_bulk: bool = True,
        *args,
        **kwargs,
    ):
        self.client = Magento2Client(MAGENTO2_EXPORT_API_URL, MAGENTO2_EXPORT_API_TOKEN)
        self.channel_idx = channel_idx
        self.runned_at = runned_at
        self.product_id = product_id
        self.is_bulk = is_bulk

    def set_logger(self, logger: ProcessLogger):
        self.logger = logger
        self.logger.add_log_param("channel_idx", self.channel_idx)
        self.logger.add_log_param("runned_at", self.runned_at)

    def _get_channels(self):
        if self.channel_idx:
            return Channel.objects.filter(idx=self.channel_idx)
        return Channel.objects.all()

    def set_magento_sdk_class(self, magento_sdk_class):
        self.magento_sdk_class = magento_sdk_class

    def _pre_init(self):
        self.channels = self._get_channels()
        match self.__class__.__name__:
            case "ExportProductPicturesToMagento":
                self.data_name = "Pictures"
            case "ExportProductsToMagento":
                self.data_name = "Products"
            case "ExportPricesToMagento":
                self.data_name = "Prices"
            case _:
                raise NotImplementedError

    def _cache_data(self, store: MagentoStore):
        raise NotImplementedError

    def _get_query_to_process(self, store: MagentoStore):
        raise NotImplementedError

    def process_list_objects(self, store: MagentoStore, obj_list):
        raise NotImplementedError

    def process_for_stores(self):
        for channel in self.channels:
            self.logger.add_log_param("channel_idx", channel.idx)
            stores = channel.magento_stores.all()
            for store in stores:
                self.logger.add_log_param("store_view", store.store_view_code)
                self.logger.add_log_param("locale", store.language.iso2)
                yield store

    def batch_iterate_query(self, query):
        if self.is_bulk:
            paginator = Paginator(query, self.batch_size)
            for page in paginator.page_range:
                yield paginator.page(page).object_list
        else:
            for obj in query:
                yield [obj]

    def start(self):
        self._pre_init()
        for store in self.process_for_stores():
            match self.__class__.__name__:
                case "ExportProductPicturesToMagento":
                    if store.pictures is False:
                        print(f"{self.data_name} export are disabled for this store {store.store_view_code}")
                        continue
                case "ExportProductsToMagento":
                    if store.products is False:
                        print(f"{self.data_name} export are disabled for this store {store.store_view_code}")
                        continue

                case "ExportPricesToMagento":
                    if store.prices is False:
                        print(f"{self.data_name} export are disabled for this store {store.store_view_code}")
                        continue
                case _:
                    raise NotImplementedError
            print(f"{self.data_name} export start for store {store.store_view_code}")
            self._cache_data(store)
            queryset_to_save = self._get_query_to_process(store)
            if not queryset_to_save.exists():
                print(f"No {self.data_name} to export")
            for obj_save_list in self.batch_iterate_query(queryset_to_save):
                self.process_list_objects(store, obj_save_list)
