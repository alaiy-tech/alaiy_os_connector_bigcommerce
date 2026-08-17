# Copyright (c) 2026, Alaiy and contributors
# For license information, please see license.txt
"""
Product IMPORT: pull BigCommerce's catalog into Alaiy OS as Items.

Field mapping confirmed against the real vendored OpenAPI specs
(docs/bigcommerce/admin-catalog-products.json, admin-catalog-product-
variants.json, admin-catalog-categories.json, admin-catalog-brands.json),
not guessed:
  price               -> Item Price, "Standard Selling" (product.price /
                          variant.price -- the base storefront price;
                          sale_price is deliberately not used, same
                          "current effective price" reasoning as
                          WooCommerce's connector)
  images              -> Item.image (primary_image if flagged, else first
                          in the `images` array; a variant falls back to
                          the parent's image since variant.image_url is
                          often blank)
  categories[0]       -> Item.item_group. BigCommerce's `categories` field
                          on a product is just an array of numeric IDs, no
                          name -- resolved via a category id->name map
                          fetched once from /catalog/categories (only the
                          first category is used, same single-Link
                          limitation as every other connector here).
  brand_id            -> Item.brand, resolved via a one-time id->name map
                          from /catalog/brands.
  inventory_tracking  -> Item.is_stock_item; stock is only reconciled when
                          tracking is "product" (own inventory_level) or
                          "variant" (the variant's own inventory_level) --
                          "none" means nothing to stock.
  variant.option_values -> appended to item_name as "Color: Black" pairs,
                          taken directly from option_display_name/label
                          (BigCommerce includes these on the variant
                          itself, unlike WooCommerce which needs a second
                          lookup against the parent product's attributes).
  identity            -> bc_product_id / bc_variant_id custom fields (no
                          ERPNext equivalent exists for these).

`?include=variants,images` fetches everything in one call per product
page -- BigCommerce supports this natively (confirmed in the spec's
IncludeParamBase enum), unlike WooCommerce which needs a second request
per variable product for its variations.
"""

import frappe
from frappe.utils import flt

from alaiy_os_connector_bigcommerce.bigcommerce.client import BigCommerceClient

_DEFAULT_ITEM_GROUP = "All Item Groups"
_DEFAULT_STOCK_UOM = "Nos"


def _stock_uom():
    return frappe.db.get_single_value("Stock Settings", "stock_uom") or _DEFAULT_STOCK_UOM


def _ensure_root_item_group():
    if frappe.db.exists("Item Group", _DEFAULT_ITEM_GROUP):
        return _DEFAULT_ITEM_GROUP
    existing_root = frappe.db.get_value(
        "Item Group", {"is_group": 1, "parent_item_group": ["in", ("", None)]}, "name"
    )
    if existing_root:
        return existing_root
    doc = frappe.new_doc("Item Group")
    doc.item_group_name = _DEFAULT_ITEM_GROUP
    doc.is_group = 1
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def _ensure_item_group(name):
    root = _ensure_root_item_group()
    name = (name or "").strip()
    if not name:
        return root
    if frappe.db.exists("Item Group", name):
        return name
    try:
        doc = frappe.new_doc("Item Group")
        doc.item_group_name = name
        doc.parent_item_group = root
        doc.is_group = 0
        doc.flags.ignore_permissions = True
        doc.insert()
        return name
    except Exception:
        frappe.log_error(
            title=f"BigCommerce import: failed to create Item Group {name}",
            message=frappe.get_traceback(),
        )
        return root


def _ensure_brand(name):
    name = (name or "").strip()
    if not name:
        return None
    if frappe.db.exists("Brand", name):
        return name
    try:
        doc = frappe.new_doc("Brand")
        doc.brand = name
        doc.flags.ignore_permissions = True
        doc.insert()
        return name
    except Exception:
        frappe.log_error(
            title=f"BigCommerce import: failed to create Brand {name}",
            message=frappe.get_traceback(),
        )
        return None


def _load_category_map(client):
    """id -> name, fetched once per pull rather than per product."""
    mapping = {}
    for page in client.get_all_pages("catalog/categories"):
        for category in page:
            mapping[category["id"]] = category.get("name")
    return mapping


def _load_brand_map(client):
    mapping = {}
    for page in client.get_all_pages("catalog/brands"):
        for brand in page:
            mapping[brand["id"]] = brand.get("name")
    return mapping


def _reconcile_stock(item_code, warehouse, company, qty):
    if not warehouse or not company:
        return
    current = flt(frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
    ) or 0)
    if current == qty:
        return
    doc = frappe.new_doc("Stock Reconciliation")
    doc.company = company
    doc.purpose = "Stock Reconciliation"
    doc.append("items", {"item_code": item_code, "warehouse": warehouse, "qty": qty})
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    doc.submit()


def _set_standard_selling_price(item_code, price_list, rate):
    if rate is None:
        return
    name = frappe.db.get_value(
        "Item Price", {"item_code": item_code, "price_list": price_list}, "name"
    )
    if name:
        frappe.db.set_value("Item Price", name, "price_list_rate", rate)
        return
    frappe.get_doc({
        "doctype": "Item Price",
        "item_code": item_code,
        "price_list": price_list,
        "price_list_rate": rate,
    }).insert(ignore_permissions=True)


def _item_code_for(sku, bc_id, bc_variant_id=None):
    if sku:
        return sku
    if bc_variant_id:
        return f"BC-{bc_id}-{bc_variant_id}"
    return f"BC-{bc_id}"


def _upsert_item(item_code, item_name, description, image_url, disabled,
                  bc_product_id, bc_variant_id, item_group, brand, weight, not_stocked):
    is_new = not frappe.db.exists("Item", item_code)
    if is_new:
        item = frappe.new_doc("Item")
        item.item_code = item_code
        item.stock_uom = _stock_uom()
    else:
        item = frappe.get_doc("Item", item_code)

    item.item_name = (item_name or item_code)[:140]
    item.description = description or item.item_name
    item.disabled = 0 if not disabled else 1
    item.item_group = item_group
    item.is_stock_item = 0 if not_stocked else 1
    if brand:
        item.brand = brand
    if weight:
        item.weight_per_unit = weight
    if image_url:
        item.image = image_url
    item.bc_product_id = str(bc_product_id)
    item.bc_variant_id = str(bc_variant_id) if bc_variant_id else ""
    item.flags.ignore_permissions = True

    if is_new:
        item.insert(ignore_permissions=True)
    else:
        item.save(ignore_permissions=True)
    return item.item_code, is_new


def _primary_image_url(images):
    if not images:
        return None
    for img in images:
        if img.get("is_thumbnail"):
            return img.get("url_standard") or img.get("image_url")
    return images[0].get("url_standard") or images[0].get("image_url")


def _upsert_simple_product(product, price_list, warehouse, company, category_map, brand_map):
    sku = (product.get("sku") or "").strip()
    item_code = _item_code_for(sku, product["id"])
    image_url = _primary_image_url(product.get("images"))
    category_ids = product.get("categories") or []
    item_group = _ensure_item_group(category_map.get(category_ids[0]) if category_ids else None)
    brand = _ensure_brand(brand_map.get(product.get("brand_id"))) if product.get("brand_id") else None

    item_code, is_new = _upsert_item(
        item_code=item_code,
        item_name=product.get("name"),
        description=product.get("description"),
        image_url=image_url,
        disabled=not product.get("is_visible", True),
        bc_product_id=product["id"],
        bc_variant_id=None,
        item_group=item_group,
        brand=brand,
        weight=flt(product.get("weight")) if product.get("weight") else None,
        not_stocked=product.get("type") == "digital",
    )
    price = product.get("price")
    _set_standard_selling_price(item_code, price_list, flt(price) if price not in (None, "") else None)

    if product.get("inventory_tracking") == "product" and product.get("inventory_level") is not None:
        _reconcile_stock(item_code, warehouse, company, flt(product["inventory_level"]))

    return is_new


def _upsert_variant(product, variant, price_list, warehouse, company, category_map, brand_map):
    sku = (variant.get("sku") or "").strip()
    item_code = _item_code_for(sku, product["id"], variant["id"])
    image_url = variant.get("image_url") or _primary_image_url(product.get("images"))
    category_ids = product.get("categories") or []
    item_group = _ensure_item_group(category_map.get(category_ids[0]) if category_ids else None)
    brand = _ensure_brand(brand_map.get(product.get("brand_id"))) if product.get("brand_id") else None

    attrs = ", ".join(
        f"{ov.get('option_display_name')}: {ov.get('label')}"
        for ov in variant.get("option_values") or [] if ov.get("label")
    )
    item_name = f"{product.get('name')} - {attrs}" if attrs else product.get("name")

    item_code, is_new = _upsert_item(
        item_code=item_code,
        item_name=item_name,
        description=product.get("description"),
        image_url=image_url,
        disabled=not product.get("is_visible", True),
        bc_product_id=product["id"],
        bc_variant_id=variant["id"],
        item_group=item_group,
        brand=brand,
        weight=flt(variant.get("weight")) if variant.get("weight") else None,
        not_stocked=product.get("type") == "digital",
    )
    price = variant.get("price") if variant.get("price") is not None else product.get("price")
    _set_standard_selling_price(item_code, price_list, flt(price) if price not in (None, "") else None)

    if product.get("inventory_tracking") == "variant" and variant.get("inventory_level") is not None:
        _reconcile_stock(item_code, warehouse, company, flt(variant["inventory_level"]))

    return is_new


def pull_products(log):
    """
    Full catalog import: page through /catalog/products with variants+
    images included inline. A product with a `variants` array of more than
    one entry is treated as variant-having; BigCommerce always returns at
    least one variant even for a simple product (its own base SKU/price),
    so a single-variant product is imported as a simple Item, not a
    1-variant one, to avoid a redundant duplicate Item per product.
    """
    settings = frappe.get_single("BigCommerce Connector Settings")
    price_list = settings.bc_price_list or "Standard Selling"
    warehouse = settings.bc_default_warehouse
    company = settings.bc_company
    client = BigCommerceClient()

    category_map = _load_category_map(client)
    brand_map = _load_brand_map(client)

    processed = created = updated = failed = 0
    pages_done = 0

    for page_rows in client.get_all_pages("catalog/products", params={"include": "variants,images"}):
        pages_done += 1
        for product in page_rows:
            processed += 1
            try:
                variants = product.get("variants") or []
                if len(variants) > 1:
                    any_new = False
                    for variant in variants:
                        is_new = _upsert_variant(
                            product, variant, price_list, warehouse, company, category_map, brand_map
                        )
                        any_new = any_new or is_new
                    if any_new:
                        created += 1
                    else:
                        updated += 1
                else:
                    is_new = _upsert_simple_product(
                        product, price_list, warehouse, company, category_map, brand_map
                    )
                    if is_new:
                        created += 1
                    else:
                        updated += 1
            except Exception:
                failed += 1
                frappe.log_error(
                    title=f"BigCommerce product pull failed: {product.get('id')}",
                    message=frappe.get_traceback(),
                )

        log.items_processed = processed
        log.items_created = created
        log.items_updated = updated
        log.items_failed = failed
        log.pages_done = pages_done
        log.save(ignore_permissions=True)
        frappe.db.commit()

    if failed:
        log.error_message = f"{failed} product(s) failed -- see Error Log."[:2000]
