# -*- coding: utf-8 -*-
# restaurant_management/api/pos.py
#
# Pre-load all POS data for client-side calculations.
# Called ONCE when OrderManager opens.

from __future__ import unicode_literals
import frappe
import json
from frappe import _
from frappe.utils import cint, flt, nowdate


@frappe.whitelist()
def get_pos_data(pos_profile):
    """
    Returns everything the React OrderManager needs to work
    without further server calls for calculations.

    Single endpoint replaces ~5 separate calls the legacy system made.
    """
    from restaurant_management.api.guards import (
        require_restaurant_user, check_pos_profile_access, user_pos_permissions,
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
        "tax_inclusive": cint(getattr(profile, "posa_tax_inclusive", 0)),
        # same flags the server enforces in api.order._validate_item_calculation
        "allow_discount_change": user_perms["allow_discount_change"],
        "allow_rate_change": user_perms["allow_rate_change"],
        "is_manager": user_perms["is_manager"],
        "price_list": profile.selling_price_list,
        "warehouse": profile.warehouse,
        "write_off_account": profile.write_off_account,
        "write_off_cost_center": profile.write_off_cost_center,
    }

    # ─── Items with prices ────────────────────────
    items = get_items_with_prices(profile)

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

    # ─── Permissions ──────────────────────────────
    permissions = []# get_user_permissions(profile)

    return {
        **config,
        "items": items,
        "item_groups": item_groups,
        "taxes": taxes,
        "pricing_rules": pricing_rules,
        "payments": payments,
        "permissions": permissions,
    }


def get_items_with_prices(profile):
    """
    Get all items visible in this POS profile, with their
    price_list_rate and item_tax_rate pre-resolved.

    This is the payload that enables client-side price lookups.
    """
    price_list = profile.selling_price_list

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
        "i.has_variants = 0",
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

    base_conditions = """
        pr.disable = 0
        AND pr.selling = 1
        AND (pr.company IN (%(company)s, '') OR pr.company IS NULL)
        AND (pr.valid_from IS NULL OR pr.valid_from <= %(today)s)
        AND (pr.valid_upto IS NULL OR pr.valid_upto >= %(today)s)
    """
    params = {"company": company, "today": today}

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


def get_user_permissions(profile):
    """
    Check what the current user can do in this POS.
    Uses the existing Restaurant Permission system.
    """
    user = frappe.session.user

    # Basic POS Profile permissions
    permissions = {
        "allow_discount_change": cint(profile.allow_discount_change),
        "allow_rate_change": cint(profile.allow_rate_change),
        "can_delete_items": True,
        "can_create_orders": True,
        "can_transfer_orders": True,
        "can_print": True,
    }

    # Check Restaurant Manager role
    is_manager = "Restaurant Manager" in frappe.get_roles(user)
    permissions["is_manager"] = is_manager

    # If there's a restaurant permission system, check it
    if frappe.db.exists("DocType", "Restaurant Permission"):
        perm = frappe.db.get_value(
            "Restaurant Permission",
            {"user": user, "pos_profile": profile.name},
            ["can_delete", "can_discount", "can_rate_change", "can_transfer"],
            as_dict=True,
        )

        if perm:
            permissions["can_delete_items"] = cint(perm.get("can_delete", 1)) or is_manager
            permissions["allow_discount_change"] = (
                cint(profile.allow_discount_change)
                and (cint(perm.get("can_discount", 1)) or is_manager)
            )
            permissions["allow_rate_change"] = (
                cint(profile.allow_rate_change)
                and (cint(perm.get("can_rate_change", 1)) or is_manager)
            )
            permissions["can_transfer_orders"] = cint(perm.get("can_transfer", 1)) or is_manager

    return permissions