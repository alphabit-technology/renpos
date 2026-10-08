# -*- coding: utf-8 -*-
# renpos/api/order.py
#
# Order management API endpoints.
# Called by React OrderManager via api.js
#
# Key principle: client calculates, server validates and persists.

import json
import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, nowdate
from renpos.api.pos import get_item_tax_rate, get_pricing_rules
from renpos.api.guards import (
    require_restaurant_user,
    check_pos_profile_access,
    get_order,
)
from renpos.api.invoicing import (
    create_invoice,
    build_invoice_preview,
    can_take_payments,
    amount_due,
    opening_status,
    payment_modes,
    get_invoice_doctype,
)

from renpos.api.statuses import is_editable
from renpos.api import access

try:
    from frappe.realtime import get_doctype_room
    _ORDER_ROOM = get_doctype_room("Ren Order")
except ImportError:
    _ORDER_ROOM = "doctype:Ren Order"


# ═══════════════════════════════════════════════════
# ORDERS — CRUD
# ═══════════════════════════════════════════════════

@frappe.whitelist()
def get_orders(table_name, customer=None):
    """
    Get all active orders for a table.
    """
    require_restaurant_user()
    access.check_table_access(table_name)

    filters = {
        "table": table_name,
        "status": ["not in", ["Invoiced", "Cancelled"]],
    }

    if customer and customer not in ("null", "undefined"):
        filters["customer"] = customer

    orders = frappe.get_all(
        "Ren Order",
        filters=filters,
        fields=[
            "name", "customer", "customer_name", "status",
            "dinners", "amount", "tax", "table",
            "creation", "owner", "show_in_pos",
            "ren_delivery", "ren_delivery_address", "ren_delivery_zip", "ren_delivery_zone", "ren_delivery_fee",
            "ren_delivery_minimum", "ren_deliver_by", "ren_guest_phone", "ren_driver_name", "ren_dispatched_at",
            "ren_delivered_at",
            "ren_origin", "ren_guest_name", "ren_pickup_time",
        ],
        order_by="creation asc",
    )

    # people without "see other people's orders" only get their own
    if not access.can("view_others_orders"):
        orders = [o for o in orders if o.owner in (frappe.session.user, access.GUEST_OWNER)]

    counts = _line_counts([o.name for o in orders])
    for o in orders:
        o.update(counts.get(o.name, {"items_count": 0, "pending_count": 0}))

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
    Create a new Ren Order for a table.
    """
    require_restaurant_user()
    access.check_table_access(table_name)
    from renpos.api.staff import require_clocked_in
    require_clocked_in()
    frappe.flags.ren_order_api = True

    table = frappe.get_doc("Ren Table", table_name)

    # Get POS Profile from table's room/floor or default
    pos_profile = _get_pos_profile_for_table(table)
    check_pos_profile_access(pos_profile)
    access.check_new_order_on_table(table_name, pos_profile)
    ensure_table_company(table_name, fallback=frappe.db.get_value("POS Profile", pos_profile, "company"))

    order = frappe.get_doc({
        "doctype": "Ren Order",
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

def _print_voids(order, rows, reason, note):
    """VOID tickets for the production centers (a printer problem never blocks the void)."""
    try:
        from renpos.api.printing import print_void_tickets
        print_void_tickets(order, rows, reason, note)
    except Exception:
        frappe.log_error(title="Restaurant: void ticket not printed", reference_doctype="Ren Order",
                         reference_name=order.name)


@frappe.whitelist()
def delete_order(order_name, reason=None, note=None):
    """
    Void a Ren Order.
    Orders with nothing sent to the kitchen: anyone who can edit them.
    Orders with sent items: managers only, with a reason; every sent item
    is written to the Ren Void Log.
    """
    from renpos.api import voids

    order = get_order(order_name, "write")
    _check_order_open(order)  # paid/closed orders can't be voided
    from renpos.api.card import order_card_payments
    if order_card_payments(order.name):
        frappe.throw(_("This order has card payments charged or in progress. Finish the payment, "
                       "or refund the card in Stripe first."), title=_("Card payment in progress"))

    sent = [i for i in order.entry_items if not is_editable(i.status) and flt(i.qty) > 0]
    if sent:
        access.require("void_orders", order.pos_profile, reference=("Ren Order", order.name),
                        amount=sum(flt(r.amount) for r in sent))
        reason, note = voids.check_reason(reason, note)
        for row in sent:
            voids.log(order, row, reason, note, void_type="Order")
        _print_voids(order, sent, reason, note)

    # Notify table
    table_name = order.table
    order.delete(ignore_permissions=True)

    _check_and_free_table(table_name)
    _publish_order_event(table_name, order_name, "Delete", data={"name": order_name})

    return {"ok": True}


@frappe.whitelist()
def get_items(order_name):
    """
    Get all items for an order.
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

def _parts(validated_item):
    """A combo whose components go to their own production centers (api/parts.py)."""
    from renpos.api.parts import parts_of
    found = parts_of(validated_item["item_code"], validated_item["modifiers"])
    return json.dumps(found) if found else None


@frappe.whitelist()
def push_item(order_name, item):
    """
    Add or update an item in an order.

    The client sends an ALREADY-CALCULATED item.
    Server validates the calculation, then persists.
    """
    if isinstance(item, str):
        item = json.loads(item)

    order = get_order(order_name, "write")
    from renpos.api.staff import require_clocked_in
    require_clocked_in()
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

    if existing and not is_editable(existing.status):
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
        existing.modifiers = json.dumps(validated_item["modifiers"]) if validated_item["modifiers"] else None
        existing.modifiers_amount = flt(validated_item["modifiers_amount"])
        existing.ren_parts = _parts(validated_item)
        existing.ren_hold = cint(item.get("ren_hold"))
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
            "modifiers": json.dumps(validated_item["modifiers"]) if validated_item["modifiers"] else None,
            "modifiers_amount": flt(validated_item["modifiers_amount"]),
            "ren_parts": _parts(validated_item),
            "ren_hold": cint(item.get("ren_hold")),
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
def delete_item(order_name, identifier, reason=None, note=None):
    """
    Delete an item from an order.
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
    if not is_editable(to_remove.status):
        if to_remove.status != "Sent":
            frappe.throw(_("Cannot delete item with status: {0}").format(to_remove.status))
        access.require("void_sent_items", order.pos_profile, reference=("Ren Order", order.name),
                       amount=flt(to_remove.amount), detail=to_remove.item_name)
        from renpos.api import voids
        reason, note = voids.check_reason(reason, note)
        voids.log(order, to_remove, reason, note)
        _print_voids(order, [to_remove], reason, note)

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
def send_order(order_name, fire=0):
    """
    Send pending items to kitchen.

    Marks all "Pending" items as "Sent" and publishes
    realtime event for KDS. Held items (ren_hold: the next course) stay for
    later; fire=1 sends the held ones (and only them).
    """
    order = get_order(order_name, "write")
    _check_order_open(order)
    _send(order, cint(fire))
    items = _get_order_items(order_name)
    return {
        "order": {"data": _order_dict(order)},
        "items": items,
    }


def _send(order, fire=0, only=None):
    """
    Send the order's pending (or, with fire, held) lines to the production
    centers; `only` limits it to those line identifiers. No permission checks.
    """
    order_name = order.name
    sent_count = 0
    sent_items = []
    sent_at = now_datetime()

    for item in order.entry_items:
        if is_editable(item.status) and flt(item.qty) > 0 and bool(cint(item.get("ren_hold"))) == bool(fire) \
                and (only is None or item.identifier in only):
            item.ren_hold = 0
            item.status = "Sent"
            item.ordered_time = sent_at
            item.ren_part_status = None  # every part starts where the line does
            sent_items.append(item)
            sent_count += 1

    if sent_count == 0:
        frappe.throw(_("No held items to fire") if fire else _("No pending items to send"))

    order.products_not_ordered = 0
    # the order shows it has been sent (production centers work on each line's status)
    if order.status in ("Draft", "Opened", "Pending", "Attending", "", None):
        order.status = "Sent"
    order.save(ignore_permissions=True)

    # Kitchen tickets on the stations' printers (a printer problem never blocks the send)
    try:
        from renpos.api.printing import print_kitchen_tickets
        print_kitchen_tickets(order, sent_items, fire=fire)
    except Exception:
        frappe.log_error(title="Restaurant: kitchen ticket not printed", reference_doctype="Ren Order",
                         reference_name=order_name)

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
    return sent_items


@frappe.whitelist()
def transfer_order(order_name, target_table):
    """
    Move an order from one table to another.
    """
    order = get_order(order_name, "write")
    _check_order_open(order)
    access.require("transfer_orders", order.pos_profile, reference=("Ren Order", order.name))
    access.check_table_access(target_table, order.pos_profile)
    target = frappe.get_doc("Ren Table", target_table)
    old_table = order.table
    if target_table == old_table:
        frappe.throw(_("The order is already on table {0}").format(target.description or target_table))
    if _table_restaurant(target_table) != _profile_restaurant(order.pos_profile):
        frappe.throw(_("Table {0} belongs to another restaurant").format(target.description or target_table))

    order_company = order.company or frappe.db.get_value("POS Profile", order.pos_profile, "company")
    ensure_table_company(target_table, fallback=order_company)
    order.table = target_table
    order.save(ignore_permissions=True)
    access.audit("transfer", pos_profile=order.pos_profile, reference=("Ren Order", order.name),
                 detail=f"{old_table} -> {target_table}")

    _check_and_free_table(old_table)
    _publish_order_event(old_table, order_name, "transfer")
    _publish_order_event(target_table, order_name, "update")

    return {"ok": True, "table": target_table}


@frappe.whitelist()
def get_transfer_targets(order_name):
    """
    Tables of the order's restaurant grouped by floor and room, for the
    transfer dialog. The order's current table is marked `current`.
    """
    order = get_order(order_name, "read")
    restaurant = _profile_restaurant(order.pos_profile)

    rows = frappe.db.sql(
        """
        SELECT t.name, t.description, t.no_of_seats, t.customer,
               r.name AS room, r.description AS room_description,
               f.name AS floor, f.description AS floor_description
        FROM `tabRen Table` t
        INNER JOIN `tabRen Room` r ON r.name = t.room
        INNER JOIN `tabRen Floor` f ON f.name = r.floor
        WHERE f.restaurant = %(restaurant)s
        ORDER BY f.description, r.description, t.description
        """,
        {"restaurant": restaurant},
        as_dict=True,
    )
    open_counts = dict(frappe.db.sql(
        """
        SELECT `table`, COUNT(*) FROM `tabRen Order`
        WHERE status NOT IN ('Invoiced', 'Cancelled') AND IFNULL(`table`, '') != ''
        GROUP BY `table`
        """
    ))

    floors = {}
    for r in rows:
        floor = floors.setdefault(r.floor, {"name": r.floor, "description": r.floor_description, "rooms": {}})
        room = floor["rooms"].setdefault(r.room, {"name": r.room, "description": r.room_description, "tables": []})
        room["tables"].append({
            "name": r.name,
            "description": r.description or r.name,
            "no_of_seats": r.no_of_seats,
            "customer": r.customer,
            "orders_count": open_counts.get(r.name, 0),
            "current": r.name == order.table,
        })

    return [
        {**f, "rooms": list(f["rooms"].values())}
        for f in floors.values()
    ]


def ensure_table_company(table, fallback=None):
    """
    Ren Order.company is mandatory and fetched from Ren Table.company,
    which itself is copied down restaurant -> floor -> room -> table.
    Tables created before their floor had a restaurant have it empty:
    resolve it through the chain (or `fallback`) and store it on the table.
    """
    row = frappe.db.sql(
        """
        SELECT t.company, r.company, f.company, rest.company
        FROM `tabRen Table` t
        LEFT JOIN `tabRen Room` r ON r.name = t.room
        LEFT JOIN `tabRen Floor` f ON f.name = r.floor
        LEFT JOIN `tabRen Restaurant` rest ON rest.name = f.restaurant
        WHERE t.name = %s
        """,
        table,
    )
    if not row:
        return fallback
    table_company = row[0][0]
    company = next((c for c in row[0] if c), None) or fallback
    if company and not table_company:
        frappe.db.set_value("Ren Table", table, "company", company, update_modified=False)
    return company


def _profile_restaurant(pos_profile):
    return frappe.db.get_value("POS Profile", pos_profile, "ren_restaurant")


def _table_restaurant(table):
    return frappe.db.sql(
        """
        SELECT f.restaurant FROM `tabRen Table` t
        INNER JOIN `tabRen Room` r ON r.name = t.room
        INNER JOIN `tabRen Floor` f ON f.name = r.floor
        WHERE t.name = %s
        """,
        table,
    )[0][0] if table else None


@frappe.whitelist()
def divide_order(order_name, items):
    """
    Split items from one order into a new order on the same table.
    """
    if isinstance(items, str):
        items = json.loads(items)

    original = get_order(order_name, "write")
    _check_order_open(original)
    access.require("divide_orders", original.pos_profile, reference=("Ren Order", original.name))

    # Create new order on same table
    new_order = frappe.get_doc({
        "doctype": "Ren Order",
        "table": original.table,
        "customer": original.customer,
        "pos_profile": original.pos_profile,
        "status": "Draft",
        "attending_status": "Pending",
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
                    # unique per row, so the same item can be split again later
                    "identifier": f"{identifier}-{frappe.generate_hash(length=6)}",
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
                    "modifiers": child.modifiers,
                    "modifiers_amount": child.modifiers_amount,
                    "ren_parts": child.get("ren_parts"),
                    "ren_part_status": child.get("ren_part_status"),
                    "status": child.status,
                    "ordered_time": child.ordered_time,
                    "batch_no": child.batch_no,
                    "serial_no": child.serial_no,
                })
                break

    if not new_order.entry_items:
        frappe.throw(_("Choose at least one item to move to the new order"))

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
def set_notes(order_name, notes=None):
    """Order note (shown to the kitchen)."""
    order = get_order(order_name, "write")
    order.notes = (notes or "").strip()[:1000]
    order.save(ignore_permissions=True)
    _publish_order_event(order.table, order_name, "update")
    return {"ok": True}


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
def get_payment_summary(order_name, tip=0, loyalty_points=0):
    """
    Everything the payment screen needs, computed by ERPNext exactly as
    the real invoice will be (taxes from the POS Profile, rounding…),
    plus the cashier's register status and the enabled modes of payment.
    Nothing is saved.
    """
    order = get_order(order_name, "read")
    _check_order_open(order)

    from renpos.api.invoicing import billing_profile_for
    billing = billing_profile_for(order)  # the cashier's POS Profile (their register)
    profile = frappe.get_cached_doc("POS Profile", billing)
    if can_take_payments():
        opening, register_problem = opening_status(billing)
    else:
        opening, register_problem = None, "no_permission"
    tip = flt(tip)
    inv = build_invoice_preview(order, tip, cint(loyalty_points))
    from renpos.api.loyalty import info as loyalty_info
    loyalty = loyalty_info(inv.customer, inv.company, inv.flags.bill_total, inv.get("loyalty_amount"))
    if loyalty:
        loyalty.update(used_points=cint(inv.get("loyalty_points")), used_amount=flt(inv.get("loyalty_amount")))
    from renpos.api.loyalty import program_to_join
    loyalty_join = None if loyalty else program_to_join(inv.customer, inv.company, profile.customer)

    from renpos.api.card import order_card_payments

    return {
        "order": order.name,
        "tip": flt(inv.get("ren_tip_amount")) if tip else 0,
        # approved (unused) and in-progress card charges: never lose them
        "card_payments": order_card_payments(order.name),
        "table": order.table,
        "customer": inv.customer,
        "customer_name": inv.customer_name or inv.customer,
        "invoice_doctype": get_invoice_doctype(),
        "currency": inv.currency,
        "precision": inv.precision("grand_total"),
        "items_count": len(inv.items),
        "net_total": inv.net_total,
        "taxes": [
            {"description": t.description, "rate": t.rate, "amount": t.tax_amount}
            for t in inv.get("taxes") or []
        ],
        "total_taxes": inv.total_taxes_and_charges,
        "discount_amount": inv.discount_amount,
        "grand_total": inv.grand_total,
        "rounding_adjustment": inv.rounding_adjustment,
        "amount_due": amount_due(inv),
        "loyalty": loyalty,
        "loyalty_join": loyalty_join,
        "payment_modes": payment_modes(profile),
        "tips": _tips_for_summary(profile, inv),
        "receipt_printer": profile.get("ren_receipt_printer"),
        "card_readers": _card_readers(profile.name),
        "register": {
            "opening_entry": opening.name if opening else None,
            "problem": register_problem,  # None | "closed" | "outdated" | "no_permission"
            "since": opening.period_start_date if opening else None,
            "pos_profile": profile.name,
            "company": profile.company,
        },
    }


@frappe.whitelist()
def process_payment(order_name, payments, tip=0, loyalty_points=0):
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
    frappe.db.get_value("Ren Order", order_name, "status", for_update=True)
    order = get_order(order_name, "write")
    if order.status == "Invoiced" or order.link_invoice:
        frappe.throw(_("Order already invoiced"))
    _check_order_open(order)
    access.require("take_payments", order.pos_profile, reference=("Ren Order", order.name))

    # card rows charged on a Stripe reader must be real, approved and unused
    from renpos.api.card import claim_card_payments, link_card_payments
    card_payments = claim_card_payments(order, payments)

    invoice = create_invoice(order, payments, flt(tip), cint(loyalty_points))
    link_card_payments(card_payments, invoice)

    order.status = "Invoiced"
    order.link_invoice = invoice.name
    order.save(ignore_permissions=True)

    _check_and_free_table(order.table)
    _publish_order_event(order.table, order_name, "invoiced")

    printed = None
    try:
        from renpos.api.printing import after_payment
        printed = after_payment(invoice)
    except Exception:
        frappe.log_error(title="Restaurant: receipt not printed", reference_doctype=invoice.doctype,
                         reference_name=invoice.name)

    return {
        "invoice": invoice.name,
        "invoice_doctype": invoice.doctype,
        "status": "Invoiced",
        "grand_total": invoice.grand_total,
        "rounded_total": invoice.rounded_total,
        "change_amount": invoice.get("change_amount") or 0,
        "tip": flt(invoice.get("ren_tip_amount")),
        "print_job": printed,
        "paid_amount": invoice.paid_amount,
        "currency": invoice.currency,
        "loyalty_points": cint(invoice.get("loyalty_points")),
        "loyalty_amount": flt(invoice.get("loyalty_amount")),
        "points_earned": cint(frappe.db.get_value("Loyalty Point Entry", {"invoice": invoice.name,
                                                                         "loyalty_points": [">", 0]}, "loyalty_points")),
    }


# ═══════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════

def _card_readers(pos_profile):
    from renpos.api.card import readers_for
    return readers_for(pos_profile)


def _tips_for_summary(profile, inv):
    from renpos.api.invoicing import tip_settings
    t = tip_settings(profile)
    return {
        "enabled": t["enabled"],
        "percentages": t["percentages"],
        "on": t["on"],
        "base": flt(inv.net_total if t["on"] == "Subtotal" else (inv.flags.pre_tip_grand_total or inv.grand_total)),
    }


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
    return cint(getattr(profile, "ren_tax_inclusive", 0))


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

    applicable_for, rule_customer, modified_by = frappe.db.get_value(
        "Pricing Rule", name, ["applicable_for", "customer", "modified_by"]
    ) or (None, None, None)
    # only rules set by a manager: staff with ERPNext selling rights can't price their own items
    from renpos.api.access import is_manager_user
    if not modified_by or not is_manager_user(modified_by):
        return None
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


def existing_manual(existing, rule_discount):
    """The line's discount is more than its pricing rule gives (someone set it by hand)."""
    return flt(existing.discount_percentage) > flt(rule_discount) + 0.0001


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

    # a variant (size...) shows as "Coke Large"
    from renpos.api.variants import display_name, template_of
    item_doc.item_name = display_name(item_code, item_doc.item_name)
    template = template_of(item_code)

    from renpos.api.guards import effective_price_list
    from renpos.api import menus
    price_list = effective_price_list(order.pos_profile)

    # Options: validated against the item's sections; their extra price is
    # part of price_list_rate (base price + modifiers_amount).
    from renpos.api import modifiers as ren_modifiers
    modifiers, modifiers_amount = ren_modifiers.resolve(
        item_code, item_doc.item_group, item.get("modifiers"), item_doc.item_name,
        restaurant=order.restaurant or _profile_restaurant(order.pos_profile),
        price_list=price_list,
    )

    profile = frappe.get_cached_doc("POS Profile", order.pos_profile)

    client_plr = flt(item.get("price_list_rate"))
    client_base = max(client_plr - flt(item.get("modifiers_amount")), 0)
    menu = menus.menu_of_order(order)
    if existing is None:
        restaurant = order.restaurant or _profile_restaurant(order.pos_profile)
        sold_out = menus.sold_out_items(restaurant)
        if item_code in sold_out or (template and template in sold_out):
            frappe.throw(_("{0} is sold out").format(frappe.bold(item_doc.item_name or item_code)), title=_("Sold out"))
        if menu and cint(frappe.db.get_single_value("Ren Settings", "only_menu_items")) \
                and not menus.in_menu(menu, item_code) and not (template and menus.in_menu(menu, template)):
            frappe.throw(_("{0} isn't on this table's menu").format(frappe.bold(item_doc.item_name or item_code)))
    if existing is not None and existing.item_code == item_code:
        # a line keeps the price it was rung in at (menu schedules can change meanwhile)
        server_price = flt(existing.price_list_rate) - flt(existing.get("modifiers_amount"))
    else:
        server_price = menus.item_price(item_code, price_list, menu)
    rule = _find_pricing_rule(
        item.get("pricing_rule"), item_code, item_doc.item_group, qty, profile, order.customer
    )

    if ren_modifiers.price_from_components(item_code):
        # built from components: the options chosen are the price
        base_price = 0
    elif rule and flt(rule.get("rate")):
        base_price = flt(rule["rate"])
    elif server_price is not None:
        base_price = server_price
    elif access.can("change_price", order.pos_profile) and client_base > 0:
        base_price = client_base
    elif existing is not None:
        # set earlier by an authorised user
        base_price = flt(existing.price_list_rate) - flt(existing.get("modifiers_amount"))
    else:
        # Never sell at 0 by accident: an item without a price needs a price
        # list entry, or a user allowed to set the rate.
        frappe.throw(
            _("{0} has no price in price list {1}").format(
                frappe.bold(item_doc.item_name or item_code), frappe.bold(price_list)
            ),
            title=_("Missing price"),
        )
    # removing included options can lower the price, never below 0
    price_list_rate = max(flt(base_price) + modifiers_amount, 0)

    if abs(price_list_rate - client_plr) > 0.01 and not frappe.flags.ren_guest_order:
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

    # What the client asks for: a custom rate (price change) or a discount.
    # The person's role decides (Ren Role: change prices, max discount %);
    # beyond it a manager PIN approves (api/access.py). Unchanged values on an
    # existing line are kept, so anyone may add qty or notes to it.
    same_as_before = existing is not None \
        and abs(price_list_rate - flt(existing.price_list_rate)) < 0.01 \
        and abs(client_discount - flt(existing.discount_percentage)) < 0.01 \
        and abs(client_rate - flt(existing.rate)) < 0.01
    ref = ("Ren Order", order.name)
    # a custom rate is one the client set on purpose: inconsistent with its own
    # price and discount (a stale or tampered price alone is just corrected)
    custom_rate = bool(price_list_rate) and client_rate > 0 and client_plr > 0 \
        and abs(client_rate - client_plr * (1 - client_discount / 100)) > 0.01
    # a discount the client attributes to a pricing rule is the rule's business
    if item.get("pricing_rule"):
        client_discount = min(client_discount, rule_discount)

    if same_as_before and existing.get("pricing_rule") and not existing_manual(existing, rule_discount):
        # a pricing-rule discount follows the rule for the new qty
        discount = rule_discount
        rate = price_list_rate * (1 - discount / 100)
    elif same_as_before:
        # unchanged line: lowering qty or editing notes keeps what was approved;
        # more units at a manual discount / price need it again if the role doesn't allow it
        discount = flt(existing.discount_percentage)
        kept_rate = custom_rate or abs(flt(existing.rate) - price_list_rate * (1 - discount / 100)) > 0.01
        if qty > flt(existing.qty):
            if kept_rate:
                access.require("change_price", order.pos_profile, reference=ref, amount=flt(existing.rate),
                               detail=f"{item_code} x{qty}")
            elif discount > rule_discount + 0.0001:
                access.require("discount", order.pos_profile, amount=discount, reference=ref,
                               detail=f"{item_code} x{qty}")
        rate = flt(existing.rate) if kept_rate else price_list_rate * (1 - discount / 100)
    elif custom_rate:
        access.require("change_price", order.pos_profile, reference=ref,
                       amount=client_rate, detail=f"{item_code}: {price_list_rate} -> {client_rate}")
        access.audit("change_price", pos_profile=order.pos_profile, reference=("Ren Order", order.name),
                     amount=client_rate, detail=f"{item_code}: {price_list_rate} -> {client_rate}")
        rate = client_rate
        discount = ((price_list_rate - rate) / price_list_rate * 100) if price_list_rate else 0
        discount = min(max(discount, 0), 100)
    elif client_discount > rule_discount + 0.0001:
        access.require("discount", order.pos_profile, amount=client_discount,
                       reference=ref, detail=f"{item_doc.item_name or item_code}: {client_discount}%")
        access.audit("discount", pos_profile=order.pos_profile, reference=("Ren Order", order.name),
                     amount=client_discount, detail=f"{item_code}: {client_discount}%")
        discount = client_discount
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
        "modifiers": modifiers,
        "modifiers_amount": modifiers_amount,
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

        if is_editable(item.status):
            products_not_ordered += 1

    order.amount = total_amount
    order.tax = total_tax
    #$order.items_count = items_count
    order.products_not_ordered = products_not_ordered


def _get_order_items(order_name):
    """Get items for an order as a list of dicts."""
    items = frappe.get_all(
        "Ren Order Item",
        filters={"parent": order_name},
        fields=[
            "name as entry_name", "identifier", "item_code", "item_name",
            "qty", "rate", "price_list_rate", "discount_percentage",
            "amount", "tax_amount", "item_tax_rate",
            "status", "notes", "batch_no", "serial_no",
            "has_batch_no", "has_serial_no", "modifiers", "modifiers_amount", "parent", "ren_hold",
            #"process_status_data",
        ],
        order_by="idx asc",
    )

    from renpos.api.modifiers import parse as parse_modifiers

    # Parse process_status_data
    for item in items:
        item["modifiers"] = parse_modifiers(item.get("modifiers"))
        if isinstance(item.get("process_status_data"), str):
            try:
                item["process_status_data"] = json.loads(item["process_status_data"])
            except (json.JSONDecodeError, TypeError):
                item["process_status_data"] = {"icon": "fa fa-circle", "color": "gray"}
        elif not item.get("process_status_data"):
            item["process_status_data"] = {"icon": "fa fa-circle", "color": "gray"}

    return items


def _line_counts(order_names):
    """{order: {items_count, pending_count}}: lines with qty, and those the waiter hasn't sent."""
    if not order_names:
        return {}
    rows = frappe.db.sql(
        """SELECT parent, status, COUNT(*) AS n FROM `tabRen Order Item`
        WHERE parenttype = 'Ren Order' AND parent IN %(orders)s AND qty > 0
        GROUP BY parent, status""",
        {"orders": list(order_names)},
        as_dict=True,
    )
    out = {}
    for r in rows:
        c = out.setdefault(r.parent, {"items_count": 0, "pending_count": 0})
        c["items_count"] += r.n
        if is_editable(r.status):
            c["pending_count"] += r.n
    return out


def _order_dict(order):
    """Convert order doc to dict for JSON response."""
    return {
        "name": order.name,
        "customer": order.customer,
        "customer_name": getattr(order, "customer_name", ""),
        "status": order.status,
        "dinners": cint(order.dinners) if hasattr(order, "dinners") else 0,
        "notes": order.get("notes") or "",
        "amount": flt(order.amount) if hasattr(order, "amount") else 0,
        "tax": flt(order.tax) if hasattr(order, "tax") else 0,
        "table": order.table,
        "show_in_pos": cint(getattr(order, "show_in_pos", 1)),
        "products_not_ordered": cint(getattr(order, "products_not_ordered", 0)),
        # order tabs badge: lines in the order / lines not sent yet
        "items_count": len([i for i in order.get("entry_items") or [] if flt(i.qty) > 0]),
        "pending_count": len([i for i in order.get("entry_items") or [] if flt(i.qty) > 0 and is_editable(i.status)]),
        "attending_status": getattr(order, "attending_status", "Pending"),
        "short_name": getattr(order, "short_name", order.name[-5:]),
        # delivery (api/delivery.py): the fee is a charge on the bill
        "ren_delivery": cint(order.get("ren_delivery")),
        "ren_delivery_address": order.get("ren_delivery_address") or "",
        "ren_delivery_zip": order.get("ren_delivery_zip") or "",
        "ren_delivery_zone": order.get("ren_delivery_zone") or "",
        "ren_delivery_fee": flt(order.get("ren_delivery_fee")),
        "ren_delivery_minimum": flt(order.get("ren_delivery_minimum")),
        "ren_deliver_by": str(order.get("ren_deliver_by") or ""),
        "ren_guest_phone": order.get("ren_guest_phone") or "",
        "ren_driver_name": order.get("ren_driver_name") or "",
        "ren_dispatched_at": str(order.get("ren_dispatched_at") or ""),
        "ren_delivered_at": str(order.get("ren_delivered_at") or ""),
        "sales_invoice": getattr(order, "sales_invoice", ""),
        "pos_profile": order.pos_profile,
        # placed by the guest (online pickup / QR at the table)
        "ren_origin": order.get("ren_origin") or "",
        "ren_guest_name": order.get("ren_guest_name") or "",
        "ren_pickup_time": str(order.get("ren_pickup_time") or ""),
    }


def _get_pos_profile_for_table(table_doc):
    """
    The POS Profile an order is taken with: the one the person works with
    (their register, or the restaurant's) when the table is of their
    restaurant, else the table's restaurant's own profile.
    """
    from renpos.api.access import restaurant_of_table
    from renpos.api.guards import current_restaurant, current_pos_profile, restaurant_profile
    restaurant = restaurant_of_table(table_doc.name)
    if restaurant and restaurant == current_restaurant():
        return current_pos_profile()
    profile = restaurant_profile(restaurant)
    if not profile:
        frappe.throw(_("Restaurant {0} has no POS Profile").format(restaurant or "?"))
    return profile


def _check_and_free_table(table_name):
    """Free table if no more active orders."""
    active = frappe.db.count(
        "Ren Order",
        filters={
            "table": table_name,
            "status": ["not in", ["Invoiced", "Cancelled"]],
        },
    )

    if active == 0:
        frappe.db.set_value("Ren Table", table_name, "customer", "")
        # refresh the table/room badges on every floor map
        frappe.get_doc("Ren Table", table_name).synchronize()


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
        # only sockets subscribed to Ren Order (they need read permission)
        room=_ORDER_ROOM,
        after_commit=True,
    )