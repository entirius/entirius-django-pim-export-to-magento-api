# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from functools import wraps

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import IntegerChoices
from django.utils.translation import gettext_lazy as _
from django_pim.models import Product


def create_export_in_magento(export_type, get_content_exported):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            content_exported, store = get_content_exported(self, *args, **kwargs)

            product = None
            if hasattr(content_exported, "product"):
                product = content_exported.product
            elif isinstance(content_exported, Product):
                product = content_exported

            form_sync_status, is_created = ExportInMagento.objects.get_or_create(
                store=store,
                content_exported=ContentType.objects.get_for_model(content_exported),
                object_id=content_exported.id,
                export_type=export_type,
                product=product,
                defaults={"export_status": Status.PENDING},
            )
            form_sync_status.save()

            self._current_export_status = form_sync_status

            try:
                result = func(self, *args, **kwargs)
                if result is None:
                    error_message = "Function returned None - setting status to FAILED"
                    if hasattr(self, "logger"):
                        self.logger.error(error_message)
                    result = Status.FAILED
                    if not form_sync_status.failed_message:
                        form_sync_status.failed_message = error_message
                elif result == Status.FAILED:
                    if not form_sync_status.failed_message:
                        form_sync_status.failed_message = (
                            "Process returned FAILED status without specific error message"
                        )
                elif result == Status.SUCCESS or result == Status.SKIP:
                    form_sync_status.failed_message = None

                form_sync_status.export_status = result
                form_sync_status.save()

                return result
            except Exception as e:
                if not form_sync_status.failed_message:
                    error_message = f"{type(e).__name__}: {str(e)}"
                    form_sync_status.failed_message = error_message

                form_sync_status.export_status = Status.FAILED
                form_sync_status.save()
                self.logger.exception(e)
                raise
            finally:
                if hasattr(self, "_current_export_status"):
                    delattr(self, "_current_export_status")

        return wrapper

    return decorator


class ExportType(IntegerChoices):
    PRODUCT_PICTURES = 0, _("product_pictures")
    PRODUCT = 1, _("product")


class Status(IntegerChoices):
    SUCCESS = 0, _("success")
    FAILED = 1, _("failed")
    PENDING = 2, _("pending")
    SKIP = 3, _("skip")


class ExportInMagento(models.Model):
    store = models.ForeignKey(
        "MagentoStore",
        related_name="exports_in_magento",
        verbose_name="store",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    export_status = models.IntegerField(choices=Status.choices)
    export_type = models.IntegerField(choices=ExportType.choices)
    content_exported = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    failed_message = models.TextField(null=True, blank=True, verbose_name="Failed Message")

    product = models.ForeignKey(
        "django_pim.Product",
        related_name="exports_in_magento",
        verbose_name="product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    objects = models.Manager()
