# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
from math import ceil

from celery import shared_task
from celery_once import QueueOnce
from django.db.models import Prefetch
from django_pim.models import Attribute, Feature, FeatureTypeEnum, Product, ProductAttribute
from magento2_sdk2.dto.product import CustomAttribute, ProductLite
from magento2_sdk2.services.attribute import Attribute as MagentoAttribute
from magento2_sdk2.services.client import Magento2Client
from magento2_sdk2.services.product import Product as MagentoProduct
from process_logger import ProcessLogger
from tqdm import tqdm

from django_pim_export_to_magento_api.models import Channel, MagentoStore
from django_pim_export_to_magento_api.settings import MAGENTO2_EXPORT_API_TOKEN, MAGENTO2_EXPORT_API_URL

BULK_SIZE = 1000


@shared_task(base=QueueOnce, queue="pim_push")
def export_attributes_to_magento(
    runned_at: str, channel_idx: str | None = None, product_id: str | None = None, bulk: bool = True
):
    logger = ProcessLogger("EXPORT_ATTRIBUTES_TO_MAGENTO", module="django_pim_export_to_magento_api")
    logger.add_log_param("channel_idx", channel_idx)
    logger.add_log_param("runned_at", runned_at)

    if channel_idx:
        channels = Channel.objects.filter(idx=channel_idx)
    else:
        channels = Channel.objects.all()

    product_query = {"real_product__sku": product_id} if product_id else {}

    if not MAGENTO2_EXPORT_API_URL or not MAGENTO2_EXPORT_API_TOKEN:
        logger.error("Brak ustawień dla API Magento.")
        return

    client = Magento2Client(MAGENTO2_EXPORT_API_URL, MAGENTO2_EXPORT_API_TOKEN)
    magento_product_service = MagentoProduct(client)
    magento_attribute_service = MagentoAttribute(client)

    for channel in channels:
        logger.add_log_param("channel_idx", channel.idx)
        stores = channel.magento_stores.all()
        features = channel.features.all()

        _ensure_features_exist_in_magento(features, magento_attribute_service, logger, channel)

        products = (
            Product.objects.filter(shop__idx=channel.idx, **product_query)
            .select_related("real_product")
            .prefetch_related(
                Prefetch(
                    "products_attributes",
                    queryset=ProductAttribute.objects.filter(feature__in=features).select_related(
                        "feature", "attribute"
                    ),
                )
            )
        )

        for store in stores:
            store_view = store.store_view_code
            language = store.language.iso2
            logger.add_log_param("store_view", store_view)
            logger.add_log_param("locale", language)

            products_to_update = {}
            for pr in tqdm(
                products, desc=f"Przetwarzanie atrybutów produktów dla kanału {channel.idx}", total=products.count()
            ):
                sku = pr.real_product.sku
                # .all() zwróci tylko to co jest odfiltrowane powyzej z metody Prefetch
                for pa in pr.products_attributes.all():
                    try:
                        pa: ProductAttribute
                        feature: Feature = pa.feature
                        logger.add_log_param("sku", sku)
                        logger.add_log_param("feature", feature.idx)

                        if not feature.magento_pk:
                            logger.warning(f"Feature {feature.idx} nie ma przypisanego magento_pk. Pomijam.")
                            continue

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
                                    pa.value_txt_t9n[language]
                                    if pa.value_txt_t9n and language in pa.value_txt_t9n
                                    else None
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
                                    logger.exception(e)
                                    continue
                            case _:
                                logger.warning(f"Feature {feature.idx} has unknown type.")
                                continue

                        if value is None:
                            logger.warning(f"Value {feature.idx} for {sku} is None.")
                            continue

                        if sku not in products_to_update:
                            product_status = 1 if pa.product.is_enabled else 0
                            products_to_update[sku]: ProductLite = ProductLite(
                                sku=sku, custom_attributes=[], status=product_status
                            )

                        if feature.feature_type != FeatureTypeEnum.MULTISELECT:
                            ca = CustomAttribute(attribute_code=feature.idx, value=value)
                            products_to_update[sku].custom_attributes.append(ca)
                        else:
                            # Multiselect jest przekazywany po przecinku więc trzeba taki fikołek zrobić
                            exists = False
                            for ca in products_to_update[sku].custom_attributes:
                                if ca.attribute_code == feature.idx:
                                    exists = True
                                    ca.value += f",{value}"
                                    break
                            if not exists:
                                ca = CustomAttribute(attribute_code=feature.idx, value=value)
                                products_to_update[sku].custom_attributes.append(ca)

                        logger.info(f"Added feature {feature.idx} for {sku} to update list.")
                    except Exception as e:
                        logger.exception(e)

                    logger.delete_few_log_param(["sku", "feature"])

                if sku not in products_to_update:
                    product_status = 1 if pr.is_enabled else 0
                    products_to_update[sku] = ProductLite(sku=sku, custom_attributes=[], status=product_status)

            if bulk:
                _bulk_save_products(products_to_update, magento_product_service, store, logger)
            else:
                _save_products_individually(products_to_update, magento_product_service, store, logger)


def _ensure_features_exist_in_magento(features, magento_attribute_service, logger, channel: Channel):
    """
    Sprawdza czy atrybuty istnieją w Magento, a jeśli nie - tworzy je.
    Zwraca słownik z atrybutami które wymagają aktualizacji w bazie danych.
    """
    features_to_update = {}

    try:
        existing_attributes = magento_attribute_service.get_attributes()

        logger.info(f"Pobrano {len(existing_attributes) if existing_attributes else 0} atrybutów z Magento")

        if not existing_attributes:
            logger.error("Nie udało się pobrać listy atrybutów z Magento.")
            return features_to_update

        existing_attr_by_id = {attr["attribute_id"]: attr for attr in existing_attributes}

        for feature in tqdm(features, desc="Sprawdzanie atrybutów"):
            if feature.magento_pk:
                if str(feature.magento_pk) in existing_attr_by_id or feature.magento_pk in existing_attr_by_id:
                    if feature.feature_type in [FeatureTypeEnum.SELECT, FeatureTypeEnum.MULTISELECT]:
                        _sync_attribute_options(feature, magento_attribute_service, logger, channel)
                continue

            logger.add_log_param_once("feature_idx", feature.idx)
            logger.warning(f"Atrybut {feature.idx} nie istnieje w Magento i nie zostanie utworzony.")
    except Exception as e:
        logger.exception(e)

    return features_to_update


def _sync_attribute_options(feature, magento_attribute_service, logger, channel: Channel):
    """
    Synchronizuje opcje dla atrybutów typu dropdown/multiselect.

    Args:
        feature: Atrybut PIM, którego opcje mają być synchronizowane
        magento_attribute_service: Serwis do komunikacji z API Magento
        logger: Logger do zapisywania informacji
        channel: Opcjonalny kanał, z którego pobierane jest ustawienie create_option_in_magento
    """

    logger.add_log_param("feature_idx", feature.idx)
    logger.info(f"Synchronizacja opcji dla atrybutu {feature.idx} (magento_pk: {feature.magento_pk})")
    create_options = channel.create_option_in_magento

    try:
        success, attribute_details = magento_attribute_service.get_attribute(feature.magento_pk)
        if not success:
            logger.error(f"Nie udało się pobrać szczegółów atrybutu {feature.idx} z Magento")
            return

        attribute_code = attribute_details.get("attribute_code")
        if not attribute_code:
            logger.error(f"Nie znaleziono kodu atrybutu dla {feature.idx}")
            return

        existing_options = {}
        if "options" in attribute_details:
            for option in attribute_details["options"]:
                if "label" in option and "value" in option:
                    existing_options[option["label"]] = option["value"]

        pim_options = []
        for attribute in feature.attributes.all():
            pim_options.append({"label": attribute.name, "idx": attribute.idx, "magento_pk": attribute.magento_pk})

        for option in pim_options:
            logger.add_log_param("attribute_idx", option["idx"])
            if option["label"] not in existing_options and create_options:
                option_data = {"option": {"label": option["label"], "sort_order": 0}}
                success, response = magento_attribute_service.add_attribute_options(attribute_code, option_data)
                if success:
                    logger.info(f"Pomyślnie dodano opcję '{option['label']}' do atrybutu {feature.idx}")

                    if isinstance(response, str) and response.isdigit():
                        Attribute.objects.filter(idx=option["idx"]).update(magento_pk=response)
                        logger.info(f"Zaktualizowano magento_pk dla opcji {option['label']}: {response}")
                else:
                    error_message = (
                        response.get("message", "Nieznany błąd") if isinstance(response, dict) else str(response)
                    )
                    logger.error(
                        f"Nie udało się dodać opcji '{option['label']}' do atrybutu {feature.idx}. Błąd: {error_message}"
                    )
            elif option["label"] in existing_options and not option["magento_pk"]:
                magento_value = existing_options[option["label"]]
                Attribute.objects.filter(idx=option["idx"]).update(magento_pk=magento_value)
                logger.info(f"Zaktualizowano magento_pk dla opcji {option['label']}: {magento_value}")
            elif not option["magento_pk"] and not create_options:
                logger.warning(
                    f"Opcja '{option['label']}' nie istnieje w Magento i nie zostanie utworzona (create_option_in_magento = False)"
                )
            logger.delete_log_param("attribute_idx")

        if create_options:
            success, updated_attr = magento_attribute_service.get_attribute(feature.magento_pk)
            if success and "options" in updated_attr:
                updated_options = {
                    opt["label"]: opt["value"] for opt in updated_attr["options"] if "label" in opt and "value" in opt
                }
                for option in pim_options:
                    logger.add_log_param("attribute_idx", option["idx"])
                    if option["label"] in updated_options and not option["magento_pk"]:
                        magento_value = updated_options[option["label"]]
                        Attribute.objects.filter(idx=option["idx"]).update(magento_pk=magento_value)
                        logger.info(f"Zaktualizowano magento_pk dla opcji {option['label']}: {magento_value}")
                    logger.delete_log_param("attribute_idx")

    except Exception as e:
        logger.exception(e)
    finally:
        logger.delete_log_param("feature_idx")


def _bulk_save_products(products_to_update, magento_product_service, store: MagentoStore, logger):
    """Zapisuje atrybuty produktów w trybie bulk."""
    print("Zapisuje atrybuty produktów w trybie bulk.")
    try:
        products_list = list(products_to_update.values())
        total_batches = ceil(len(products_list) / BULK_SIZE)

        for i in range(total_batches):
            start_idx = i * BULK_SIZE
            end_idx = min((i + 1) * BULK_SIZE, len(products_list))
            batch = products_list[start_idx:end_idx]

            if store.default:
                validation, response = magento_product_service.save_products_attributes(batch)
            else:
                validation, response = magento_product_service.save_products_attributes(batch, store.store_view_code)
            if validation:
                if "bulk_uuid" in response:
                    logger.add_log_param("bulk_uuid", response["bulk_uuid"])
                logger.info(f"Zaktualizowano atrybuty produktów w Magento, {len(batch)} produktów).")
            else:
                logger.add_log_param("response", response)
                logger.error(f"Błąd podczas aktualizacji atrybutów produktów w Magento (batch {i + 1}).")
    except Exception as e:
        logger.exception(e)


def _save_products_individually(products_to_update, magento_product_service, store: MagentoStore, logger):
    """Zapisuje atrybuty produktów indywidualnie."""
    print("Zapisuje atrybuty produktów indywidualnie.")
    for sku, p in products_to_update.items():
        logger.add_log_param("sku", sku)
        try:
            if store.default:
                validation, response = magento_product_service.save_product_attributes(p)
            else:
                validation, response = magento_product_service.save_product_attributes(p, store.store_view_code)
            if validation:
                logger.info(f"Zaktualizowano atrybuty produktu o SKU: {sku}")
            else:
                logger.add_log_param("response", response)
                logger.error(f"Błąd podczas aktualizacji atrybutów produktu o SKU: {sku}")
        except Exception as e:
            logger.exception(e)
        finally:
            logger.delete_log_param("sku")
