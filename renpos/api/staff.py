# -*- coding: utf-8 -*-
# renpos/api/staff.py
#
# Staff on shared terminals:
#   - clock in / out (Ren Shift); optional "must clock in to take orders"
#   - terminals a manager registered (Ren Terminal): staff switch
#     user there with their PIN instead of a password (/pos-login)

import hashlib
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, now_datetime, time_diff_in_seconds

from renpos.api.guards import require_restaurant_user, is_manager, current_pos_profile
from renpos.api import access


# ─────────────────────────────────────────────
# Clock in / out
# ─────────────────────────────────────────────

def open_shift(user=None):
    return frappe.db.get_value("Ren Shift", {"user": user or frappe.session.user, "clock_out": ["is", "not set"]},
                               ["name", "clock_in"], as_dict=True)


def require_clocked_in():
    if is_manager() or not cint(frappe.db.get_single_value("Ren Settings", "require_clock_in")):
        return
    if not open_shift():
        frappe.throw(_("Clock in to start taking orders"), title=_("Not clocked in"))


@frappe.whitelist()
def get_shift():
    require_restaurant_user()
    s = open_shift()
    return {"clocked_in": bool(s), "clock_in": s.clock_in if s else None,
            "required": cint(frappe.db.get_single_value("Ren Settings", "require_clock_in"))}


@frappe.whitelist()
def clock_in():
    require_restaurant_user()
    if open_shift():
        return get_shift()
    frappe.get_doc({"doctype": "Ren Shift", "user": frappe.session.user,
                    "pos_profile": current_pos_profile(), "clock_in": now_datetime()}).insert(ignore_permissions=True)
    return get_shift()


@frappe.whitelist()
def clock_out():
    require_restaurant_user()
    s = open_shift()
    if s:
        now = now_datetime()
        frappe.db.set_value("Ren Shift", s.name, {
            "clock_out": now, "minutes": int(time_diff_in_seconds(now, s.clock_in) // 60)})
    return get_shift()


# ─────────────────────────────────────────────
# Terminals and PIN login
# ─────────────────────────────────────────────

def _token_hash(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


@frappe.whitelist()
def register_terminal(terminal_name, pos_profile=None):
    """A manager registers this device: returns its secret token (kept in the browser)."""
    require_restaurant_user()
    if not is_manager():
        raise frappe.PermissionError(_("Only a manager can register a terminal"))
    pos_profile = pos_profile or current_pos_profile()
    if not pos_profile:
        frappe.throw(_("Choose a POS Profile"))
    token = secrets.token_urlsafe(32)
    doc = frappe.get_doc({"doctype": "Ren Terminal", "terminal_name": (terminal_name or "Terminal")[:140],
                          "pos_profile": pos_profile, "enabled": 1, "registered_by": frappe.session.user,
                          "token_hash": _token_hash(token)}).insert(ignore_permissions=True)
    access.audit("register_terminal", pos_profile=pos_profile, reference=("Ren Terminal", doc.name))
    return {"terminal": doc.name, "token": token, "terminal_name": doc.terminal_name}


def _terminal(token):
    if not token:
        return None
    name = frappe.db.get_value("Ren Terminal", {"token_hash": _token_hash(token), "enabled": 1}, "name")
    return frappe.get_doc("Ren Terminal", name) if name else None


def _pin_staff(pos_profile):
    """Who may log in with a PIN at a terminal: the staff of its restaurant with a PIN, never system managers."""
    restaurant = frappe.db.get_value("POS Profile", pos_profile, "ren_restaurant")
    users = frappe.get_all("Ren Staff", filters={"restaurant": restaurant, "enabled": 1}, pluck="user") \
        if restaurant else []
    out = []
    for u in users:
        if u == "Administrator" or not frappe.db.get_value("User", u, "enabled"):
            continue
        if "System Manager" in frappe.get_roles(u):
            continue
        if frappe.get_meta("User").has_field("ren_pin_hash") and frappe.db.get_value("User", u, "ren_pin_hash"):
            out.append(u)
    return out


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=60, seconds=60 * 10)
def terminal_info(token):
    t = _terminal(token)
    if not t or not cint(frappe.db.get_single_value("Ren Settings", "allow_pin_login")):
        return {"valid": False}
    staff = [{"user": u, "name": frappe.utils.get_fullname(u)} for u in _pin_staff(t.pos_profile)]
    return {"valid": True, "terminal_name": t.terminal_name, "staff": sorted(staff, key=lambda s: s["name"])}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 5)
def pin_login(user, pin, token):
    """
    Log in on a registered terminal: pick your name, type your PIN. Only the
    terminal's POS Profile staff (never system managers); 5 wrong PINs lock
    that person on that terminal for 5 minutes.
    """
    if not cint(frappe.db.get_single_value("Ren Settings", "allow_pin_login")):
        frappe.throw(_("PIN login is off"), frappe.PermissionError)
    t = _terminal(token)
    if not t:
        frappe.throw(_("This device isn't a registered terminal"), frappe.PermissionError)
    lock = f"ren_pin_login_fail:{t.name}:{user}"
    if cint(frappe.cache.get_value(lock)) >= 5:
        frappe.throw(_("Too many wrong PINs. Try again in a few minutes."), frappe.AuthenticationError)
    if user not in _pin_staff(t.pos_profile) or not access.pin_matches(user, pin):
        frappe.cache.set_value(lock, cint(frappe.cache.get_value(lock)) + 1, expires_in_sec=300)
        frappe.throw(_("Wrong PIN"), frappe.AuthenticationError)
    frappe.cache.delete_value(lock)
    frappe.local.login_manager.login_as(user)
    # the terminal's restaurant is where the person works now
    restaurant = frappe.db.get_value("POS Profile", t.pos_profile, "ren_restaurant")
    if restaurant:
        from renpos.api.guards import RESTAURANT_KEY
        frappe.defaults.set_user_default(RESTAURANT_KEY, restaurant, user)
    frappe.db.set_value("Ren Terminal", t.name, "last_login", now_datetime(), update_modified=False)
    access.audit("pin_login", pos_profile=t.pos_profile, reference=("Ren Terminal", t.name))
    return {"user": user, "full_name": frappe.utils.get_fullname(user)}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def grantable(doctype, txt, searchfield, start, page_len, filters):
    """Ren Staff form: the floors, rooms, tables or stations of the restaurant (object_name search)."""
    require_restaurant_user()
    object_type = (filters or {}).get("object_type")
    restaurant = (filters or {}).get("restaurant")
    if object_type not in ("Ren Floor", "Ren Room", "Ren Table", "Ren Station") or not restaurant:
        return []
    joins = {
        "Ren Floor": ("", "x.restaurant = %(r)s"),
        "Ren Room": ("JOIN `tabRen Floor` f ON f.name = x.floor", "f.restaurant = %(r)s"),
        "Ren Table": ("JOIN `tabRen Room` rm ON rm.name = x.room JOIN `tabRen Floor` f ON f.name = rm.floor",
                      "f.restaurant = %(r)s"),
        "Ren Station": ("JOIN `tabRen Floor` f ON f.name = x.floor", "f.restaurant = %(r)s"),
    }[object_type]
    return frappe.db.sql(f"""SELECT x.name, x.description FROM `tab{object_type}` x {joins[0]}
        WHERE {joins[1]} AND (x.name LIKE %(t)s OR IFNULL(x.description, '') LIKE %(t)s)
        ORDER BY x.description LIMIT %(start)s, %(len)s""",
        {"r": restaurant, "t": f"%{txt}%", "start": int(start), "len": int(page_len)})


def refresh_grant_labels(doc, method=None):
    """A floor / room / table / station got another name: the grants that give it show the new one."""
    if doc.has_value_changed("description"):
        frappe.db.sql("""UPDATE `tabRen Access Grant` SET description = %s
            WHERE object_type = %s AND object_name = %s""", (doc.description or doc.name, doc.doctype, doc.name))


# ─────────────────────────────────────────────
# Charging: what ERPNext needs besides the Ren Role
# ─────────────────────────────────────────────

CASHIER_ROLES = ("Accounts User", "Sales Manager")


def charging_gaps(user, restaurant):
    """
    Why someone whose Ren Role charges can't charge yet: the ERPNext rights
    on POS invoices, or not being in a POS Profile of the restaurant.
    [] = ready (or their role doesn't charge).
    """
    from renpos.api.guards import billing_profiles, restaurant_profiles
    from renpos.api.invoicing import get_invoice_doctype
    staff = frappe.db.get_value("Ren Staff", {"user": user, "restaurant": restaurant}, "name")
    role = frappe.db.get_value("Ren Staff", staff, "restaurant_role") if staff else None
    if not role or not cint(frappe.db.get_value("Ren Role", role, "take_payments")):
        return []
    gaps = []
    doctype = get_invoice_doctype()
    if not (frappe.has_permission(doctype, "create", user=user) and frappe.has_permission(doctype, "submit", user=user)
            and frappe.has_permission("POS Opening Entry", "read", user=user)):
        gaps.append(_("ERPNext roles to create POS invoices ({0})").format(", ".join(CASHIER_ROLES)))
    if not restaurant_profiles(restaurant):
        gaps.append(_("{0} has no POS Profile").format(restaurant))
    elif not billing_profiles(restaurant, user):
        gaps.append(_("being in a POS Profile of {0} (Applicable for Users)").format(restaurant))
    return gaps


@frappe.whitelist()
def staff_charging(staff):
    """Ren Staff form: what is missing for the person to charge."""
    doc = frappe.get_doc("Ren Staff", staff)
    doc.check_permission("read")
    return {"gaps": charging_gaps(doc.user, doc.restaurant),
            "can_fix": "System Manager" in frappe.get_roles()}


@frappe.whitelist(methods=["POST"])
def enable_charging(staff):
    """System Manager: give the ERPNext cashier roles and add the person to the restaurant's POS Profile."""
    if "System Manager" not in frappe.get_roles():
        raise frappe.PermissionError(_("Only a System Manager can give accounting roles"))
    from renpos.api.guards import billing_profiles, restaurant_profile
    doc = frappe.get_doc("Ren Staff", staff)
    frappe.get_doc("User", doc.user).add_roles(*CASHIER_ROLES)
    if not billing_profiles(doc.restaurant, doc.user):
        name = restaurant_profile(doc.restaurant)
        if not name:
            frappe.throw(_("{0} has no POS Profile").format(doc.restaurant))
        profile = frappe.get_doc("POS Profile", name)
        profile.append("applicable_for_users", {"user": doc.user})
        profile.save()
    return staff_charging(staff)
