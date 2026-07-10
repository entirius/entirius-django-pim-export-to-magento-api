# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django_regional.models import Country, Currency, Language

    from django_pim_export_to_magento_api.models import Channel


class MagentoStore(models.Model):
    channel: "Channel" = models.ForeignKey("Channel", on_delete=models.CASCADE, related_name="magento_stores")
    store_view_code = models.CharField(max_length=256, blank=True, null=True)
    magento_pk = models.PositiveIntegerField(blank=True, null=True, help_text="website_id from magento")
    default = models.BooleanField(default=False, help_text="Default storeview for whole magento")
    language: "Language" = models.ForeignKey("django_regional.Language", on_delete=models.CASCADE)
    currency: "Currency" = models.ForeignKey("django_regional.Currency", on_delete=models.CASCADE)
    country: "Country" = models.ForeignKey("django_regional.Country", on_delete=models.CASCADE)
    pictures = models.BooleanField(
        default=False, help_text="Choose only one per channel, because magento can't handle pictures per storeview"
    )
    products = models.BooleanField(default=False)
    prices = models.BooleanField(default=False)
    objects = models.Manager()

    def __str__(self) -> str:
        return str(self.store_view_code)

    class Meta:
        unique_together = (("channel", "store_view_code"),)
