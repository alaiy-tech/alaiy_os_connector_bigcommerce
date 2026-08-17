# Products

Full catalog import, BigCommerce → Alaiy OS only (no push direction exists).
Code lives in `bigcommerce/products.py`, called from
`bigcommerce/sync.py: run_pull_sync`.

---

## BigCommerce field → Alaiy OS field

| BigCommerce field | Alaiy OS field | Notes |
|---|---|---|
| `sku` (product or variant) | Item Code | Falls back to `BC-{product_id}` (simple) or `BC-{product_id}-{variant_id}` (variant) when SKU is blank. |
| `name` | Item Name | Variant items get `"{product name} - {Color: X, Size: Y}"` appended from the variant's own `option_values` (`option_display_name`/`label`). |
| `description` | Description | Same product description used for every variant Item. |
| `price` (variant price if set, else product price) | Item Price, "Standard Selling"-style price list (whatever Price List is configured) | `sale_price` is deliberately not used. |
| `images[]` | Item.image | Primary image if flagged `is_thumbnail`, else first in the array; a variant with no own `image_url` falls back to the parent product's image. |
| `categories[0]` | Item Group | BigCommerce only stores category IDs on the product — resolved through a one-time id→name map fetched from `/catalog/categories`. Only the first category is used; multi-category products lose the rest. |
| `brand_id` | Brand | Resolved through a one-time id→name map from `/catalog/brands`. |
| `inventory_tracking` + `inventory_level` | Item.is_stock_item + Stock Reconciliation | Stock is only reconciled when tracking is `"product"` (uses the product's own level) or `"variant"` (uses that variant's level); `"none"` means the Item is marked non-stock and nothing is reconciled. |
| `type == "digital"` | Item.is_stock_item = 0 | Digital products are never treated as stock items regardless of `inventory_tracking`. |
| `is_visible` | Item.disabled | Inverted: not visible on the storefront → Item disabled. |
| `weight` | Item.weight_per_unit | |
| product `id` / variant `id` | `bc_product_id` / `bc_variant_id` custom fields | No ERPNext-native equivalent exists for these, added via `setup/install.py`. |

## Variant handling

One request per page (`?include=variants,images` on `/catalog/products`)
returns everything needed — no second request per product, unlike
connectors for platforms that require a separate variation lookup.

BigCommerce always returns at least one variant per product, even for a
simple (non-variant) product — its own base SKU/price as a single-entry
`variants` array. To avoid creating a redundant duplicate Item, this
connector treats a product as "variant-having" only when its `variants`
array has more than one entry; a single-variant product is imported as one
plain Item, not a 1-variant special case.

## Known gaps

- Only the first category on a product is used for Item Group — a product
  in multiple categories has the rest silently dropped.
- No delta detection: every pull re-reads and re-saves every product and
  variant, every time.
- No deletion handling: a product removed from BigCommerce is never
  disabled or deleted in Alaiy OS by this connector.
- Order import is not built — this page is catalog-only.
