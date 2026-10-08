# -*- coding: utf-8 -*-
# renpos/api/guards.py
#
# Server-side access checks shared by every whitelisted endpoint.
# The React client hides actions the user can't perform, but the
# server is the only place where permissions are actually enforced.

import frappe
from frappe import _
from frappe.utils import cint, flt

RESTAURANT_ROLES = {"Restaurant User", "Restaurant Manager", "System Manager"}
MANAGER_ROLES = {"Restaurant Manager", "System Manager"}


def _roles():
    return set(frappe.get_roles(frappe.session.user))


def is_manager():
    return frappe.session.user == "Administrator" or bool(_roles() & MANAGER_ROLES)


def require_restaurant_user():
    """Any restaurant endpoint: logged-in user with a restaurant role."""
    if frappe.session.user == "Guest":
        raise frappe.PermissionError(_("Login required"))

    if frappe.session.user != "Administrator" and not (_roles() & RESTAURANT_ROLES):
        raise frappe.PermissionError(_("You don't have access to the restaurant"))


def get_order(order_name, ptype="write"):
    """
    Load a Ren Order for the restaurant API: role, POS Profile, the table
    (restaurant and the person's tables) and other people's orders
    (see api/access.py). Changes go through the API only (see RenOrder.validate).
    """
    require_restaurant_user()
    order = frappe.get_doc("Ren Order", order_name)
    order.check_permission("read")
    if not is_manager() and not works_at(order.get("restaurant") or profile_restaurant(order.pos_profile)):
        raise frappe.PermissionError(_("This order belongs to another restaurant"))
    from renpos.api.access import check_order_access
    check_order_access(order, write=ptype != "read")
    frappe.flags.ren_order_api = True
    return order


def user_pos_permissions(pos_profile):
    """
    Effective price-editing permissions for the current user.
    POS Profile flags apply to everyone; managers may always change
    rate and discount.

    Note: api.pos.get_user_permissions() queries fields that don't exist
    on the "Ren Access Grant" child table, so it is not used here.
    """
    from renpos.api.access import role_of
    role = role_of(pos_profile=pos_profile)
    return {
        "allow_discount_change": 1 if flt(role.max_discount) > 0 else 0,
        "allow_rate_change": cint(role.change_price),
        "max_discount": flt(role.max_discount),
        "is_manager": is_manager(),
    }


# ─────────────────────────────────────────────
# Where the person works, and with which POS Profile
# ─────────────────────────────────────────────
#
#   Ren Staff     a person at a restaurant: role and access (floors, rooms,
#                 tables, stations). "Work at" picks the restaurant when the
#                 person works at several (RESTAURANT_KEY).
#   POS Profile   only for charging and pricing: company, warehouse, price
#                 list, taxes, payment modes, the register. Cashiers are the
#                 users listed in it ("Applicable for Users"). Waiters don't
#                 need one: they take orders with the restaurant's profile.

RESTAURANT_KEY = "ren_current_restaurant"


def _is_manager_user(user):
    return user == "Administrator" or bool(set(frappe.get_roles(user)) & MANAGER_ROLES)


def _memo(key, fn):
    """Per-request cache: these run many times per call (only in web requests, which start clean)."""
    if getattr(frappe.local, "request", None) is None:
        return fn()
    cache = getattr(frappe.local, "ren_ctx", None)
    if cache is None:
        cache = frappe.local.ren_ctx = {}
    if key not in cache:
        cache[key] = fn()
    return cache[key]


def clear_context():
    frappe.local.ren_ctx = {}


def staff_restaurants(user=None):
    """The active restaurants the person works at (default first). Managers: every active one."""
    user = user or frappe.session.user

    def load():
        if _is_manager_user(user):
            mine = frappe.get_all("Ren Staff", filters={"user": user, "enabled": 1},
                                  fields=["restaurant", "is_default"])
            first = {r.restaurant for r in mine if cint(r.is_default)}
            names = frappe.get_all("Ren Restaurant", filters={"active": 1}, pluck="name", order_by="restaurant_name asc")
            return sorted(names, key=lambda n: n not in first)
        rows = frappe.db.sql("""SELECT s.restaurant FROM `tabRen Staff` s
            JOIN `tabRen Restaurant` r ON r.name = s.restaurant
            WHERE s.user = %s AND IFNULL(s.enabled, 0) = 1 AND IFNULL(r.active, 0) = 1
            ORDER BY s.is_default DESC, r.restaurant_name ASC""", user)
        return [r[0] for r in rows]

    return _memo(("restaurants", user), load)


def works_at(restaurant, user=None):
    return bool(restaurant) and restaurant in staff_restaurants(user)


def current_restaurant(user=None):
    """The restaurant the person works at now: the one chosen in "Work at", else their default."""
    user = user or frappe.session.user

    def load():
        mine = staff_restaurants(user)
        chosen = frappe.defaults.get_user_default(RESTAURANT_KEY, user)
        if chosen and chosen in mine:
            return chosen
        return mine[0] if mine else None

    return _memo(("restaurant", user), load)


def restaurant_profiles(restaurant):
    """The restaurant's enabled POS Profiles, its own (Ren Restaurant.pos_profile) first."""
    if not restaurant:
        return []
    own = frappe.db.get_value("Ren Restaurant", restaurant, "pos_profile")
    names = frappe.get_all("POS Profile", filters={"ren_restaurant": restaurant, "disabled": 0},
                           pluck="name", order_by="creation asc")
    return sorted(names, key=lambda n: n != own)


def restaurant_profile(restaurant):
    """The profile orders are taken (and priced) with when the person doesn't charge."""
    profiles = restaurant_profiles(restaurant)
    return profiles[0] if profiles else None


def billing_profiles(restaurant=None, user=None):
    """The POS Profiles of the restaurant the person charges with (listed in them; managers: all)."""
    user = user or frappe.session.user
    restaurant = restaurant or current_restaurant(user)
    profiles = restaurant_profiles(restaurant)
    if _is_manager_user(user):
        return profiles
    listed = frappe.get_all("POS Profile User", filters={"parenttype": "POS Profile", "user": user,
                                                         "parent": ["in", profiles or [""]]},
                            fields=["parent", "default"])
    order = {p: i for i, p in enumerate(profiles)}
    listed.sort(key=lambda r: (not cint(r.default), order.get(r.parent, 99)))
    return [r.parent for r in listed]


def current_pos_profile(user=None, company=None):
    """
    The POS Profile the person works with in their restaurant now: the one of
    their open register, else one they charge with (default first), else the
    restaurant's own (waiters). None when they work at no restaurant.
    """
    user = user or frappe.session.user

    def load():
        restaurant = current_restaurant(user)
        if not restaurant:
            return None
        profiles = restaurant_profiles(restaurant)
        if not profiles:
            return None
        opened = frappe.get_all("POS Opening Entry", filters={
            "user": user, "status": "Open", "docstatus": 1, "pos_profile": ["in", profiles]},
            pluck="pos_profile", order_by="period_start_date desc", limit=1)
        if opened:
            return opened[0]
        mine = billing_profiles(restaurant, user)
        return mine[0] if mine else profiles[0]

    return _memo(("profile", user), load)


def profile_restaurant(pos_profile):
    return frappe.db.get_value("POS Profile", pos_profile, "ren_restaurant") if pos_profile else None


def check_pos_profile_access(pos_profile):
    """The profile belongs to a restaurant the person works at (orders, catalog, printing)."""
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))
    if is_manager():
        return
    if not works_at(profile_restaurant(pos_profile)):
        raise frappe.PermissionError(_("You don't work at the restaurant of POS Profile {0}").format(pos_profile))


def check_billing_profile(pos_profile):
    """Charging with a profile: the person is listed in it (ERPNext's rule). Managers: any."""
    check_pos_profile_access(pos_profile)
    if is_manager():
        return
    if not frappe.db.exists("POS Profile User", {"parenttype": "POS Profile", "parent": pos_profile,
                                                 "user": frappe.session.user}):
        raise frappe.PermissionError(
            _("You don't charge with POS Profile {0}: a manager adds cashiers in its Applicable for Users").format(
                pos_profile))


def effective_price_list(pos_profile):
    """
    Selling price list used everywhere (catalog, validation, invoice):
    the restaurant's default_price_list when set, else the POS Profile's.
    Must match Ren Restaurant.get_data() -> pos_profile.selling_price_list.
    """
    profile_pl, restaurant = frappe.db.get_value(
        "POS Profile", pos_profile, ["selling_price_list", "ren_restaurant"]
    ) or (None, None)
    if restaurant:
        pl = frappe.db.get_value("Ren Restaurant", restaurant, "default_price_list")
        if pl:
            return pl
    return profile_pl


def require_system_manager():
    """Like frappe.only_for("System Manager"), but also enforced in tests."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        raise frappe.PermissionError(_("Only a System Manager can do this"))
