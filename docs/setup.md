# Setup & Configuration

This is a standard Frappe app (`alaiy_os_connector_bigcommerce`). It installs
disabled — the pull/push scheduler and both custom Item fields' actual use
are gated behind flipping `Enable BigCommerce` on in the settings Single
DocType, though the custom fields themselves are always provisioned (see
"First enable" below).

---

## 1. Prerequisites

- Frappe bench with `alaiy_os` and `erpnext` installed (both are hard
  dependencies declared in `hooks.py`'s `required_apps`).
- A BigCommerce store, with an API Account created for it (Legacy API
  Account, or a store-level OAuth app) under Settings > API > API Accounts.

## 2. BigCommerce credentials

| BigCommerce-side value | Settings field |
|---|---|
| Store hash — the `abc123` in `store-abc123.mybigcommerce.com`, from Settings > Store Profile or the store's own URL | Store Hash (`bc_store_hash`) |
| A token minted from a Legacy API Account (or store-level OAuth app) created under Settings > API > API Accounts, with Products/Orders/Customers read/write scope | Access Token (`bc_access_token`) |

The Access Token is a value you generate on BigCommerce yourself and paste
in directly — this connector does not mint or refresh it. It's a
long-lived token sent as-is on every request in the `X-Auth-Token` header;
there is no OAuth2 client-credentials exchange happening on the connector
side.

## 3. BigCommerce Connector Settings — every field

**API Connection**

| Field | Type | Purpose |
|---|---|---|
| Enable BigCommerce (`is_enabled`) | Check | Master switch. Governs whether the per-minute scheduler will enqueue anything. |
| Store Hash (`bc_store_hash`) | Data, required | Identifies which BigCommerce store every API call targets. |
| Access Token (`bc_access_token`) | Password, required | Sent as `X-Auth-Token` on every request. |

**Alaiy OS Defaults**

| Field | Type | Purpose |
|---|---|---|
| Company (`bc_company`) | Link → Company, required | Company used when reconciling stock via Stock Reconciliation. |
| Default Warehouse (`bc_default_warehouse`) | Link → Warehouse, required | Warehouse stock is reconciled into during the product pull. |
| Price List (`bc_price_list`) | Link → Price List, required | Price List the pulled product/variant price is written to as an Item Price. Falls back to "Standard Selling" in code if left blank, but the field itself is marked required. |

**Sync Schedule**

| Field | Type | Purpose |
|---|---|---|
| Pull Sync Interval (`bc_pull_sync_interval`) | Select (Disabled/5/15/30/60 min), required, default Disabled | How often the scheduler auto-runs the product pull. |
| Push Sync Interval (`bc_push_sync_interval`) | Select (Disabled/5/15/30/60 min), required, default Disabled | How often the scheduler would auto-run the push job — currently a no-op regardless of this setting, since the push worker does nothing. |

## 4. First enable

Flipping `is_enabled` 0→1 sets an internal flag (`bc_just_enabled`) that
fires `_on_first_enable()` — currently an empty hook (a placeholder
comment notes it's reserved for one-time actions like registering
BigCommerce webhooks once real credentials exist; nothing is implemented
there yet). Disabling it the same way fires `_on_disable()`, also empty.

What actually happens unconditionally, on every enable *and* on every
`bench migrate` regardless of enabled state:
- The two custom fields (`bc_product_id`, `bc_variant_id`) are provisioned
  on the ERPNext Item doctype, idempotently, via
  `create_custom_fields(..., update=True)`.
- This connector's row is (re)registered in Alaiy OS's OS Connector
  Registry, and its Logs entry is added to the Alaiy OS sidebar.

Enabling/disabling only flips `is_enabled` on the registry row and toggles
whether the per-minute scheduler check (`check_and_enqueue`) will actually
enqueue a pull/push job — it does not itself provision or unregister
webhooks, since no webhook code exists yet.
