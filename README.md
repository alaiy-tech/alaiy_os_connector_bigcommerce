# Alaiy OS Connector: BigCommerce

Connects a BigCommerce store to [Alaiy OS](https://alaiy.com), syncing
products, orders, and inventory through BigCommerce's Admin API (v3).

## Features

- **Secure authentication** — a store-scoped access token (X-Auth-Token),
  with a live Test Connection check.
- **Resilient sync** — automatic retry with backoff on rate limits (honors
  BigCommerce's own rate-limit headers) and transient errors, paginated
  fetches, and a full sync log with per-run counts and failure detail.
- **Scheduled or on-demand** — configurable pull/push intervals, with a
  guard against a crashed run blocking future syncs.

## Setup

1. In BigCommerce: **Settings → API → API Accounts**, create a Legacy API
   Account (or a store-level app) with Products/Orders/Customers
   read/write scope. Note the Store Hash (from the store's own control
   panel URL) and the Access Token.
2. In Alaiy OS: open **BigCommerce Connector Settings** and fill in:
   - **Store Hash** and **Access Token** — from step 1.
   - **Company** / **Default Warehouse** / **Price List** — where synced
     data lands in Alaiy OS.
3. Click **Test Connection** to confirm the credentials work.
4. Enable the connector and save.

## Roadmap

Product and variant import (with categories, brands, and stock) is live.
Order import, and pushing inventory/price updates back to BigCommerce,
are planned next.

## License

AGPL-3.0
