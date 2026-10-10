# Management commands

Every command wraps the task of the same name in `django_pim_export_to_magento_api.tasks` and takes its options from
`django_utils.workers.command.ChannelCeleryCommand`:

| Option | Default | Meaning |
|---|---|---|
| `--channel_idx <idx>` | all channels | `idx` of one `Channel` of this module |
| `--celery` / `--no-celery` | off | "Run inside Celery tasks" (the option's help text); off runs the task in the process |

The export commands add:

| Option | Default | Meaning |
|---|---|---|
| `--product_id <sku>` | all products | one product, by SKU |
| `--bulk` / `--no-bulk` | on | process the queryset in batches; `--no-bulk` goes one object at a time |

`MAGENTO2_EXPORT_API_URL` and `MAGENTO2_EXPORT_API_TOKEN` must be set for all of them.

## export-products-to-magento

```bash
python manage.py export-products-to-magento --channel_idx <idx>
```

Sends products with their attributes to every Magento store view of the channel that has `products` switched on.
Extra option: `--product_class <class>`, one of `simple`, `config`, `bundle`, `custom` (default: all classes).

## export-prices-to-magento

```bash
python manage.py export-prices-to-magento --channel_idx <idx>
```

Sends prices from the latest price list of `django_pricemanager` to every store view that has `prices` switched on.
Extra option: `--product_class <class>`, as above.

## export-product-pictures-to-magento

```bash
python manage.py export-product-pictures-to-magento --channel_idx <idx> --picture_roles main general
```

Sends product pictures to every store view that has `pictures` switched on. Extra option: `--picture_roles`, any of
`main`, `general`, `unknown`, `variant`, `angle` (default: `main general`).

## export-attributes-to-magento

```bash
python manage.py export-attributes-to-magento --channel_idx <idx>
```

Checks the features selected on the channel against the Magento attribute list (a feature Magento does not have is
logged and skipped, never created), syncs the options of select and multiselect attributes, then sends the attribute
values of the channel's products.

## import-magento-attributes

```bash
python manage.py import-magento-attributes --channel_idx <idx>
```

Reads the attribute list from Magento and matches it to the PIM features by attribute code. Takes the common options
only.
