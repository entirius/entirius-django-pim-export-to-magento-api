# AGENTS.md

Products, prices, pictures, and attributes export from PIM to Magento via the Magento REST API —
distribution `entirius-django-pim-export-to-magento-api`, Django app
`django_pim_export_to_magento_api`. Celery-driven, per-channel configuration.

**Tech:** Python >=3.11, Django >=5.0, Celery, entirius-django-pim, entirius-django-pricemanager,
entirius-py-magento2-sdk2

## Commands

| Command | Meaning |
|---|---|
| `make install` | sync dependencies (uv, incl. extras) |
| `make check` | lint + format-check (ruff) |
| `make fix` | auto-fix lint + format |
| `make test` | test suite (pytest + pytest-django) |

## Conventions

- English only: code, docs, commits, branches, PRs.
- MPL-2.0: every non-trivial source file carries the license header (pre-commit inserts it).
- Toolchain: uv + ruff + hatchling + pytest; all config in `pyproject.toml`; `uv.lock` committed.
- Git flow: `master` (production) + `develop` (integration); changes land via PR; semver tag on `master`.
- Never rename the package / Django app_label / DB table prefix `django_pim_export_to_magento_api` —
  it is a schema contract.
- Migrations are part of the public contract — never edit an already released migration.
- Default: do not commit — git is the user's call.

## Architecture

```
Management Command / Celery task (per export type)
  → exporter.py (Magento API orchestration)
    → django-pim models (products, attributes, pictures)
    → django-pricemanager output (prices)
      → magento2-sdk2 (Magento REST client)
```

| Path | Purpose |
|------|---------|
| `models/channel.py` | `Channel` — per-Magento-instance export config (features, create options) |
| `models/magento_store.py` | `MagentoStore` — PIM shop ↔ Magento store view mapping |
| `models/export_in_magento.py` | `ExportInMagento` — per-product export state + `failed_message` |
| `tasks/` | 6 celery tasks: products, prices, pictures, attributes, product-in-category, import-attributes |
| `management/commands/` | CLI wrappers for the tasks |
| `admin/` | Django admin for the three models |
| `exporter.py` | Magento API communication layer |
| `settings.py` | `MAGENTO2_EXPORT_API_URL`, `MAGENTO2_EXPORT_API_TOKEN`, picture role/position mappings |

## Settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `MAGENTO2_EXPORT_API_URL` | `None` | Magento REST API base URL (required) |
| `MAGENTO2_EXPORT_API_TOKEN` | `None` | Magento API token (required) |
| `PICTURE_ROLE_TO_MAGENTO_TYPE` | see `settings.py` | PIM picture role → Magento image types |
| `PICTURE_POSITION_TO_MAGENTO` | see `settings.py` | Optional position overrides per role |
| `PICTURES_ONLY_LANGUAGE` | `None` | Send non-main images with one language only |
| `PRODUCT_DEFAULT_PRICE` | `99999` | Fallback price when pricemanager has none |

## Gotchas

- `tasks/__init__.py` imports all task modules eagerly — celery autodiscovery loads them, so all
  runtime dependencies (incl. `django_pricemanager`) must be installed in the host service.
- Price export reads `django_pricemanager.output.get_price_qs_by_latest_pricelist` — hard dependency.
- URL keys are generated for products missing them during export (since 1.8.0 of the private line).
