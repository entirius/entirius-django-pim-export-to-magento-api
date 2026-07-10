# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.


from celery import shared_task
from celery_once import QueueOnce
from django_pim.models import Attribute, Feature
from magento2_sdk2.services.client import Magento2Client
from magento2_sdk2.services.product import Product as MagentoProduct
from process_logger import ProcessLogger
from tqdm import tqdm

from django_pim_export_to_magento_api.models import Channel
from django_pim_export_to_magento_api.settings import MAGENTO2_EXPORT_API_TOKEN, MAGENTO2_EXPORT_API_URL


@shared_task(base=QueueOnce, queue="pim_pull")
def import_magento_attributes(runned_at: str, channel_idx: str | None = None):
    logger = ProcessLogger("IMPORT_MAGENTO_ATTRIBUTES", module="django_pim_export_to_magento_api")
    logger.add_log_param("channel_idx", channel_idx)
    logger.add_log_param("runned_at", runned_at)

    if channel_idx:
        channels = Channel.objects.filter(idx=channel_idx)
    else:
        channels = Channel.objects.all()

    client = Magento2Client(MAGENTO2_EXPORT_API_URL, MAGENTO2_EXPORT_API_TOKEN)
    magento_service = MagentoProduct(client)

    for channel in channels:
        print(f"Channel {channel.idx}")
        stores = channel.magento_stores.all()
        for store in stores:
            store_view = store.store_view_code
            print(f"Storeview {store_view}")
            language = store.language.iso2
            logger.add_log_param("store_view", store_view)
            logger.add_log_param("locale", language)

            result = magento_service.get_attributes()
            if not result:
                return

            items = {}
            for item in result:
                items[item["attribute_code"]] = item

            features_query = Feature.objects.all()
            for feature in features_query:
                print(f"- Feature: {feature.idx}")
                logger.add_log_param("feature_idx", feature.idx)
                feature: Feature
                if feature.idx not in items:
                    print("  - Feature not found in magento attributes. Skipping.")
                    logger.warning(f"Feature {feature.idx} not found in magento attributes. Skipping.")
                    continue

                if "attribute_id" in items[feature.idx]:
                    feature.magento_pk = items[feature.idx]["attribute_id"]
                    feature.save()

                if "options" in items[feature.idx] and len(items[feature.idx]["options"]) > 0:
                    options = {}
                    for option in items[feature.idx]["options"]:
                        options[option["label"]] = option["value"]

                    attributes = Attribute.objects.filter(feature=feature)
                    for attribute in tqdm(attributes, desc=f"Processing attributes for feature: {feature.idx}"):
                        try:
                            attribute: Attribute
                            name = attribute.name_lang(language)
                            if name in options:
                                attribute.magento_pk = int(options[name])
                                attribute.save()
                        except Exception as e:
                            logger.exception(e)
                            continue
