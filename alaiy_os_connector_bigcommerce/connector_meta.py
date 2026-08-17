"""
Single source of truth for this connector's registration metadata.
Consumed by setup/install.py → upserted into alaiy_os's OS Connector Registry.
"""

connector_meta = {
    "connector_id": "bigcommerce",
    "connector_name": "BigCommerce",
    "connector_app": "alaiy_os_connector_bigcommerce",
    # "channel" (sell TO — e.g. Shopify) or "supplier" (buy FROM — e.g. Cloudstore)
    "connector_type": "channel",
    "description": "Syncs products, orders, and inventory with a BigCommerce store via its Admin API.",
    "icon": "box",
    "icon_url": "",
    "settings_doctype": "BigCommerce Connector Settings",
    "test_method": "alaiy_os_connector_bigcommerce.api.test_connection.test_connection",
    "sync_categories_method": "alaiy_os_connector_bigcommerce.api.sync.trigger_pull_sync",
    "sync_items_method": "alaiy_os_connector_bigcommerce.api.sync.trigger_push_sync",
    "sync_status_method": "alaiy_os_connector_bigcommerce.api.sync.get_sync_status",
    "sync_categories_label": "Pull",
    "sync_items_label": "Push",
    "is_enabled": 0,
    "connection_status": "untested",
}
