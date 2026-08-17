# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
HTTP client for the BigCommerce Admin API (v3).

Auth: a single access token in the X-Auth-Token header (from a Legacy API
Account or store-level OAuth app) -- BigCommerce doesn't use Basic Auth or
an OAuth2 client_credentials exchange the way WooCommerce/Shopify's custom
apps do; the token itself is long-lived and used directly on every request.

Every request is scoped under /stores/{store_hash}/v3/... -- store_hash
identifies which store, same role Shopify's store domain or WooCommerce's
store URL plays for those connectors.

Retry policy mirrors alaiy_os_connector_fedex's client.py (fixed max
retries, linear backoff, honors Retry-After) -- BigCommerce enforces a real
rate limit (X-Rate-Limit-Requests-Left / -Time-Reset-Ms response headers)
so a retry-on-429 default is the right call here, not an afterthought.
"""

import time

import frappe
import requests

API_BASE = "https://api.bigcommerce.com"

_DEFAULT_TIMEOUT = (10, 60)
_RETRYABLE_STATUS = (429, 500, 502, 503, 504)
_MAX_RETRIES = 3
_DEFAULT_RETRY_AFTER_SECONDS = 2


class BigCommerceAPIError(Exception):
    """Raised with the response body preserved (BigCommerce error bodies are
    {"status": ..., "title": ..., "errors": {...}})."""

    def __init__(self, message, status_code=None, retryable=False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _parse_bc_error(resp):
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300]
    return body.get("title") or body.get("message") or resp.text[:300]


class BigCommerceClient:
    def __init__(self):
        settings = frappe.get_single("BigCommerce Connector Settings")
        store_hash = (settings.bc_store_hash or "").strip()
        access_token = settings.get_password("bc_access_token") if settings.bc_access_token else None

        if not store_hash or not access_token:
            raise RuntimeError(
                "BigCommerce connector is not configured (Store Hash / Access Token missing)."
            )

        self.base_url = f"{API_BASE}/stores/{store_hash}/v3"
        self._headers = {
            "X-Auth-Token": access_token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(self, method, path, params=None, json=None, timeout=_DEFAULT_TIMEOUT):
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_resp = None
        for attempt in range(_MAX_RETRIES + 1):
            resp = requests.request(
                method, url, headers=self._headers, params=params, json=json, timeout=timeout,
            )
            if resp.status_code < 400:
                return resp

            last_resp = resp
            if resp.status_code not in _RETRYABLE_STATUS or attempt == _MAX_RETRIES:
                break

            retry_after = resp.headers.get("Retry-After") or resp.headers.get("X-Rate-Limit-Time-Reset-Ms")
            if retry_after and retry_after.replace(".", "", 1).isdigit():
                wait = float(retry_after) / 1000 if resp.headers.get("X-Rate-Limit-Time-Reset-Ms") else float(retry_after)
            else:
                wait = _DEFAULT_RETRY_AFTER_SECONDS
            time.sleep(wait * (attempt + 1))

        raise BigCommerceAPIError(
            f"{last_resp.status_code}: {_parse_bc_error(last_resp)}",
            status_code=last_resp.status_code,
            retryable=last_resp.status_code in _RETRYABLE_STATUS,
        )

    def get(self, path, params=None, timeout=_DEFAULT_TIMEOUT):
        return self._request("GET", path, params=params, timeout=timeout).json()

    def post(self, path, json=None, timeout=_DEFAULT_TIMEOUT):
        return self._request("POST", path, json=json, timeout=timeout).json()

    def put(self, path, json=None, timeout=_DEFAULT_TIMEOUT):
        return self._request("PUT", path, json=json, timeout=timeout).json()

    def delete(self, path, params=None, timeout=_DEFAULT_TIMEOUT):
        return self._request("DELETE", path, params=params, timeout=timeout).json()

    def get_all_pages(self, path, params=None, limit=250, timeout=_DEFAULT_TIMEOUT):
        """Paginates a BigCommerce v3 list endpoint using its page/limit
        params and response meta.pagination block. Yields each page's list
        of rows (the `data` array)."""
        page = 1
        page_params = dict(params or {})
        page_params["limit"] = limit
        while True:
            page_params["page"] = page
            body = self._request("GET", path, params=page_params, timeout=timeout).json()
            rows = body.get("data") or []
            if not rows:
                return
            yield rows

            pagination = (body.get("meta") or {}).get("pagination") or {}
            total_pages = pagination.get("total_pages") or 1
            if page >= total_pages:
                return
            page += 1
