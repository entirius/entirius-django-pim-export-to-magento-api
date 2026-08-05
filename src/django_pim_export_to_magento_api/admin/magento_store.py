# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django_utils.admin.base_admin import BaseModelAdmin as ModelAdmin

from django_pim_export_to_magento_api.models import MagentoStore


@admin.register(MagentoStore)
class MagentoStoreAdmin(ModelAdmin):
    list_display = (
        "channel",
        "store_view_code",
        "magento_pk",
        "default",
        "language",
        "currency",
        "country",
        "pictures",
        "products",
        "prices",
        "check_prices",
    )

    fieldsets = (
        (None, {"fields": ("channel", "store_view_code", "magento_pk", "default")}),
        ("Regional", {"fields": ("language", "currency", "country")}),
        ("What to export?", {"fields": ("pictures", "products", "prices", "check_prices")}),
    )
