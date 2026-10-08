# -*- coding: utf-8 -*-
# renpos/api/menus.py
#
# Which menu a table sells from, at what price, and what is sold out.
#
# Menu in force for a room (first enabled one wins):
#   1. the room's own menu (Ren Room.menu)
#   2. the restaurant's active menu (Ren Restaurant.active_menu)
#   3. the company's default menu (Ren Menu.is_default)
# The star in the Menu Manager sets (2) for the current restaurant and keeps
# (3) in step, so the two can't disagree.
#
# Price of an item on a menu: the menu row's "Menu Price" when set, else the
# price list (same rules everywhere: catalog, order validation, invoice).
#
# Sold out ("86"): Ren Sold Out rows per restaurant; the catalog greys
# the item out on every screen in real time and new lines are refused.

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate, now_datetime

from renpos.api.guards import require_restaurant_user, current_restaurant, is_manager

try:
    from frappe.realtime import get_doctype_room
    _ORDER_ROOM = get_doctype_room("Ren Order")
except ImportError:
    _ORDER_ROOM = "doctype:Ren Order"


# ─────────────────────────────────────────────
# Menu in force
# ─────────────────────────────────────────────

def _enabled(menu):
    return bool(menu) and cint(frappe.db.get_value("Ren Menu", menu, "enabled"))


def restaurant_of_room(room):
    if not room:
        return None
    floor = frappe.db.get_value("Ren Room", room, "floor")
    return frappe.db.get_value("Ren Floor", floor, "restaurant") if floor else None


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def scheduled_menu(company, at=None):
    """The enabled menu whose schedule covers `at` (now), e.g. Breakfast 7-11, Happy Hour 16-18."""
    if not company:
        return None
    at = at or now_datetime()
    t = at.time()
    day, prev = WEEKDAYS[at.weekday()], WEEKDAYS[(at.weekday() - 1) % 7]
    rows = frappe.db.sql(
        """SELECT m.name, s.weekday, s.from_time, s.to_time FROM `tabRen Menu Schedule` s
        JOIN `tabRen Menu` m ON m.name = s.parent AND s.parenttype = 'Ren Menu'
        WHERE m.company = %s AND m.enabled = 1 ORDER BY m.menu_name, s.idx""", company, as_dict=True)
    for r in rows:
        start, end = frappe.utils.get_time(r.from_time), frappe.utils.get_time(r.to_time)
        overnight = end <= start
        today_ok = r.weekday in ("Every day", day)
        yesterday_ok = r.weekday in ("Every day", prev)
        if today_ok and t >= start and (overnight or t < end):
            return r.name
        if yesterday_ok and overnight and t < end:
            return r.name
    return None


def resolve_menu(room=None, restaurant=None, at=None):
    """{name, menu_name, source: room | schedule | restaurant | default} or None."""
    restaurant = restaurant or restaurant_of_room(room) or current_restaurant()
    candidates = []
    if room:
        candidates.append((frappe.db.get_value("Ren Room", room, "menu"), "room"))
    if restaurant:
        company = frappe.db.get_value("Ren Restaurant", restaurant, "company")
        candidates.append((scheduled_menu(company, at), "schedule"))
        candidates.append((frappe.db.get_value("Ren Restaurant", restaurant, "active_menu"), "restaurant"))
        if company:
            candidates.append((frappe.db.get_value(
                "Ren Menu", {"company": company, "is_default": 1, "enabled": 1}, "name"), "default"))
    for menu, source in candidates:
        if _enabled(menu):
            return {"name": menu, "menu_name": frappe.db.get_value("Ren Menu", menu, "menu_name"),
                    "source": source}
    return None


def menu_of_order(order):
    room = order.get("room") or (frappe.db.get_value("Ren Table", order.table, "room") if order.get("table") else None)
    m = resolve_menu(room=room)
    return m["name"] if m else None


@frappe.whitelist()
def get_active_menu(room=None):
    require_restaurant_user()
    return resolve_menu(room=room)


# ─────────────────────────────────────────────
# Prices
# ─────────────────────────────────────────────

def menu_prices(menu, item_codes=None):
    """{item_code: Menu Price} for rows with a price on that menu."""
    if not menu:
        return {}
    filters = {"parent": menu, "parenttype": "Ren Menu", "rate": [">", 0]}
    if item_codes is not None:
        filters["item"] = ["in", list(item_codes) or [""]]
    return {r.item: flt(r.rate) for r in frappe.get_all("Ren Menu Item", filters=filters,
                                                        fields=["item", "rate"])}


def list_prices(item_codes, price_list):
    """{item_code: price} from the price list: valid today, no customer/batch, stock UOM first."""
    if not item_codes or not price_list:
        return {}
    rows = frappe.db.sql(
        """
        SELECT ip.item_code, ip.price_list_rate
        FROM `tabItem Price` ip JOIN `tabItem` i ON i.name = ip.item_code
        WHERE ip.item_code IN %(codes)s AND ip.price_list = %(pl)s AND ip.selling = 1
          AND (ip.valid_from IS NULL OR ip.valid_from <= %(today)s)
          AND (ip.valid_upto IS NULL OR ip.valid_upto >= %(today)s)
          AND IFNULL(ip.customer, '') = '' AND IFNULL(ip.batch_no, '') = ''
        ORDER BY (IFNULL(ip.uom, '') = '' OR ip.uom = i.stock_uom) ASC, ip.valid_from ASC
        """,
        {"codes": list(item_codes), "pl": price_list, "today": nowdate()},
        as_dict=True,
    )
    out = {}
    for r in rows:  # later rows win: best UOM match, latest valid_from
        out[r.item_code] = flt(r.price_list_rate)
    return out


def item_price(item_code, price_list, menu=None):
    """The price a line is charged before discounts: menu price, else price list (None if neither)."""
    mp = menu_prices(menu, [item_code]).get(item_code)
    if mp:
        return mp
    return list_prices([item_code], price_list).get(item_code)


def in_menu(menu, item_code):
    return bool(frappe.db.exists("Ren Menu Item", {
        "parent": menu, "parenttype": "Ren Menu", "item": item_code, "enabled": 1}))


# ─────────────────────────────────────────────
# Sold out (86)
# ─────────────────────────────────────────────

def sold_out_items(restaurant=None):
    restaurant = restaurant or current_restaurant()
    return set(frappe.get_all("Ren Sold Out", filters={"restaurant": restaurant or ""}, pluck="item_code"))


@frappe.whitelist()
def get_sold_out():
    require_restaurant_user()
    restaurant = current_restaurant()
    return frappe.get_all("Ren Sold Out", filters={"restaurant": restaurant or ""},
                          fields=["item_code", "item_name", "owner", "creation"], order_by="creation desc")


@frappe.whitelist()
def set_sold_out(item_code, sold_out=1):
    """86 an item (sold_out=1) or bring it back (0), for the user's restaurant."""
    require_restaurant_user()
    from renpos.api import access
    access.require("mark_sold_out")
    restaurant = current_restaurant()
    if not restaurant:
        frappe.throw(_("Your POS Profile has no restaurant"))
    existing = frappe.db.get_value("Ren Sold Out", {"restaurant": restaurant, "item_code": item_code})
    if cint(sold_out) and not existing:
        frappe.get_doc({"doctype": "Ren Sold Out", "restaurant": restaurant, "item_code": item_code,
                        "item_name": frappe.db.get_value("Item", item_code, "item_name")}).insert(ignore_permissions=True)
    elif not cint(sold_out) and existing:
        frappe.delete_doc("Ren Sold Out", existing, ignore_permissions=True)
    frappe.publish_realtime("menu_availability", {"restaurant": restaurant, "item_code": item_code,
                                                  "sold_out": cint(sold_out)}, after_commit=True)
    return {"item_code": item_code, "sold_out": cint(sold_out)}


# ─────────────────────────────────────────────
# Menu Manager
# ─────────────────────────────────────────────

@frappe.whitelist()
def list_menus(company=None, search=None, limit=50, start=0, restaurant=None):
    """Menus of the company, with the one active in the user's restaurant and the rooms using each."""
    require_restaurant_user()
    restaurant = restaurant or current_restaurant()
    company = company or (frappe.db.get_value("Ren Restaurant", restaurant, "company") if restaurant else None) \
        or frappe.defaults.get_user_default("company")
    filters = {"company": company}
    if search:
        filters["menu_name"] = ["like", f"%{search}%"]
    menus = frappe.get_all("Ren Menu", filters=filters,
                           fields=["name", "menu_name", "company", "enabled", "is_default", "total_items"],
                           order_by="menu_name asc", limit_start=cint(start), limit_page_length=cint(limit) or 50)
    active = resolve_menu(restaurant=restaurant) if restaurant else None
    rooms = {}
    for r in frappe.get_all("Ren Room", filters={"menu": ["is", "set"]}, fields=["name", "description", "menu"]):
        rooms.setdefault(r.menu, []).append(r.description or r.name)
    scheduled = set(frappe.get_all("Ren Menu Schedule", filters={"parenttype": "Ren Menu"}, pluck="parent"))
    star = frappe.db.get_value("Ren Restaurant", restaurant, "active_menu") if restaurant else None
    for m in menus:
        m["is_active"] = 1 if (star or (active or {}).get("name")) == m.name else 0
        m["in_force"] = 1 if active and active["name"] == m.name else 0
        m["scheduled"] = 1 if m.name in scheduled else 0
        m["rooms"] = rooms.get(m.name, [])
    menus.sort(key=lambda m: (-m["is_active"], m.menu_name or ""))
    return {"menus": menus, "restaurant": restaurant, "company": company}


@frappe.whitelist()
def set_active_menu(menu, restaurant=None):
    """The star: this menu is the restaurant's menu (and the company default)."""
    require_restaurant_user()
    from renpos.api import access
    access.require("edit_menu")
    mine = current_restaurant()
    if restaurant and restaurant != mine and not is_manager():
        raise frappe.PermissionError(_("Not your restaurant"))
    restaurant = restaurant or mine
    company = frappe.db.get_value("Ren Menu", menu, "company")
    if restaurant:
        if frappe.db.get_value("Ren Restaurant", restaurant, "company") not in (None, "", company):
            frappe.throw(_("Menu {0} belongs to another company").format(menu))
        frappe.db.set_value("Ren Restaurant", restaurant, "active_menu", menu)
    doc = frappe.get_doc("Ren Menu", menu)
    if not doc.enabled:
        doc.enabled = 1
    doc.is_default = 1
    doc.flags.ignore_permissions = True
    doc.save()
    frappe.publish_realtime("menu_changed", {"restaurant": restaurant, "menu": menu}, after_commit=True)
    return resolve_menu(restaurant=restaurant)


@frappe.whitelist()
def set_menu_item(menu, item_code, enabled=1, rate=None):
    """Add / re-enable / remove (enabled=0) an item on a menu; optional Menu Price."""
    require_restaurant_user()
    from renpos.api import access
    access.require("edit_menu")
    doc = frappe.get_doc("Ren Menu", menu)
    doc.check_permission("read")
    doc.flags.ignore_permissions = True
    row = next((r for r in doc.items if r.item == item_code), None)
    if cint(enabled):
        if not row:
            row = doc.append("items", {"item": item_code, "enabled": 1})
        row.enabled = 1
        if rate is not None:
            row.rate = flt(rate)
    elif row:
        doc.remove(row)
    doc.save()
    frappe.publish_realtime("menu_changed", {"menu": menu}, after_commit=True)
    return {"menu": menu, "total_items": doc.total_items}


# ─────────────────────────────────────────────
# Menu tags (dietary & allergens)
# ─────────────────────────────────────────────

DEFAULT_TAGS = [
    # tag, kind, abbreviation, color, filter
    ("Vegetarian", "Dietary", "V", "#16a34a", 1),
    ("Vegan", "Dietary", "VG", "#15803d", 1),
    ("Gluten-free", "Dietary", "GF", "#ca8a04", 1),
    ("Spicy", "Other", "🌶", "#dc2626", 0),
    ("Peanuts", "Allergen", "PN", "#b45309", 0),
    ("Tree nuts", "Allergen", "TN", "#92400e", 0),
    ("Milk", "Allergen", "MK", "#0284c7", 0),
    ("Eggs", "Allergen", "EG", "#eab308", 0),
    ("Wheat", "Allergen", "WH", "#a16207", 0),
    ("Soy", "Allergen", "SY", "#65a30d", 0),
    ("Fish", "Allergen", "FS", "#0369a1", 0),
    ("Shellfish", "Allergen", "SF", "#e11d48", 0),
    ("Sesame", "Allergen", "SS", "#78350f", 0),
]


def install_default_tags():
    """The US "Big 9" allergens plus common dietary tags (only when there are none)."""
    if not frappe.db.exists("DocType", "Ren Menu Tag") or frappe.db.count("Ren Menu Tag"):
        return
    for name, kind, abbr, color, flt_ in DEFAULT_TAGS:
        frappe.get_doc({"doctype": "Ren Menu Tag", "tag_name": name, "kind": kind, "abbreviation": abbr, "color": color,
                        "show_as_filter": flt_}).insert(ignore_permissions=True)


@frappe.whitelist()
def get_menu_tags():
    require_restaurant_user()
    return frappe.get_all("Ren Menu Tag", fields=["name", "kind", "abbreviation", "color", "show_as_filter"],
                          order_by="kind asc, tag_name asc")


def item_tags(item_codes):
    """{item_code: [tag, ...]}"""
    if not item_codes or not frappe.db.exists("DocType", "Ren Item Menu Tag"):
        return {}
    out = {}
    for r in frappe.get_all("Ren Item Menu Tag", filters={"parenttype": "Item", "parent": ["in", list(item_codes)]},
                            fields=["parent", "tag"], order_by="idx asc"):
        out.setdefault(r.parent, []).append(r.tag)
    return out


def items_with_tag(tag):
    return frappe.get_all("Ren Item Menu Tag", filters={"parenttype": "Item", "tag": tag}, pluck="parent")
