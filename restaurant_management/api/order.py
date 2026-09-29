# -*- coding: utf-8 -*-
# restaurant_management/api/order.py
#
# Order management API endpoints.
# Called by React OrderManager via api.js
#
# Key principle: client calculates, server validates and persists.

from __future__ import unicode_literals
import json
import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, nowdate
from restaurant_management.api.pos import get_item_tax_rate, get_pricing_rules
from restaurant_management.api.guards import (
    require_restaurant_user,
    check_pos_profile_access,
    get_order,
    user_pos_permissions,
    is_manager,
)
from restaurant_management.api.invoicing import create_invoice

EDITABLE_STATUSES = ("Pending", "Attending", "", None)

try:
    from frappe.realtime import get_doctype_room
    _ORDER_ROOM = get_doctype_room("Table Order")
except ImportError:
    _ORDER_ROOM = "doctype:Table Order"


# ═══════════════════════════════════════════════════
# ORDERS — CRUD
# ═══════════════════════════════════════════════════

@frappe.whitelist()
def get_orders(table_name, customer=None):
    """
    Get all active orders for a table.
    Legacy: Ren Table.orders_list
    """
    require_restaurant_user()
    if not frappe.has_permission("Table Order", "read"):
        raise frappe.PermissionError(_("Not permitted to read orders"))

    filters = {
        "table": table_name,
        "status": ["not in", ["Invoiced", "Cancelled"]],
    }

    if customer:
        filters["customer"] = customer

    orders = frappe.get_all(
        "Table Order",
        filters=filters,
        fields=[
            "name", "customer", "customer_name", "status",
            "dinners", "amount", "tax", "table",
            "creation", "owner", "show_in_pos",
            "is_delivery", "delivery_branch", "charge_amount",
        ],
        order_by="creation asc",
    )

    # Determine which order to auto-select
    current_order = None
    if orders:
        current_order = orders[-1].name

    return {
        "orders": [{"data": o} for o in orders],
        "order": current_order,
    }


@frappe.whitelist()
def add_order(table_name):
    """
    Create a new Table Order for a table.
    Legacy: Ren Table.add_order
    """
    require_restaurant_user()
    if not frappe.has_permission("Table Order", "create"):
        raise frappe.PermissionError(_("Not permitted to create orders"))

    table = frappe.get_doc("Ren Table", table_name)
    table.check_permission("read")

    # Get POS Profile from table's room/floor or default
    pos_profile = _get_pos_profile_for_table(table)
    check_pos_profile_access(pos_profile)

    order = frappe.get_doc({
        "doctype": "Table Order",
        "table": table_name,
        "pos_profile": pos_profile,
        "status": "Draft",
        "attending_status": "Pending",
    })

    order.insert(ignore_permissions=True)

    _publish_order_event(table_name, order.name, "Add", data={"order": _order_dict(order)})
    return {
        "order": {"data": _order_dict(order)},
        "items": [],
    }

@frappe.whitelist()
def delete_order(order_name):
    """
    Delete a Table Order (only if no sent items).
    Legacy: Table Order._delete
    """
    order = get_order(order_name, "write")

    # Check if any items have been sent to kitchen
    sent_items = frappe.db.count(
        "Order Entry Item",
        filters={
            "parent": order_name,
            "status": ["not in", ["Pending", "", None]],
        },
    )

    if sent_items > 0:
        frappe.throw(_("Cannot delete: {0} items already sent to kitchen").format(sent_items))

    # Notify table
    table_name = order.table
    order.delete(ignore_permissions=True)

    _publish_order_event(table_name, order_name, "Delete", data={"name": order_name})

    return {"ok": True}


@frappe.whitelist()
def get_items(order_name):
    """
    Get all items for an order.
    Legacy: Table Order.get_items
    """
    order = get_order(order_name, "read")
    items = _get_order_items(order_name)

    return {
        "order": {"data": _order_dict(order)},
        "items": items,
    }


# ═══════════════════════════════════════════════════
# ITEMS — Add / Update / Delete
# ═══════════════════════════════════════════════════

@frappe.whitelist()
def push_item(order_name, item):
    """
    Add or update an item in an order.
    Legacy: Table Order.push_item

    The client sends an ALREADY-CALCULATED item.
    Server validates the calculation, then persists.
    """
    if isinstance(item, str):
        item = json.loads(item)

    order = get_order(order_name, "write")
    _check_order_open(order)
    identifier = item.get("identifier")
    if not identifier:
        frappe.throw(_("Item identifier is required"))

    # ── Check if item exists (update) or is new ──
    existing = None
    for child in order.entry_items:
        if child.identifier == identifier:
            existing = child
            break

    if existing and existing.status not in EDITABLE_STATUSES:
        frappe.throw(_("Item {0} was already sent and can't be changed").format(existing.item_name))

    if existing and item.get("item_code") != existing.item_code:
        frappe.throw(_("Item code can't be changed"))

    # ── Validate client calculation (server is the source of truth) ──
    validated_item = _validate_item_calculation(item, order, existing)

    if existing:
        # Update existing
        existing.qty = flt(validated_item["qty"])
        existing.rate = flt(validated_item["rate"])
        existing.price_list_rate = flt(validated_item["price_list_rate"])
        existing.discount_percentage = flt(validated_item["discount_percentage"])
        existing.amount = flt(validated_item["amount"])
        existing.tax_amount = flt(validated_item.get("tax_amount", 0))
        existing.notes = validated_item.get("notes", "")
        existing.item_tax_rate = validated_item["item_tax_rate"]
        # status is server-controlled: an editable item stays as it is
        existing.status = existing.status or "Pending"
        existing.batch_no = validated_item.get("batch_no", "")
        existing.serial_no = validated_item.get("serial_no", "")
    else:
        # Add new item
        order.append("entry_items", {
            "identifier": identifier,
            "item_code": validated_item["item_code"],
            "item_name": validated_item["item_name"],
            "qty": flt(validated_item["qty"]),
            "rate": flt(validated_item["rate"]),
            "price_list_rate": flt(validated_item["price_list_rate"]),
            "discount_percentage": flt(validated_item["discount_percentage"]),
            "amount": flt(validated_item["amount"]),
            "tax_amount": flt(validated_item.get("tax_amount", 0)),
            "item_tax_rate": validated_item["item_tax_rate"],
            "notes": validated_item.get("notes", ""),
            "status": "Pending",
            "batch_no": validated_item.get("batch_no", ""),
            "serial_no": validated_item.get("serial_no", ""),
        })

    # Recalculate order totals
    _aggregate_order(order)
    order.save(ignore_permissions=True)

    _publish_order_event(order.table, order_name, "update")

    return {
        "item": validated_item,
        "order": {"data": _order_dict(order)},
    }


@frappe.whitelist()
def delete_item(order_name, identifier):
    """
    Delete an item from an order.
    Legacy: Table Order.delete_item
    """
    order = get_order(order_name, "write")
    _check_order_open(order)

    to_remove = None
    for child in order.entry_items:
        if child.identifier == identifier:
            to_remove = child
            break

    if not to_remove:
        frappe.throw(_("Item not found"))

    # Pending items: anyone. Items already sent to the kitchen: managers only.
    # Anything further along (processing, delivered…) can't be deleted.
    if to_remove.status not in EDITABLE_STATUSES:
        if to_remove.status != "Sent":
            frappe.throw(_("Cannot delete item with status: {0}").format(to_remove.status))
        if not is_manager():
            raise frappe.PermissionError(
                _("Only a Restaurant Manager can remove items already sent to the kitchen")
            )

    order.remove(to_remove)
    _aggregate_order(order)
    order.save(ignore_permissions=True)

    _publish_order_event(order.table, order_name, "update")

    return {
        "ok": True,
        "order": {"data": _order_dict(order)},
    }


# ═══════════════════════════════════════════════════
# ORDER ACTIONS
# ═══════════════════════════════════════════════════

@frappe.whitelist()
def send_order(order_name):
    """
    Send pending items to kitchen.
    Legacy: Table Order.send

    Marks all "Pending" items as "Sent" and publishes
    realtime event for KDS.
    """
    order = get_order(order_name, "write")
    _check_order_open(order)
    sent_count = 0
    sent_items = []
    sent_at = now_datetime()

    for item in order.entry_items:
        if item.status in EDITABLE_STATUSES and flt(item.qty) > 0:
            item.status = "Sent"
            item.ordered_time = sent_at
            sent_items.append(item)
            sent_count += 1

    if sent_count == 0:
        frappe.throw(_("No pending items to send"))

    order.products_not_ordered = 0
    order.save(ignore_permissions=True)

    # Publish to kitchen displays
    frappe.publish_realtime(
        "kitchen_order",
        {
            "order": order_name,
            "table": order.table,
            "items": [
                {
                    "item_code": i.item_code,
                    "item_name": i.item_name,
                    "qty": i.qty,
                    "notes": i.notes,
                    "identifier": i.identifier,
                }
                for i in sent_items
            ],
        },
        room=_ORDER_ROOM,
        after_commit=True,
    )

    _publish_order_event(order.table, order_name, "update")

    items = _get_order_items(order_name)
    return {
        "order": {"data": _order_dict(order)},
        "items": items,
    }


@frappe.whitelist()
def transfer_order(order_name, target_table):
    """
    Move an order from one table to another.
    Legacy: managed via RM.transfer_order
    """
    order = get_order(order_name, "write")
    _check_order_open(order)
    target = frappe.get_doc("Ren Table", target_table)
    target.check_permission("read")
    old_table = order.table

    order.table = target_table
    order.save(ignore_permissions=True)

    _publish_order_event(old_table, order_name, "transfer")
    _publish_order_event(target_table, order_name, "update")

    return {"ok": True}


@frappe.whitelist()
def divide_order(order_name, items):
    """
    Split items from one order into a new order on the same table.
    Legacy: Table Order.divide
    """
    if isinstance(items, str):
        items = json.loads(items)

    original = get_order(order_name, "write")
    _check_order_open(original)
    if not frappe.has_permission("Table Order", "create"):
        raise frappe.PermissionError(_("Not permitted to create orders"))

    # Create new order on same table
    new_order = frappe.get_doc({
        "doctype": "Table Order",
        "table": original.table,
        "customer": original.customer,
        "pos_profile": original.pos_profile,
        "status": "Draft",
    })

    for identifier, split_data in items.items():
        # Find the original item
        for child in original.entry_items:
            if child.identifier == identifier:
                split_qty = flt(split_data.get("qty", 0))

                if split_qty <= 0 or split_qty > child.qty:
                    continue

                # Reduce qty in original
                child.qty -= split_qty
                _recalculate_row(child, original)

                # Add to new order
                new_order.append("entry_items", {
                    "identifier": split_data.get("identifier", f"split_{identifier}"),
                    "item_code": child.item_code,
                    "item_name": child.item_name,
                    "qty": split_qty,
                    "rate": child.rate,
                    "price_list_rate": child.price_list_rate,
                    "discount_percentage": child.discount_percentage,
                    "amount": 0,  # recalculated below
                    "tax_amount": 0,
                    "item_tax_rate": child.item_tax_rate,
                    "notes": child.notes,
                    "status": child.status,
                })
                break

    # Remove zero-qty items from original
    original.entry_items = [i for i in original.entry_items if flt(i.qty) > 0]

    _aggregate_order(original)
    original.save(ignore_permissions=True)

    for row in new_order.entry_items:
        _recalculate_row(row, original)
    _aggregate_order(new_order)
    new_order.insert(ignore_permissions=True)

    _publish_order_event(original.table, order_name, "split")

    return {
        "original_order": {"data": _order_dict(original)},
        "new_order": {"data": _order_dict(new_order)},
    }


# ═══════════════════════════════════════════════════
# CUSTOMER & DINNERS
# ═══════════════════════════════════════════════════

@frappe.whitelist()
def set_customer(order_name, customer):
    """Set customer on an order."""
    order = get_order(order_name, "write")
    _check_order_open(order)
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} not found").format(customer))
    order.customer = customer

    # Fetch customer name
    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    order.customer_name = customer_name

    order.save(ignore_permissions=True)

    # Also update the table
    if order.table:
        frappe.db.set_value("Ren Table", order.table, "customer", customer)

    return {
        "ok": True,
        "customer": customer,
        "customer_name": customer_name,
    }


@frappe.whitelist()
def set_dinners(order_name, dinners):
    """Set party size on an order."""
    order = get_order(order_name, "write")
    order.dinners = max(0, cint(dinners))
    order.save(ignore_permissions=True)

    return {"ok": True}


# ═══════════════════════════════════════════════════
# PAYMENT
# ═══════════════════════════════════════════════════

@frappe.whitelist()
def process_payment(order_name, payments):
    """
    Charge an order: create and submit the POS invoice (POS Invoice or,
    on ERPNext v16 when configured, Sales Invoice), mark the order as
    Invoiced and free the table. Requires an open POS Opening Entry.
    """
    if isinstance(payments, str):
        payments = json.loads(payments)

    require_restaurant_user()
    # Lock the order row first so two terminals can't charge it twice and
    # no item can be added between loading and invoicing.
    frappe.db.get_value("Table Order", order_name, "status", for_update=True)
    order = get_order(order_name, "write")
    if order.status == "Invoiced" or order.link_invoice:
        frappe.throw(_("Order already invoiced"))
    _check_order_open(order)

    invoice = create_invoice(order, payments)

    order.status = "Invoiced"
    order.link_invoice = invoice.name
    order.save(ignore_permissions=True)

    _check_and_free_table(order.table)
    _publish_order_event(order.table, order_name, "invoiced")

    return {
        "invoice": invoice.name,
        "invoice_doctype": invoice.doctype,
        "status": "Invoiced",
        "grand_total": invoice.grand_total,
        "rounded_total": invoice.rounded_total,
        "change_amount": invoice.get("change_amount") or 0,
    }


# ═══════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════

def _check_order_open(order):
    if order.status in ("Invoiced", "Cancelled", "Closed") or order.link_invoice:
        frappe.throw(_("Order {0} is closed").format(order.name))


def _server_price(item_code, price_list):
    """Selling price from the price list, same rules as api.pos catalog."""
    today = nowdate()
    rows = frappe.db.sql(
        """
        SELECT price_list_rate FROM `tabItem Price`
        WHERE item_code = %(item_code)s AND price_list = %(price_list)s AND selling = 1
          AND (valid_from IS NULL OR valid_from <= %(today)s)
          AND (valid_upto IS NULL OR valid_upto >= %(today)s)
          AND IFNULL(customer, '') = ''
          AND IFNULL(batch_no, '') = ''
        ORDER BY (IFNULL(uom, '') = '' OR uom = %(stock_uom)s) DESC, valid_from DESC
        LIMIT 1
        """,
        {"item_code": item_code, "price_list": price_list, "today": today,
         "stock_uom": frappe.db.get_value("Item", item_code, "stock_uom") or ""},
    )
    return flt(rows[0][0]) if rows else None


def _server_item_tax_rate(item_code, company, tax_category=None):
    """
    item_tax_rate JSON. Looks at the Item, then up its Item Group tree,
    like ERPNext does when it builds the invoice.
    """
    today = nowdate()

    def template_for(parent, parenttype):
        rows = frappe.db.sql(
            """
            SELECT itax.item_tax_template FROM `tabItem Tax` itax
            INNER JOIN `tabItem Tax Template` itt ON itt.name = itax.item_tax_template
            WHERE itax.parent = %(parent)s AND itax.parenttype = %(parenttype)s
              AND IFNULL(itax.tax_category, '') IN ('', %(tax_category)s)
              AND (itax.valid_from IS NULL OR itax.valid_from <= %(today)s)
              AND itt.company = %(company)s
              AND IFNULL(itt.disabled, 0) = 0
            ORDER BY (IFNULL(itax.tax_category, '') = %(tax_category)s) DESC, itax.valid_from DESC
            LIMIT 1
            """,
            {"parent": parent, "parenttype": parenttype, "today": today,
             "company": company, "tax_category": tax_category or ""},
        )
        return rows[0][0] if rows else None

    template = template_for(item_code, "Item")
    group = frappe.db.get_value("Item", item_code, "item_group")
    while not template and group:
        template = template_for(group, "Item Group")
        group = frappe.db.get_value("Item Group", group, "parent_item_group")

    return get_item_tax_rate(template, company)


def _tax_inclusive(order):
    profile = frappe.get_cached_doc("POS Profile", order.pos_profile)
    return cint(getattr(profile, "posa_tax_inclusive", 0))


def _row_amounts(qty, rate, item_tax_rate, tax_inclusive):
    """Mirror of calculator.js calculateItem: returns (tax_amount, amount)."""
    base = flt(qty) * flt(rate)
    try:
        rates = json.loads(item_tax_rate or "{}")
    except (ValueError, TypeError):
        rates = {}
    total_rate = sum(flt(r) for r in rates.values())
    if tax_inclusive:
        # the price already contains all taxes: net = base / (1 + Σr)
        tax = base - base / (1 + total_rate / 100)
    else:
        tax = base * total_rate / 100
    tax = flt(tax, 2)
    amount = flt(base, 2) if tax_inclusive else flt(base + tax, 2)
    return tax, amount


def _recalculate_row(row, order):
    row.tax_amount, row.amount = _row_amounts(
        row.qty, row.rate, row.item_tax_rate, _tax_inclusive(order)
    )


def _in_item_group(item_group, rule_group):
    """True if item_group is rule_group or one of its descendants."""
    if not item_group or not rule_group:
        return False
    if item_group == rule_group:
        return True
    a = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=True)
    b = frappe.db.get_value("Item Group", rule_group, ["lft", "rgt"], as_dict=True)
    return bool(a and b and b.lft <= a.lft and a.rgt <= b.rgt)


def _find_pricing_rule(name, item_code, item_group, qty, profile, customer=None):
    """
    Return the client-claimed pricing rule only if it really applies:
    same rule list the POS catalog uses (Item Code / Item Group rules,
    active, dated, company), matching item or group tree, qty range and
    "Applicable For" (only none or this Customer).
    """
    if not name:
        return None

    applicable_for, rule_customer = frappe.db.get_value(
        "Pricing Rule", name, ["applicable_for", "customer"]
    ) or (None, None)
    if applicable_for and not (applicable_for == "Customer" and rule_customer == customer):
        return None

    for r in get_pricing_rules(profile):
        if r["name"] != name:
            continue
        if r.get("item_code"):
            if r["item_code"] != item_code:
                continue
        elif r.get("item_group"):
            if not _in_item_group(item_group, r["item_group"]):
                continue
        else:
            continue  # rules not scoped to an item or group are not accepted
        if flt(r.get("min_qty")) and flt(qty) < flt(r["min_qty"]):
            continue
        if flt(r.get("max_qty")) and flt(qty) > flt(r["max_qty"]):
            continue
        return r
    return None


def _validate_item_calculation(item, order, existing=None):
    """
    Recompute the item on the server. The client's numbers are only
    accepted where the user is allowed to change them:

      price_list_rate  <- Item Price of the POS price list (or a valid
                          "Rate" pricing rule); client value only when the
                          item has no price and rate change is allowed.
      discount / rate  <- a valid pricing rule, or the client's value when
                          the POS Profile allows discount / rate change.
      tax, amount      <- always recomputed.
    """
    item_code = item.get("item_code")
    if not item_code:
        frappe.throw(_("Item code is required"))

    item_doc = frappe.db.get_value(
        "Item", item_code,
        ["item_name", "item_group", "disabled", "is_sales_item", "has_variants"],
        as_dict=True,
    )
    if not item_doc or item_doc.disabled or not item_doc.is_sales_item or item_doc.has_variants:
        frappe.throw(_("Item {0} can't be sold").format(item_code))

    qty = flt(item.get("qty"))
    if qty < 0:
        frappe.throw(_("Quantity can't be negative"))

    profile = frappe.get_cached_doc("POS Profile", order.pos_profile)
    perms = user_pos_permissions(order.pos_profile)

    client_plr = flt(item.get("price_list_rate"))
    server_price = _server_price(item_code, profile.selling_price_list)
    rule = _find_pricing_rule(
        item.get("pricing_rule"), item_code, item_doc.item_group, qty, profile, order.customer
    )

    if rule and flt(rule.get("rate")):
        price_list_rate = flt(rule["rate"])
    elif server_price is not None:
        price_list_rate = server_price
    elif perms["allow_rate_change"]:
        price_list_rate = client_plr
    elif existing is not None:
        price_list_rate = flt(existing.price_list_rate)  # set earlier by an authorised user
    else:
        price_list_rate = 0

    if abs(price_list_rate - client_plr) > 0.01:
        frappe.log_error(
            title="Restaurant: item price corrected",
            message=f"Order {order.name}, item {item_code}: client sent {client_plr}, server used {price_list_rate}",
        )

    # Discount granted by a pricing rule
    rule_discount = 0
    if rule and price_list_rate:
        if flt(rule.get("discount_percentage")):
            rule_discount = flt(rule["discount_percentage"])
        elif flt(rule.get("discount_amount")):
            rule_discount = flt(rule["discount_amount"]) / price_list_rate * 100
    rule_discount = min(max(rule_discount, 0), 100)

    client_discount = min(max(flt(item.get("discount_percentage")), 0), 100)
    client_rate = max(flt(item.get("rate")), 0)

    if perms["allow_rate_change"]:
        rate = client_rate
        discount = ((price_list_rate - rate) / price_list_rate * 100) if price_list_rate else 0
        discount = min(max(discount, 0), 100)
    elif perms["allow_discount_change"]:
        discount = client_discount
        rate = price_list_rate * (1 - discount / 100)
    elif existing is not None and abs(client_discount - flt(existing.discount_percentage)) < 0.01 \
            and abs(price_list_rate - flt(existing.price_list_rate)) < 0.01 \
            and qty >= flt(existing.qty):
        # Unchanged discount on an existing row (e.g. given by a manager):
        # a user without discount rights may still add qty or edit notes.
        # Lowering qty drops it (a min-qty rule may no longer apply).
        discount = flt(existing.discount_percentage)
        rate = price_list_rate * (1 - discount / 100)
    else:
        discount = rule_discount
        rate = price_list_rate * (1 - discount / 100)

    item_tax_rate = _server_item_tax_rate(item_code, profile.company, profile.get("tax_category"))
    tax_amount, amount = _row_amounts(qty, rate, item_tax_rate, _tax_inclusive(order))

    return {
        **item,
        "item_name": item_doc.item_name,
        "qty": qty,
        "price_list_rate": flt(price_list_rate, 2),
        "discount_percentage": flt(discount, 4),
        "rate": flt(rate, 2),
        "item_tax_rate": item_tax_rate,
        "tax_amount": tax_amount,
        "amount": amount,
        "pricing_rule": rule["name"] if rule else None,
    }


def _aggregate_order(order):
    """Recalculate order totals from items."""
    total_amount = 0
    total_tax = 0
    items_count = 0
    products_not_ordered = 0

    for item in order.entry_items:
        if flt(item.qty) <= 0:
            continue
        total_amount += flt(item.amount)
        total_tax += flt(item.tax_amount) if hasattr(item, "tax_amount") else 0
        items_count += 1

        if item.status in ("Pending", "Attending", "", None):
            products_not_ordered += 1

    order.amount = total_amount
    order.tax = total_tax
    #$order.items_count = items_count
    order.products_not_ordered = products_not_ordered


def _get_order_items(order_name):
    """Get items for an order as a list of dicts."""
    items = frappe.get_all(
        "Order Entry Item",
        filters={"parent": order_name},
        fields=[
            "name as entry_name", "identifier", "item_code", "item_name",
            "qty", "rate", "price_list_rate", "discount_percentage",
            "amount", "tax_amount", "item_tax_rate",
            "status", "notes", "batch_no", "serial_no",
            "has_batch_no", "has_serial_no",
            #"process_status_data",
        ],
        order_by="idx asc",
    )

    # Parse process_status_data
    for item in items:
        if isinstance(item.get("process_status_data"), str):
            try:
                item["process_status_data"] = json.loads(item["process_status_data"])
            except (json.JSONDecodeError, TypeError):
                item["process_status_data"] = {"icon": "fa fa-circle", "color": "gray"}
        elif not item.get("process_status_data"):
            item["process_status_data"] = {"icon": "fa fa-circle", "color": "gray"}

    return items


def _order_dict(order):
    """Convert order doc to dict for JSON response."""
    return {
        "name": order.name,
        "customer": order.customer,
        "customer_name": getattr(order, "customer_name", ""),
        "status": order.status,
        "dinners": cint(order.dinners) if hasattr(order, "dinners") else 0,
        "amount": flt(order.amount) if hasattr(order, "amount") else 0,
        "tax": flt(order.tax) if hasattr(order, "tax") else 0,
        "table": order.table,
        "show_in_pos": cint(getattr(order, "show_in_pos", 1)),
        "products_not_ordered": cint(getattr(order, "products_not_ordered", 0)),
        "items_count": cint(getattr(order, "items_count", 0)),
        "attending_status": getattr(order, "attending_status", "Pending"),
        "short_name": getattr(order, "short_name", order.name[-5:]),
        "is_delivery": cint(getattr(order, "is_delivery", 0)),
        "delivery_branch": cint(getattr(order, "delivery_branch", 0)),
        "charge_amount": flt(getattr(order, "charge_amount", 0)),
        "sales_invoice": getattr(order, "sales_invoice", ""),
        "pos_profile": order.pos_profile,
    }


def _get_pos_profile_for_table(table_doc):
    """
    Determine which POS Profile to use for a table.
    Priority: Restaurant Permission > default POS Profile.
    """
    user = frappe.session.user

    # Check Restaurant Permission for this user
    """ if frappe.db.exists("DocType", "Restaurant Permission Manage"):
        pos = frappe.db.get_value(
            "Restaurant Permission Manage",
            {"user": user},
            "pos_profile",
        )
        if pos:
            return pos """

    # Fallback: user's default POS Profile
    pos = frappe.db.get_value(
        "POS Profile User",
        {"user": user, "default": 1},
        "parent",
    )
    if pos:
        return pos

    # Last fallback: any active POS Profile for the company
    company = frappe.db.get_value("Ren Table", table_doc.name, "company")
    if not company:
        # Try to get company from the floor
        room = table_doc.room if hasattr(table_doc, "room") else None
        if room:
            floor = frappe.db.get_value("Ren Room", room, "room")
            if floor:
                company = frappe.db.get_value("Ren Floor", floor, "company")

    if company:
        pos = frappe.db.get_value(
            "POS Profile",
            {"company": company, "disabled": 0},
            "name",
        )
        if pos:
            return pos

    frappe.throw(_("No POS Profile found. Please configure one for this user."))


def _check_and_free_table(table_name):
    """Free table if no more active orders."""
    active = frappe.db.get_count(
        "Table Order",
        filters={
            "table": table_name,
            "status": ["not in", ["Invoiced", "Cancelled"]],
        },
    )

    if active == 0:
        frappe.db.set_value("Ren Table", table_name, "customer", "")
        table = frappe.get_doc("Ren Table", table_name)
        if hasattr(table, "_on_update"):
            table._on_update()


def _publish_order_event(table, order_name, action, data=None):
    """
    Notify every terminal showing this table. `client_id` identifies the
    browser tab that made the change (sent by the React API wrapper), so
    that tab can ignore its own echo while other tabs, even with the same
    user, still refresh.
    """
    frappe.publish_realtime(
        "order_update",
        {
            "table": table,
            "order": order_name,
            "action": (action or "").lower(),
            "source": frappe.session.user,
            "client_id": frappe.form_dict.get("client_id"),
            **(data or {}),
        },
        # only sockets subscribed to Table Order (they need read permission)
        room=_ORDER_ROOM,
        after_commit=True,
    )