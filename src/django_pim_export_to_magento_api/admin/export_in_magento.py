# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.contrib import admin
from django.contrib.admin import DateFieldListFilter
from django.urls import reverse
from django.utils.html import format_html

from django_pim_export_to_magento_api.models import ExportInMagento


@admin.register(ExportInMagento)
class ExportInMagentoAdmin(admin.ModelAdmin):
    list_display = (
        "store",
        "export_status",
        "export_type",
        "linked_content_exported",
        "linked_object_id",
        "created_at",
        "modified_at",
        "product",
    )
    list_filter = (
        "store",
        ("created_at", DateFieldListFilter),
        ("modified_at", DateFieldListFilter),
        "export_status",
        "export_type",
        "content_exported",
    )
    search_fields = ("object_id", "product__real_product__sku")
    autocomplete_fields = ("product",)

    def linked_content_exported(self, obj):
        app_label = obj.content_exported.app_label
        model_name = obj.content_exported.model
        url = reverse(f"admin:{app_label}_{model_name}_changelist")
        return format_html('<a href="{}">{}.{}</a>', url, app_label, model_name)

    linked_content_exported.short_description = "Content exported"
    linked_content_exported.admin_order_field = "content_exported"

    def linked_object_id(self, obj):
        app_label = obj.content_exported.app_label
        model_name = obj.content_exported.model
        url = reverse(f"admin:{app_label}_{model_name}_change", args=[obj.object_id])
        return format_html('<a href="{}">{}</a>', url, obj.object_id)

    linked_object_id.short_description = "Object ID"
    linked_object_id.admin_order_field = "object_id"
