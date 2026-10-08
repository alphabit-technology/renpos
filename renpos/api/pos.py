# -*- coding: utf-8 -*-
# renpos/api/pos.py
#
# Pre-load all POS data for client-side calculations.
# Called ONCE when OrderManager opens.

import frappe
from renpos.api.statuses import editable_statuses
import json
from frappe.utils import cint, flt, nowdate


@frappe.whitelist()
def get_pos_data(pos_profile):
    """
    Everything the order screen needs to price and tax lines locally,
    in one call.
    """
    from renpos.api.guards import (
        require_restaurant_user, check_pos_profile_access, user_pos_permissions,
        effective_price_list,
    )

    require_restaurant_user()
    check_pos_profile_access(pos_profile)
    user_perms = user_pos_permissions(pos_profile)

    profile = frappe.get_doc("POS Profile", pos_profile)
    company = profile.company

    # ─── Config ───────────────────────────────────
    config = {
        "pos_profile": profile.name,
        "company": company,
        "currency": profile.currency or frappe.get_cached_value("Company", company, "default_currency"),
        "tax_inclusive": cint(getattr(profile, "ren_tax_inclusive", 0)),
        # same flags the server enforces in api.order._validate_item_calculation
        "allow_discount_change": user_perms["allow_discount_change"],
        "allow_rate_change": user_perms["allow_rate_change"],
        "is_manager": user_perms["is_manager"],
        "max_discount": user_perms["max_discount"],
        # what the person's Ren Role allows (the client asks for a PIN otherwise)
        "access": _access(pos_profile),
        "price_list": effective_price_list(profile.name),
        "warehouse": profile.warehouse,
        "write_off_account": profile.write_off_account,
        "write_off_cost_center": profile.write_off_cost_center,
        "receipt_printer": profile.get("ren_receipt_printer"),
    }
    from renpos.api.card import readers_for
    config["card_readers"] = readers_for(profile.name)

    # ─── Items with prices ────────────────────────
    items = get_items_with_prices(profile)

    # ─── Options (sets item["modifier_groups"]) ───
    from renpos.api.modifiers import catalog_for_items, modes_for
    modifier_groups = catalog_for_items(items, config["price_list"])
    modifier_modes = modes_for(profile.get("ren_restaurant"))

    # ─── Item groups (for menu tabs) ──────────────
    item_groups = get_item_groups(profile)

    # ─── Taxes ────────────────────────────────────
    taxes = get_tax_template(profile)

    # ─── Pricing Rules ────────────────────────────
    pricing_rules = get_pricing_rules(profile)

    # ─── Payment methods ──────────────────────────
    payments = []
    for p in profile.payments:
        payments.append({
            "mode_of_payment": p.mode_of_payment,
            "default": cint(p.default),
        })


    return {
        **config,
        "items": items,
        "modifier_groups": modifier_groups,
        "modifier_modes": modifier_modes,
        "item_groups": item_groups,
        "taxes": taxes,
        "pricing_rules": pricing_rules,
        "payments": payments,
        # statuses the waiter can still edit ("Allows to edit Item")
        "editable_statuses": list(editable_statuses()),
    }


def get_items_with_prices(profile):
    """
    Get all items visible in this POS profile, with their
    price_list_rate and item_tax_rate pre-resolved.

    This is the payload that enables client-side price lookups.
    """
    from renpos.api.guards import effective_price_list
    price_list = effective_price_list(profile.name)

    # Build item group filter
    item_groups = None
    if profile.item_groups and len(profile.item_groups) > 0:
        groups = [ig.item_group for ig in profile.item_groups]
        # Include child groups
        all_groups = set(groups)
        for g in groups:
            children = frappe.get_all(
                "Item Group",
                filters={"parent_item_group": g},
                pluck="name",
            )
            all_groups.update(children)
        item_groups = all_groups

    items = _get_items_clean(profile, price_list, item_groups)
    items = _with_variants(items)

    # Resolve item_tax_rate for each item
    for item in items:
        item["item_tax_rate"] = get_item_tax_rate(
            item.get("item_tax_template"), profile.company
        )
        item["rate"] = flt(item.get("price_list_rate"))
        # Remove internal field
        item.pop("item_tax_template", None)

    return items


def _get_items_clean(profile, price_list, item_groups):
    """Clean item query with proper parameter handling."""
    conditions = [
        "i.disabled = 0",
        "i.is_sales_item = 1",
    ]
    params = {
        "price_list": price_list,
        "today": nowdate(),
    }

    if item_groups:
        conditions.append("i.item_group IN %(groups)s")
        params["groups"] = list(item_groups)

    where = " AND ".join(conditions)

    # Item Tax Template lives in child table `tabItem Tax`
    # We LEFT JOIN to get the first applicable template per item.
    # If multiple rows exist (e.g. different tax categories),
    # we pick the one without tax_category or valid_from constraints first.
    return frappe.db.sql(
        """
        SELECT
            i.name as item_code,
            i.item_name,
            i.item_group,
            i.description,
            i.image,
            i.has_batch_no,
            i.has_serial_no,
            i.stock_uom,
            i.is_stock_item,
            i.has_variants,
            i.variant_of,
            COALESCE(ip.price_list_rate, 0) as price_list_rate,
            itax.item_tax_template
        FROM `tabItem` i
        LEFT JOIN `tabItem Price` ip
            ON ip.item_code = i.name
            AND ip.price_list = %(price_list)s
            AND ip.selling = 1
            AND (ip.valid_from IS NULL OR ip.valid_from <= %(today)s)
            AND (ip.valid_upto IS NULL OR ip.valid_upto >= %(today)s)
            AND IFNULL(ip.customer, '') = ''
            AND IFNULL(ip.batch_no, '') = ''
        LEFT JOIN `tabItem Tax` itax
            ON itax.parent = i.name
            AND itax.parenttype = 'Item'
            AND (itax.tax_category IS NULL OR itax.tax_category = '')
            AND (itax.valid_from IS NULL OR itax.valid_from <= %(today)s)
        WHERE {where}
        GROUP BY i.name
        ORDER BY i.item_name ASC
        """.format(where=where),
        params,
        as_dict=True,
    )


def _with_variants(items):
    """
    Sizes are ERPNext variants: a template (has_variants) is shown once, with
    `variants` = {attributes, variants: [{item_code, values, label}]} and, as
    its price, the cheapest one ("from $X"); the waiter picks the size and
    the line is the variant. Variants stay in the list (prices, taxes,
    options) named "Coke Large". Templates with no variant to sell go away.
    """
    from renpos.api.variants import variant_info
    codes = {i["item_code"] for i in items}
    info = variant_info([i["item_code"] for i in items if cint(i.get("has_variants"))], only=codes)
    by_code = {i["item_code"]: i for i in items}
    out = []
    for item in items:
        if cint(item.get("has_variants")):
            vi = info.get(item["item_code"])
            if not vi:
                continue
            item["variants"] = vi
            prices = [flt(by_code[v["item_code"]].get("price_list_rate")) for v in vi["variants"]]
            item["price_list_rate"] = min(prices) if prices else 0
        elif item.get("variant_of"):
            template = by_code.get(item["variant_of"])
            label = next((v["label"] for v in info.get(item["variant_of"], {}).get("variants", [])
                          if v["item_code"] == item["item_code"]), "")
            if template and label:
                item["item_name"] = f"{template['item_name']} {label}"
                item["variant_label"] = label
        out.append(item)
    return out


def get_item_tax_rate(item_tax_template, company):
    """
    Resolve an Item Tax Template into the actual tax rates JSON.

    Input: "Honduras Tax Template" (Link to Item Tax Template)
    Output: '{"VAT - HN": 15.0}' (JSON string)

    This is what OrderItem.tax_calculate() uses to compute taxes.
    """
    if not item_tax_template:
        return "{}"

    tax_rates = {}

    template = frappe.get_cached_doc("Item Tax Template", item_tax_template)
    for tax in template.taxes:
        if tax.tax_type:
            tax_rates[tax.tax_type] = flt(tax.tax_rate)

    return json.dumps(tax_rates)


def get_item_groups(profile):
    """
    Get item groups for menu tabs/categories.
    Returns flat list with hierarchy info.
    """
    if profile.item_groups and len(profile.item_groups) > 0:
        parent_groups = [ig.item_group for ig in profile.item_groups]

        groups = frappe.get_all(
            "Item Group",
            filters={"name": ["in", parent_groups]},
            fields=["name", "parent_item_group", "image", "lft", "rgt"],
            order_by="lft asc",
        )

        # Also get children one level deep
        for g in parent_groups:
            children = frappe.get_all(
                "Item Group",
                filters={"parent_item_group": g},
                fields=["name", "parent_item_group", "image", "lft", "rgt"],
                order_by="lft asc",
            )
            groups.extend(children)

        # Deduplicate
        seen = set()
        unique = []
        for g in groups:
            if g["name"] not in seen:
                seen.add(g["name"])
                unique.append(g)

        return unique

    # Fallback: all groups with items
    return frappe.get_all(
        "Item Group",
        filters={"is_group": 0},
        fields=["name", "parent_item_group", "image"],
        order_by="name asc",
        limit=50,
    )


def get_tax_template(profile):
    """
    Get the Sales Taxes and Charges Template for this POS.
    Returns the template name and its tax rows.
    """
    # POS Profile has taxes_and_charges
    template_name = profile.taxes_and_charges

    if not template_name:
        # Fallback: get default for the company
        template_name = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {"company": profile.company, "is_default": 1},
            "name",
        )

    if not template_name:
        return {"name": None, "taxes": []}

    template = frappe.get_cached_doc("Sales Taxes and Charges Template", template_name)
    taxes = []
    for t in template.taxes:
        taxes.append({
            "charge_type": t.charge_type,
            "account_head": t.account_head,
            "rate": flt(t.rate),
            "description": t.description,
            "included_in_print_rate": cint(t.included_in_print_rate),
            "row_id": t.row_id,
        })

    return {
        "name": template_name,
        "taxes": taxes,
    }


def get_pricing_rules(profile):
    """
    Get active Pricing Rules applicable to this POS.

    ERPNext uses separate child tables per apply_on type:
      - Pricing Rule Item Code  (item_code, uom)
      - Pricing Rule Item Group (item_group)

    We query each separately and merge.
    """
    today = nowdate()
    company = profile.company

    # Only plain price rules the POS can apply by itself: no coupon, no
    # Python condition, no free-item (product) discounts, and for this
    # price list. The server re-checks claimed rules against this same list.
    base_conditions = """
        pr.disable = 0
        AND pr.selling = 1
        AND (pr.company IN (%(company)s, '') OR pr.company IS NULL)
        AND (pr.valid_from IS NULL OR pr.valid_from <= %(today)s)
        AND (pr.valid_upto IS NULL OR pr.valid_upto >= %(today)s)
        AND IFNULL(pr.coupon_code_based, 0) = 0
        AND IFNULL(pr.price_or_product_discount, 'Price') = 'Price'
        AND IFNULL(pr.`condition`, '') = ''
        AND (IFNULL(pr.for_price_list, '') = '' OR pr.for_price_list = %(price_list)s)
    """
    from renpos.api.guards import effective_price_list
    params = {"company": company, "today": today, "price_list": effective_price_list(profile.name)}

    result = []

    # ── Rules by Item Code ────────────────────────
    item_rules = frappe.db.sql(
        """
        SELECT
            pr.name, pr.min_qty, pr.max_qty,
            pr.discount_percentage, pr.discount_amount,
            pr.rate_or_discount, pr.rate, pr.priority,
            pri.item_code
        FROM `tabPricing Rule` pr
        INNER JOIN `tabPricing Rule Item Code` pri
            ON pri.parent = pr.name AND pri.parenttype = 'Pricing Rule'
        WHERE {conditions}
          AND pr.apply_on = 'Item Code'
        ORDER BY pr.priority ASC
        """.format(conditions=base_conditions),
        params,
        as_dict=True,
    )

    for r in item_rules:
        result.append(_format_pricing_rule(r, item_code=r.item_code))

    # ── Rules by Item Group ───────────────────────
    group_rules = frappe.db.sql(
        """
        SELECT
            pr.name, pr.min_qty, pr.max_qty,
            pr.discount_percentage, pr.discount_amount,
            pr.rate_or_discount, pr.rate, pr.priority,
            prig.item_group
        FROM `tabPricing Rule` pr
        INNER JOIN `tabPricing Rule Item Group` prig
            ON prig.parent = pr.name AND prig.parenttype = 'Pricing Rule'
        WHERE {conditions}
          AND pr.apply_on = 'Item Group'
        ORDER BY pr.priority ASC
        """.format(conditions=base_conditions),
        params,
        as_dict=True,
    )

    for r in group_rules:
        result.append(_format_pricing_rule(r, item_group=r.item_group))

    return result


def _format_pricing_rule(r, item_code=None, item_group=None):
    """Format a pricing rule row for the client."""
    return {
        "name": r.name,
        "item_code": item_code,
        "item_group": item_group,
        "min_qty": flt(r.min_qty),
        "max_qty": flt(r.max_qty),
        "discount_percentage": flt(r.discount_percentage) if r.rate_or_discount == "Discount Percentage" else 0,
        "discount_amount": flt(r.discount_amount) if r.rate_or_discount == "Discount Amount" else 0,
        "rate": flt(r.rate) if r.rate_or_discount == "Rate" else 0,
        "priority": cint(r.priority),
    }


def _access(pos_profile):
    from renpos.api.access import role_of, has_pin
    return {**role_of(pos_profile=pos_profile), "has_pin": has_pin()}
