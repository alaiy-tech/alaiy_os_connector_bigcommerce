# Architecture & Sync Engine

The plumbing shared across every domain: auth, the API client, retry
behavior, logging, and how the scheduler decides when to run.

---

## Connector pattern

Standalone Frappe app, registered into Alaiy OS's OS Connector Registry on
every `after_migrate` (`setup/install.py: sync_connector_registry`), with a
single-row Settings DocType (`BigCommerce Connector Settings`) and its own
Sync Log doctype (`BigCommerce Sync Log`) shown under the Alaiy OS "Logs"
sidebar section.

## Auth & client

`bigcommerce/client.py`'s `BigCommerceClient` authenticates with a single
long-lived access token sent as `X-Auth-Token` on every request — no
OAuth2 exchange happens on the connector's side. Every request is scoped
under `/stores/{store_hash}/v3/...`.

Retry policy: up to 3 retries on `429, 500, 502, 503, 504`, with a linear
backoff (`wait * (attempt + 1)`) honoring `Retry-After` or
`X-Rate-Limit-Time-Reset-Ms` response headers when present, otherwise
defaulting to 2 seconds. Request timeout is `(10, 60)` (connect, read).
`get_all_pages()` walks a v3 list endpoint's `page`/`limit` params and its
`meta.pagination.total_pages` block, yielding one page's `data` array at a
time.

## Change detection & identity

There is no delta/webhook-based change detection — every pull is a full
catalog re-walk of `/catalog/products`. Identity for upsert is the Item
code: the BigCommerce SKU if present, else `BC-{product_id}` (simple
product) or `BC-{product_id}-{variant_id}` (variant). An existing Item at
that code is updated in place; a new code creates a new Item. The
`bc_product_id` / `bc_variant_id` custom fields on Item store the raw
BigCommerce IDs for reference but aren't themselves used to look up the
Item — the item_code is.

There is no "skip unchanged rows" optimization — every product/variant in
every pull is re-read and re-saved regardless of whether anything changed.

## Scheduler

`bigcommerce/sync_jobs.py: check_and_enqueue()` runs every minute (cron
hook in `hooks.py`). It does nothing if the connector is disabled or the
Sync Log doctype doesn't exist yet. For each of pull/push, it enqueues the
matching job (`long` queue, 600s timeout) only when:
- the configured interval isn't "Disabled", and
- no non-stale `running` log exists for that sync type (a run stuck
  "running" for more than 1800 seconds is treated as dead and ignored), and
- the last `success` log for that sync type is older than the configured
  interval.

## Sync log / error visibility

Every pull/push run creates a `BigCommerce Sync Log` row
(`sync.py: get_or_create_log`), moving through `queued` → `running` →
`success`/`failed`. Manual triggers (via the connector card's Pull/Push
buttons, `api/sync.py`) pre-create the log as `queued` so it appears
immediately; the scheduler creates it itself. Fields tracked: `sync_type`
(pull/push), `trigger` (scheduled/manual/webhook), `status`, `started_at`,
`finished_at`, `items_processed/created/updated/failed`,
`pages_total/pages_done`, `error_message`, `log_messages`. A run is marked
`failed` if it raised an uncaught exception (traceback saved to
`error_message` and to the Frappe Error Log) or if the worker itself
recorded any `items_failed` — even one row failing marks the whole run
failed, though the pull loop itself continues past individual product
failures rather than aborting.
