# Django PIM Export to Magento API

Products, prices, pictures, and attributes export from PIM to Magento via the Magento REST API.
Celery-driven, per-channel configuration. Companion module to
[entirius-django-pim](https://github.com/entirius/entirius-django-pim).

## Quick Start

Requires Python 3.11+.

```bash
make install                     # uv sync, incl. extras
make test                        # pytest (smoke imports, sqlite)
```

### Other commands

```bash
make check    # ruff check + format-check
make fix      # auto-fix lint + format
```

## Usage

Add `django_pim_export_to_magento_api` to `INSTALLED_APPS` (requires `django_pim` and
`django_pricemanager`) and set `MAGENTO2_EXPORT_API_URL` + `MAGENTO2_EXPORT_API_TOKEN`.
Exports run via celery tasks or management commands:

```bash
python manage.py export-products-to-magento <shop_idx>
python manage.py export-prices-to-magento <shop_idx>
python manage.py export-product-pictures-to-magento <shop_idx>
python manage.py export-attributes-to-magento <shop_idx>
python manage.py import-magento-attributes <shop_idx>
```

## Details

See `AGENTS.md` for architecture and settings reference.
