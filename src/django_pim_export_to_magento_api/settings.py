# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.conf import settings

MAGENTO2_EXPORT_API_URL = getattr(settings, "MAGENTO2_EXPORT_API_URL", None)
MAGENTO2_EXPORT_API_TOKEN = getattr(settings, "MAGENTO2_EXPORT_API_TOKEN", None)

PICTURE_ROLE_TO_MAGENTO_TYPE_DEFAULT = {
    "unknown": [],
    "main": ["image", "small_image", "thumbnail"],
    "general": ["image"],
    "variant": ["image"],
    "angle": ["image"],
}
PICTURE_ROLE_TO_MAGENTO_TYPE = getattr(settings, "PICTURE_ROLE_TO_MAGENTO_TYPE", PICTURE_ROLE_TO_MAGENTO_TYPE_DEFAULT)

# You can ovveride some pictures position by type
PICTURE_POSITION_TO_MAGENTO_DEFAULT = {"unknown": None, "main": None, "general": None, "variant": None, "angle": None}
PICTURE_POSITION_TO_MAGENTO = getattr(settings, "PICTURE_POSITION_TO_MAGENTO", PICTURE_POSITION_TO_MAGENTO_DEFAULT)

# Only the main image will be sent with all languages, the rest will be sent only with this language
# because magento can't handle images per storeview (accepts language iso2 ex: pl)
PICTURES_ONLY_LANGUAGE = getattr(settings, "PICTURES_ONLY_LANGUAGE", None)

PRODUCT_DEFAULT_PRICE = getattr(settings, "PRODUCT_DEFAULT_PRICE", 99999)
