# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from magento2_sdk2.services.client import Magento2Client
from magento2_sdk2.services.worker import post_product_in_category
from process_logger import ProcessLogger

from django_pim_export_to_magento_api.models import Channel, MagentoStore
from django_pim_export_to_magento_api.settings import MAGENTO2_EXPORT_API_TOKEN, MAGENTO2_EXPORT_API_URL

BULK_SIZE = 1000


## Used by ulep
def export_product_in_category_to_magento(
    runned_at: str,
    channel_idx: str | None = None,
    products_in_categories: list[dict] = None,
    logger: ProcessLogger = None,
):
    products_in_categories = products_in_categories or []
    if not logger:
        logger = ProcessLogger("EXPORT_PRODUCT_IN_CATEGORY_TO_MAGENTO", module="django_pim_export_to_magento_api")
    logger.add_log_param("channel_idx", channel_idx)
    logger.add_log_param("runned_at", runned_at)

    if channel_idx:
        channels = Channel.objects.filter(idx=channel_idx)
    else:
        channels = Channel.objects.all()

    if not MAGENTO2_EXPORT_API_URL or not MAGENTO2_EXPORT_API_TOKEN:
        logger.error("Brak ustawień dla API Magento.")
        return

    client = Magento2Client(MAGENTO2_EXPORT_API_URL, MAGENTO2_EXPORT_API_TOKEN)

    for channel in channels:
        logger.add_log_param("channel_idx", channel.idx)
        stores = channel.magento_stores.all()

        for store in stores:
            store: MagentoStore

            if not store.default:
                # For now skip all not default stores
                continue

            store_view = store.store_view_code
            language = store.language.iso2
            logger.add_log_param("store_view", store_view)
            logger.add_log_param("locale", language)

            for product_in_category in products_in_categories:
                try:
                    sku = product_in_category["sku"]
                    logger.add_log_param("sku", sku)
                    category_id = product_in_category["category_id"]
                    logger.add_log_param("category_magento_id", category_id)
                    position = product_in_category.get("position", 0)

                    if store.default:
                        post_product_in_category(client, category_id, sku, position)
                    else:
                        post_product_in_category(client, category_id, sku, position, store_view=store_view)
                    logger.info(f"Product {sku} in category {category_id} saved into Magento")
                except Exception as e:
                    logger.exception(e)
                    continue
