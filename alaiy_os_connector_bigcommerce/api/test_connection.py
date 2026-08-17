# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Reachability check for the saved credentials. Wired into the registry via
connector_meta["test_method"] and called by the "Test Connection" button.
Always returns {"success": bool, "message": str} — never raises to the caller.
"""

import frappe

from alaiy_os_connector_bigcommerce.bigcommerce.client import BigCommerceAPIError, BigCommerceClient


@frappe.whitelist()
def test_connection():
    settings = frappe.get_single("BigCommerce Connector Settings")
    if not settings.bc_store_hash:
        return {"success": False, "message": "Store Hash is not set."}
    if not settings.bc_access_token:
        return {"success": False, "message": "Access Token is not set."}

    try:
        client = BigCommerceClient()
    except RuntimeError as e:
        return {"success": False, "message": str(e)}

    # Cheapest real read that both proves the token works and that this is
    # actually a reachable store for this store_hash.
    try:
        client.get("catalog/products", params={"limit": 1})
        return {"success": True, "message": "Connected successfully."}
    except BigCommerceAPIError as e:
        if e.status_code == 401:
            return {"success": False, "message": "Authentication failed — check your Access Token."}
        if e.status_code == 404:
            return {"success": False, "message": "Store not found — check your Store Hash."}
        return {"success": False, "message": str(e)}
    except Exception as e:
        return {"success": False, "message": str(e)[:200]}
