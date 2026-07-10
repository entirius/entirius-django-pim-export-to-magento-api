# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from django.db import models


class Channel(models.Model):
    idx = models.CharField(max_length=64)
    label = models.CharField(max_length=64)
    features = models.ManyToManyField("django_pim.Feature", blank=True, related_name="magento_export_features_channel")
    product_create_features = models.ManyToManyField(
        "django_pim.Feature",
        blank=True,
        related_name="magento_export_product_features_channel",
        help_text="Choose wich features will be passed to magento with product create",
    )
    create_option_in_magento = models.BooleanField(
        default=True, help_text="Determines whether attribute options should be created in Magento"
    )
    objects = models.Manager()

    def __str__(self) -> str:
        return f"{self.label} | {self.idx}"
