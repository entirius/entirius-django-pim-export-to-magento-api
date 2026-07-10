# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Smoke test: every public submodule imports cleanly under a configured Django."""

import importlib

import pytest

MODULES = [
    "django_pim_export_to_magento_api.apps",
    "django_pim_export_to_magento_api.commands",
    "django_pim_export_to_magento_api.exporter",
    "django_pim_export_to_magento_api.settings",
    "django_pim_export_to_magento_api.utils",
    "django_pim_export_to_magento_api.admin.channel",
    "django_pim_export_to_magento_api.admin.export_in_magento",
    "django_pim_export_to_magento_api.admin.magento_store",
    "django_pim_export_to_magento_api.models.channel",
    "django_pim_export_to_magento_api.models.export_in_magento",
    "django_pim_export_to_magento_api.models.magento_store",
    "django_pim_export_to_magento_api.tasks.export_attributes_to_magento",
    "django_pim_export_to_magento_api.tasks.export_prices_to_magento",
    "django_pim_export_to_magento_api.tasks.export_product_in_category_to_magento",
    "django_pim_export_to_magento_api.tasks.export_product_pictures_to_magento",
    "django_pim_export_to_magento_api.tasks.export_products_to_magento",
    "django_pim_export_to_magento_api.tasks.import_magento_attributes",
    "django_pim_export_to_magento_api.management.commands.export-attributes-to-magento",
    "django_pim_export_to_magento_api.management.commands.export-prices-to-magento",
    "django_pim_export_to_magento_api.management.commands.export-product-pictures-to-magento",
    "django_pim_export_to_magento_api.management.commands.export-products-to-magento",
    "django_pim_export_to_magento_api.management.commands.import-magento-attributes",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module):
    importlib.import_module(module)
