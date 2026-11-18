# BigCommerce Connector — what it actually does

BigCommerce is a hosted e-commerce platform a store runs its storefront on.
Alaiy OS is the ERPNext-based back office. This connector moves catalog data
from BigCommerce into Alaiy OS as Items.

---

## The short version

| | Direction | Automatic? |
|---|---|---|
| Products (incl. variants, images, category, brand) | BigCommerce → Alaiy OS | yes, on the configured Pull Sync Interval, or on demand via the connector card's "Pull" button |
| Stock levels | BigCommerce → Alaiy OS | yes, as part of the same product pull, but only for items where BigCommerce reports inventory tracking |
| Orders | BigCommerce → Alaiy OS | **not built.** No order import code exists in this connector yet. |
| Anything | Alaiy OS → BigCommerce | **not built.** The "push" sync exists as a named job and a settings interval, but its worker is an empty stub — it does nothing. |

**Nothing writes to BigCommerce, ever, in the current code.** The push
direction is wired up in the UI (a Push button, a Push Sync Interval field,
a scheduler slot) but the job it calls has no body. Nothing else happens
automatically until the connector is enabled (`Enable BigCommerce` checked)
— disabled, its per-minute scheduler check is a no-op and the manual
pull/push buttons still run but the client raises immediately without a
Store Hash and Access Token configured.

---

## Coming IN from BigCommerce

### Product catalog pull
Triggered on the configured interval (5/15/30/60 min or Disabled) or by
pressing "Pull" on the connector card. Pages through every product in
`/catalog/products` with variants and images included in the same request.

- A product with more than one BigCommerce variant becomes one Alaiy OS Item
  per variant (color/size combo), each carrying the parent's shared fields
  (description, category, brand) plus its own SKU, price, and stock.
- A product with exactly one variant (BigCommerce always returns at least
  one, even for non-variant products) is imported as a single Item — no
  redundant "1-variant" duplicate.
- Category and brand are resolved through one-time id→name lookup maps
  fetched once per pull, not once per product.
- Stock is reconciled (via a Stock Reconciliation) only when BigCommerce
  reports `inventory_tracking` as `"product"` or `"variant"` for that
  row — `"none"` means nothing is stocked from that read.
- Every row updates a BigCommerce Sync Log (`pull` type) with running
  counts of items processed/created/updated/failed; a failed individual
  product is logged and skipped, it does not abort the whole run.

### Orders
Not built. There is no order-import module, no Sales Order creation code,
and no order-related custom fields anywhere in this connector.

---

## Going OUT to BigCommerce

### Push sync
A "Push" button and a Push Sync Interval setting exist and will enqueue a
job, but `run_push_sync`'s worker function is an empty stub (`pass`) —
running it does nothing to BigCommerce or Alaiy OS. There is no code that
writes Items, prices, or stock from Alaiy OS back to BigCommerce.
