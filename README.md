# entirius-django-pim-export-to-magento-api

A Django module that exports the product catalog of Entirius, the open-source modular ecommerce platform, to an
existing Magento 2 store over its REST API. Products, prices, pictures and attributes are pushed per channel and
store view, from management commands or Celery tasks.

[![PyPI](https://img.shields.io/pypi/v/entirius-django-pim-export-to-magento-api.svg)](https://pypi.org/project/entirius-django-pim-export-to-magento-api/)
[![Python](https://img.shields.io/pypi/pyversions/entirius-django-pim-export-to-magento-api.svg)](https://pypi.org/project/entirius-django-pim-export-to-magento-api/)
[![License: MPL-2.0](https://img.shields.io/badge/license-MPL--2.0-blue.svg)](https://github.com/entirius/entirius-django-pim-export-to-magento-api/blob/develop/LICENSE)

## What it does

- Exports products with their attributes to Magento 2, one store view at a time, with a fallback price for products
  the price manager has no price for.
- Exports prices from the latest price list of the price manager.
- Exports product pictures, mapping picture roles to Magento image types.
- Sends attribute values, syncs the options of select attributes and matches Magento attributes to catalog features.
- Keeps the export state of every product, with the failure message when Magento rejects it.
- Maps each channel to its Magento store views; products, prices and pictures are switched on per store view.

## Installation

```shell
uv add entirius-django-pim-export-to-magento-api
pip install entirius-django-pim-export-to-magento-api
```

```python
INSTALLED_APPS = [
    ...
    "django_regional",
    "django_utils",
    "django_pim",
    "django_pricemanager",
    "django_pim_export_to_magento_api",
]
```

Required settings: `MAGENTO2_EXPORT_API_URL` and `MAGENTO2_EXPORT_API_TOKEN`. Optional settings:
`PICTURE_ROLE_TO_MAGENTO_TYPE`, `PICTURE_POSITION_TO_MAGENTO`, `PICTURES_ONLY_LANGUAGE`, `PRODUCT_DEFAULT_PRICE`;
reference with defaults in
https://github.com/entirius/entirius-django-pim-export-to-magento-api/blob/develop/AGENTS.md (section Settings).

## Quick start

```python
# settings.py
MAGENTO2_EXPORT_API_URL = "https://magento.example.com/rest/"
MAGENTO2_EXPORT_API_TOKEN = "<api-token>"

# a shell or a scheduled job
from django.core.management import call_command

call_command("export-products-to-magento", channel_idx="default")
```

`channel_idx` is the `idx` of a `Channel` configured in the Django admin together with its Magento store views;
without it the command runs for every channel.

## Requirements

- Python 3.11 or newer, Django 5.0 or newer.
- PostgreSQL (through `entirius-django-pim`).
- Celery with a configured `celery-once` backend: every task module imports it.
- A Magento 2 store with a REST API integration token.
- Entirius packages pulled in: `entirius-django-pim`, `entirius-django-pricemanager`, `entirius-django-regional`,
  `entirius-django-utils`, `entirius-py-magento2-sdk2`, `entirius-py-process-logger`, `entirius-py-idx-normalizator`.

## Documentation

- Module docs (management commands): https://github.com/entirius/entirius-django-pim-export-to-magento-api/tree/develop/docs
- Entirius documentation: https://docs.entirius.com/
- Releases: https://github.com/entirius/entirius-django-pim-export-to-magento-api/releases

## Part of Entirius

This module runs inside the Entirius backend service (Volkanos) and is one of the bridges that connect it to an
existing Magento 2 store.

- Backend service: https://github.com/entirius/entirius-service-volkanos
- Docker harness: https://github.com/entirius/entirius-zeno
- Product and price modules: https://github.com/entirius/entirius-django-pim,
  https://github.com/entirius/entirius-django-pricemanager
- Magento 2 SDK it uses: https://github.com/entirius/entirius-py-magento2-sdk2
- Sibling bridges: https://github.com/entirius/entirius-django-checkout-export-to-magento-api,
  https://github.com/entirius/entirius-django-checkout-import-from-magento-api,
  https://github.com/entirius/entirius-django-accounts-export-to-magento-api

## Development

```shell
make install     # sync dependencies (uv)
make check       # lint + format check (ruff)
make test        # test suite (pytest + pytest-django, import smoke test on sqlite)
```

Development and agent instructions: https://github.com/entirius/entirius-django-pim-export-to-magento-api/blob/develop/AGENTS.md

## License

Mozilla Public License 2.0 (MPL-2.0) — see https://github.com/entirius/entirius-django-pim-export-to-magento-api/blob/develop/LICENSE.
