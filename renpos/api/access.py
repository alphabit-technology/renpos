# -*- coding: utf-8 -*-
# renpos/api/access.py
#
# Who may do what, in one place.
#
#   Ren Role   what a person may do (Server, Bartender, Host, Cashier,
#                     Manager... all editable records): max discount, voids,
#                     price changes, drawer, transfers, other people's orders,
#                     86, reservations, floor and menu editing, approving.
#   Ren Staff  a person at a restaurant: their role there and the
#                     floors / rooms / tables / stations they work.
#   POS Profile       only for charging (cashiers are listed in it), see guards.py.
#   Managers          (Restaurant Manager / System Manager) may do everything.
#
# When a role doesn't allow an action, a person whose role does (and has
# "Approve with PIN") can approve it on the spot: the client asks for the
# PIN, gets a one-time approval token (approve) and repeats the call with it.
# Approvals and sensitive actions go to the Ren Audit Log.

import hashlib
import hmac
import secrets

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, get_fullname

from renpos.api.guards import (
    require_restaurant_user, is_manager, current_pos_profile, current_restaurant, profile_restaurant,
    staff_restaurants,
)

ACTIONS = {
    "all_tables": _("work on every table"),
    "view_others_orders": _("see other people's orders"),
    "operate_others_orders": _("work on other people's orders"),
    "transfer_orders": _("transfer orders"),
    "divide_orders": _("split orders"),
    "discount": _("give this discount"),
    "change_price": _("change prices"),
    "void_sent_items": _("void items sent to the kitchen"),
    "void_orders": _("void orders"),
    "take_payments": _("charge orders"),
    "manage_register": _("open or close the register"),
    "open_drawer": _("open the cash drawer"),
    "reprint": _("reprint"),
    "mark_sold_out": _("mark items sold out"),
    "manage_reservations": _("manage reservations"),
    "edit_floor": _("edit the floor plan"),
    "edit_menu": _("edit menus"),
    "delivers_orders": _("deliver orders"),
    "all_stations": _("work every production center"),
}
FLAGS = [a for a in ACTIONS if a != "discount"]

APPROVAL_TTL = 120

# orders guests placed themselves (online, QR at the table) belong to every server
GUEST_OWNER = "Guest"  # seconds


class ApprovalRequired(frappe.ValidationError):
    """The action needs a manager PIN (client: ask for it and retry with `approval`)."""


# ─────────────────────────────────────────────
# Roles
# ─────────────────────────────────────────────

def staff_record(user, restaurant):
    """The person's Ren Staff at the restaurant (enabled), if any."""
    if not restaurant:
        return None
    return frappe.db.get_value("Ren Staff", {"user": user, "restaurant": restaurant, "enabled": 1}, "name")


def _context_restaurant(user, pos_profile=None):
    """The restaurant a check is about: the profile's, else where the person works now."""
    return profile_restaurant(pos_profile) if pos_profile else current_restaurant(user)


TEAM_SERVICE = "Team service"


def table_service(pos_profile=None, restaurant=None):
    """The restaurant's table policy: "Own tables" (default) or "Team service"."""
    restaurant = restaurant or _context_restaurant(frappe.session.user, pos_profile)
    return (restaurant and frappe.db.get_value("Ren Restaurant", restaurant, "table_service")) or "Own tables"


def role_of(user=None, pos_profile=None):
    """
    The person's Ren Role as a dict of flags (+ max_discount). Managers:
    everything. In a "Team service" restaurant everyone may see and work on
    the orders of the tables they work, whoever opened them.
    """
    user = user or frappe.session.user
    restaurant = _context_restaurant(user, pos_profile)
    role = _role_of(user, restaurant)
    role.table_service = table_service(restaurant=restaurant)
    if not role.manager and role.table_service == TEAM_SERVICE:
        role.update(view_others_orders=1, operate_others_orders=1)
    return role


def _role_of(user, restaurant):
    user = user or frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & {"Restaurant Manager", "System Manager"}:
        return frappe._dict({**{f: 1 for f in FLAGS}, "max_discount": 100, "can_approve": 1,
                             "name": None, "manager": 1})
    staff = staff_record(user, restaurant)
    role = frappe.db.get_value("Ren Staff", staff, "restaurant_role") if staff else None
    role = role or frappe.db.get_single_value("Ren Settings", "default_restaurant_role")
    if role and frappe.db.exists("Ren Role", role):
        d = frappe.get_cached_doc("Ren Role", role)
        out = frappe._dict({f: cint(d.get(f)) for f in FLAGS})
        out.update(max_discount=flt(d.max_discount), can_approve=cint(d.can_approve), name=role, manager=0)
        return out
    # no role anywhere: the permissive defaults of a server
    return frappe._dict({f: 0 for f in FLAGS} | {
        "view_others_orders": 1, "transfer_orders": 1, "divide_orders": 1, "take_payments": 1,
        "manage_register": 1, "reprint": 1, "mark_sold_out": 1, "manage_reservations": 1,
        "max_discount": 0, "can_approve": 0, "name": None, "manager": 0})


def can(action, pos_profile=None, user=None, amount=None):
    role = role_of(user, pos_profile)
    if action == "discount":
        return flt(amount) <= flt(role.max_discount) + 1e-6
    return bool(role.get(action))


def require(action, pos_profile=None, approval=None, amount=None, reference=None, detail=None):
    """
    Allowed by the role, or approved with a PIN (one-time `approval` token).
    Returns the approver (None when the role allows it). Raises ApprovalRequired.
    """
    if can(action, pos_profile, amount=amount):
        return None
    approval = approval or frappe.form_dict.get("approval")
    ref_name = reference[1] if reference else None
    approver = _consume_approval(approval, action, amount, ref_name) if approval else None
    if approver:
        audit(f"approved:{action}", approved_by=approver, pos_profile=pos_profile, reference=reference,
              amount=amount, detail=detail)
        return approver
    label = ACTIONS.get(action, action)
    # the client reads these to ask for a manager PIN and repeat the call
    frappe.local.response["approval_action"] = action
    frappe.local.response["approval_label"] = label
    if amount is not None:
        frappe.local.response["approval_amount"] = flt(amount)
    if ref_name:
        frappe.local.response["approval_reference"] = ref_name
    if detail:
        frappe.local.response["approval_detail"] = str(detail)[:140]
    frappe.throw(_("You need a manager's approval to {0}").format(label), ApprovalRequired,
                 title=_("Approval needed"))


# ─────────────────────────────────────────────
# Tables & orders
# ─────────────────────────────────────────────

def restaurant_of_table(table):
    row = frappe.db.sql(
        """SELECT f.restaurant FROM `tabRen Table` t JOIN `tabRen Room` r ON r.name = t.room
        JOIN `tabRen Floor` f ON f.name = r.floor WHERE t.name = %s""", table)
    return row[0][0] if row else None


def user_tables(pos_profile=None):
    """
    None = every table: managers, and a role with "Every table of the
    restaurant" when no floor, room or table is assigned to the person.
    Otherwise the tables of what is assigned in their Ren Staff.
    """
    if is_manager():
        return None
    settings = frappe.get_single("Ren Settings")
    if can("all_tables", pos_profile) and not settings.has_layout_grants():
        return None
    return settings.restaurant_access("Ren Table") or set()


def takes_orders():
    """Works some table (managers: all). Kitchen and drivers don't: no tables, no phone orders."""
    return is_manager() or user_tables() != set()


def check_table_access(table, pos_profile=None):
    """The table belongs to the user's restaurant and the user works it."""
    require_restaurant_user()
    if not table or not frappe.db.exists("Ren Table", table):
        frappe.throw(_("Table {0} not found").format(table), frappe.DoesNotExistError)
    if is_manager():
        return
    mine = current_restaurant()
    theirs = restaurant_of_table(table)
    if theirs != mine:
        raise frappe.PermissionError(_("This table belongs to another restaurant (switch in \"Work at\")"))
    tables = user_tables()
    if tables is not None and table not in tables:
        raise frappe.PermissionError(_("You don't work this table"))


def check_order_access(order, write=True, approval=None):
    """
    Table access, plus other people's orders: seeing them needs "see other
    people's orders", working on them "work on other people's orders" (or a PIN).
    """
    if is_manager():
        return
    if order.get("table"):
        check_table_access(order.table, order.pos_profile)
    if order.owner in (frappe.session.user, GUEST_OWNER):
        return
    if not can("view_others_orders", order.pos_profile):
        raise frappe.PermissionError(_("This order belongs to {0}").format(frappe.utils.get_fullname(order.owner)))
    if write:
        # one approval unlocks that order for this person for a while
        unlock = f"ren_order_unlock:{frappe.session.user}:{order.name}"
        if frappe.cache.get_value(unlock):
            return
        if require("operate_others_orders", order.pos_profile, approval=approval,
                   reference=("Ren Order", order.name)):
            frappe.cache.set_value(unlock, 1, expires_in_sec=30 * 60)


def check_new_order_on_table(table, pos_profile=None, approval=None):
    """
    Own tables: an occupied table belongs to whoever opened it. Opening another
    order on it takes "work on other people's orders" (or a manager PIN).
    """
    if is_manager():
        return
    owners = set(frappe.get_all("Ren Order", pluck="owner", filters={
        "table": table, "status": ["not in", ["Invoiced", "Cancelled"]]}))
    owners -= {frappe.session.user, GUEST_OWNER}
    if owners:
        require("operate_others_orders", pos_profile, approval=approval, reference=("Ren Table", table))


# ─────────────────────────────────────────────
# PINs and approvals
# ─────────────────────────────────────────────

def _pin_hash(user, pin):
    secret = (frappe.local.conf.get("encryption_key") or frappe.local.site or "").encode()
    return hashlib.pbkdf2_hmac("sha256", str(pin).encode(), secret + user.encode(), 20_000).hex()


def _valid_pin(pin):
    pin = str(pin or "").strip()
    if not pin.isdigit() or not 4 <= len(pin) <= 8:
        frappe.throw(_("The PIN must be 4 to 8 digits"))
    return pin


def users_with_pin():
    if not frappe.get_meta("User").has_field("ren_pin_hash"):
        return []
    return frappe.get_all("User", filters={"enabled": 1, "ren_pin_hash": ["is", "set"]},
                          fields=["name", "ren_pin_hash"])


def users_by_pin(pin, candidates=None):
    """Everyone whose PIN this is (PINs aren't unique: telling would reveal other people's)."""
    pin = str(pin or "").strip()
    if not pin:
        return []
    found = []
    for u in users_with_pin():
        if candidates is not None and u.name not in candidates:
            continue
        if hmac.compare_digest(u.ren_pin_hash, _pin_hash(u.name, pin)):
            found.append(u.name)
    return found


def pin_matches(user, pin):
    h = frappe.db.get_value("User", user, "ren_pin_hash") if frappe.get_meta("User").has_field("ren_pin_hash") else None
    return bool(h) and hmac.compare_digest(h, _pin_hash(user, str(pin or "").strip()))


@frappe.whitelist()
def set_pin(pin, user=None):
    """Set your own PIN (or, for managers, someone else's). PINs are unique."""
    require_restaurant_user()
    user = user or frappe.session.user
    if user != frappe.session.user:
        # managers set staff PINs; never an administrator's, and another manager's only by a System Manager
        if not is_manager():
            raise frappe.PermissionError(_("Only a manager can set another person's PIN"))
        roles = set(frappe.get_roles(user))
        if user == "Administrator" or "System Manager" in roles:
            raise frappe.PermissionError(_("System managers set their own PIN"))
        if "Restaurant Manager" in roles and "System Manager" not in frappe.get_roles():
            raise frappe.PermissionError(_("Only a System Manager can set a manager's PIN"))
    pin = _valid_pin(pin)
    frappe.db.set_value("User", user, "ren_pin_hash", _pin_hash(user, pin), update_modified=False)
    audit("set_pin", detail=user)
    return {"ok": True}


@frappe.whitelist()
def has_pin():
    require_restaurant_user()
    return bool(frappe.db.get_value("User", frappe.session.user, "ren_pin_hash")) \
        if frappe.get_meta("User").has_field("ren_pin_hash") else False


@frappe.whitelist()
def approve(action, pin, amount=None, reference=None):
    """
    Someone allowed to approves `action` for the current user: returns a
    one-time token valid for APPROVAL_TTL seconds, for this user, action,
    order (`reference`) and amount (discount %, new price, voided value).
    """
    require_restaurant_user()
    if action not in ACTIONS:
        frappe.throw(_("Unknown action"))
    _valid_pin(pin)
    _check_attempts()
    profile = current_pos_profile()
    approver = None
    # someone else, whose role (in this POS Profile) approves and allows the action
    for candidate in users_by_pin(pin):
        if candidate == frappe.session.user:
            continue
        role = role_of(candidate, profile)
        if cint(role.can_approve) and can(action, profile, user=candidate, amount=amount):
            approver = candidate
            break
    ok = bool(approver)
    if not ok:
        _count_attempt()
        audit("approval_denied", detail=action)
        frappe.throw(_("PIN not valid for this approval"), frappe.PermissionError)
    token = secrets.token_urlsafe(24)
    frappe.cache.set_value(f"ren_approval:{token}", {
        "user": frappe.session.user, "action": action, "approver": approver,
        "amount": None if amount in (None, "") else flt(amount), "reference": reference or None,
    }, expires_in_sec=APPROVAL_TTL)
    return {"approval": token, "approver": frappe.utils.get_fullname(approver)}


def is_manager_user(user):
    return user == "Administrator" or bool(set(frappe.get_roles(user)) & {"Restaurant Manager", "System Manager"})


# how the approved amount bounds the real one
AMOUNT_RULES = {"discount": "max", "void_sent_items": "max", "void_orders": "max", "change_price": "equal"}


def _consume_approval(token, action, amount=None, reference=None):
    key = f"ren_approval:{token}"
    data = frappe.cache.get_value(key)
    if not data or data.get("user") != frappe.session.user or data.get("action") != action:
        return None
    if data.get("reference") and reference and data["reference"] != reference:
        return None
    rule = AMOUNT_RULES.get(action)
    if rule and amount is not None:
        approved = data.get("amount")
        if approved is None:
            return None
        if rule == "max" and flt(amount) > flt(approved) + 1e-6:
            return None
        if rule == "equal" and abs(flt(amount) - flt(approved)) > 0.01:
            return None
    frappe.cache.delete_value(key)
    return data.get("approver")


def _attempt_key():
    return f"ren_pin_attempts:{frappe.session.user}"


def _check_attempts():
    if cint(frappe.cache.get_value(_attempt_key())) >= 5:
        frappe.throw(_("Too many wrong PINs. Wait a few minutes."), frappe.PermissionError)


def _count_attempt():
    key = _attempt_key()
    frappe.cache.set_value(key, cint(frappe.cache.get_value(key)) + 1, expires_in_sec=300)


# ─────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────

def audit(action, approved_by=None, pos_profile=None, reference=None, amount=None, detail=None):
    """Written in its own job, so it stays even if the request that triggered it fails."""
    try:
        frappe.enqueue("renpos.api.access._write_audit", queue="short",
                       enqueue_after_commit=False, now=bool(frappe.flags.in_test),
                       user=frappe.session.user, action=action, approved_by=approved_by, pos_profile=pos_profile,
                       reference=list(reference) if reference else None, amount=amount, detail=detail,
                       at=now_datetime())
    except Exception:
        frappe.log_error(title="Restaurant: audit log not queued")


def _write_audit(user, action, approved_by=None, pos_profile=None, reference=None, amount=None, detail=None,
                 at=None):
    try:
        frappe.get_doc({
            "doctype": "Ren Audit Log", "logged_at": at or now_datetime(), "action": action[:140],
            "user": user, "approved_by": approved_by,
            "pos_profile": pos_profile, "reference_doctype": reference[0] if reference else None,
            "reference_name": reference[1] if reference else None, "amount": flt(amount) if amount else None,
            "detail": str(detail)[:1000] if detail else None,
        }).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="Restaurant: audit log not written")


# ─────────────────────────────────────────────
# What the client needs
# ─────────────────────────────────────────────

@frappe.whitelist()
def my_context():
    """
    Where the person is working and why they see what they see: the
    restaurant (and how it was chosen), every restaurant they work at with
    their role and access there, the role in force and where it comes from,
    and the POS Profiles they charge with here.
    """
    require_restaurant_user()
    from renpos.api.guards import RESTAURANT_KEY, billing_profiles
    user = frappe.session.user
    restaurant = current_restaurant(user)
    chosen = frappe.defaults.get_user_default(RESTAURANT_KEY, user)

    labels = {}

    def label(doctype, name):
        key = (doctype, name)
        if key not in labels:
            labels[key] = frappe.db.get_value(doctype, name, "description") or name
        return labels[key]

    staff = []
    for r in frappe.get_all("Ren Staff", filters={"user": user},
                            fields=["name", "restaurant", "restaurant_role", "is_default", "enabled"],
                            order_by="is_default desc, restaurant asc"):
        grants = frappe.get_all("Ren Access Grant", filters={"parenttype": "Ren Staff", "parent": r.name},
                                fields=["object_type", "object_name"], order_by="idx")
        staff.append({
            "restaurant": r.restaurant,
            "restaurant_name": frappe.db.get_value("Ren Restaurant", r.restaurant, "restaurant_name") or r.restaurant,
            "role": r.restaurant_role, "default": cint(r.is_default), "enabled": cint(r.enabled),
            "active": r.restaurant == restaurant,
            "grants": [{"type": g.object_type, "name": g.object_name, "label": label(g.object_type, g.object_name)}
                       for g in grants if g.object_type and frappe.db.exists(g.object_type, g.object_name)],
        })

    if not restaurant:
        how = "none"
    elif chosen == restaurant:
        how = "chosen"
    elif any(s_["active"] and s_["default"] for s_ in staff):
        how = "default"
    else:
        how = "first"

    role = role_of(user)
    active_row = next((x for x in staff if x["active"]), None)
    if role.manager:
        role_source = "manager"
    elif active_row and active_row["role"]:
        role_source = "staff"
    elif role.name:
        role_source = "settings_default"
    else:
        role_source = "built_in"

    settings = frappe.get_single("Ren Settings")
    whole_plan = bool(settings.user_has_admin_role())
    visible = None
    if not whole_plan:
        visible = {key: len(settings.restaurant_access(doctype)) for key, doctype in (
            ("floors", "Ren Floor"), ("rooms", "Ren Room"), ("tables", "Ren Table"), ("stations", "Ren Station"))}

    rest = frappe.db.get_value("Ren Restaurant", restaurant, ["name", "restaurant_name", "company"],
                               as_dict=True) if restaurant else None
    return {
        "user": user,
        "full_name": get_fullname(user),
        "restaurant": rest,
        "chosen_by": how,
        "pos_profile": current_pos_profile(user),
        "billing_profiles": billing_profiles(restaurant, user) if restaurant else [],
        "role": {"name": role.name, "manager": cint(role.manager), "source": role_source},
        "whole_plan": whole_plan,
        "visible": visible,
        "staff": staff,
    }


# ─────────────────────────────────────────────
# List restrictions (REST and list views)
# ─────────────────────────────────────────────

def table_order_query(user=None):
    user = user or frappe.session.user
    if is_manager_user(user):
        return ""
    restaurants = staff_restaurants(user)
    if not restaurants:
        return "1=0"
    cond = "`tabRen Order`.restaurant in ({0})".format(", ".join(frappe.db.escape(r) for r in restaurants))
    if not can("view_others_orders", user=user):
        # guests' own orders (online, QR at the table) are everybody's
        cond += " and `tabRen Order`.owner in ({0}, 'Guest')".format(frappe.db.escape(user))
    return cond


def booking_query(user=None):
    user = user or frappe.session.user
    if is_manager_user(user):
        return ""
    if not can("manage_reservations", user=user):
        return "1 = 0"
    restaurants = staff_restaurants(user)
    if not restaurants:
        return "IFNULL(`tabRen Booking`.restaurant, '') = ''"
    return "IFNULL(`tabRen Booking`.restaurant, '') in ('', {0})".format(
        ", ".join(frappe.db.escape(r) for r in restaurants))


def table_order_has_permission(doc, ptype=None, user=None, debug=False):
    user = user or frappe.session.user
    if is_manager_user(user):
        return True
    if doc.get("restaurant") not in staff_restaurants(user):
        return False
    if doc.owner not in (user, GUEST_OWNER) and not can("view_others_orders", doc.pos_profile, user=user):
        return False
    if doc.get("table") and user == frappe.session.user:
        tables = user_tables(doc.pos_profile)
        if tables is not None and doc.table not in tables:
            return False
    return True


def booking_has_permission(doc, ptype=None, user=None, debug=False):
    user = user or frappe.session.user
    if is_manager_user(user):
        return True
    if not can("manage_reservations", user=user):
        return False
    return not doc.restaurant or doc.restaurant in staff_restaurants(user)


# ─────────────────────────────────────────────
# Defaults
# ─────────────────────────────────────────────

DEFAULT_ROLES = {
    "Server": dict(view_others_orders=1, transfer_orders=1, divide_orders=1, take_payments=1, manage_register=1,
                   reprint=1, mark_sold_out=1, manage_reservations=1, max_discount=0,
                   description="Takes orders on their tables. Discounts, voids and price changes need a manager PIN."),
    "Bartender": dict(all_tables=1, view_others_orders=1, operate_others_orders=1, transfer_orders=1, divide_orders=1,
                      take_payments=1, manage_register=1, open_drawer=1, reprint=1, mark_sold_out=1, max_discount=10,
                      description="Runs the bar: any tab, charges, small discounts."),
    "Host": dict(all_tables=1, view_others_orders=1, manage_reservations=1, take_payments=0, manage_register=0,
                 description="Reservations, waitlist and seating."),
    "Cashier": dict(all_tables=1, view_others_orders=1, operate_others_orders=1, divide_orders=1, take_payments=1,
                    manage_register=1, open_drawer=1, reprint=1, max_discount=10,
                    description="Charges any order and runs the register."),
    "Driver": dict(view_others_orders=1, delivers_orders=1, take_payments=0, manage_register=0,
                   description="Takes delivery orders out: is listed as a driver on the dispatch screen."),
    "Kitchen": dict(description="Works the screens of the production centers assigned to them. No tables, no charging."),
    "Manager": dict(**{f: 1 for f in FLAGS}, max_discount=100, can_approve=1,
                    description="Everything, and approves other people's actions with their PIN."),
}


def insert_default_role(name):
    """One of DEFAULT_ROLES, with every flag set explicitly (field defaults don't apply)."""
    flags = DEFAULT_ROLES[name]
    doc = frappe.new_doc("Ren Role")
    doc.role_name = name
    for f in FLAGS + ["can_approve"]:
        doc.set(f, cint(flags.get(f, 0)))
    doc.max_discount = flt(flags.get("max_discount", 0))
    doc.description = flags.get("description")
    return doc.insert(ignore_permissions=True)


def install_default_roles():
    if not frappe.db.exists("DocType", "Ren Role") or frappe.db.count("Ren Role"):
        return
    for name in DEFAULT_ROLES:
        insert_default_role(name)
    if not frappe.db.get_single_value("Ren Settings", "default_restaurant_role"):
        frappe.db.set_single_value("Ren Settings", "default_restaurant_role", "Server")
