# -*- coding: utf-8 -*-
# restaurant_management/api/guards.py
#
# Server-side access checks shared by every whitelisted endpoint.
# The React client hides actions the user can't perform, but the
# server is the only place where permissions are actually enforced.

import frappe
from frappe import _
from frappe.utils import cint

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


def check_pos_profile_access(pos_profile):
    """
    Same rule ERPNext's POS uses: a user may use a POS Profile when listed
    in its "Applicable for Users" table, or when the table is empty.
    Managers may use any profile.
    """
    if not pos_profile:
        frappe.throw(_("POS Profile is required"))

    if is_manager():
        return

    users = frappe.get_all(
        "POS Profile User",
        filters={"parent": pos_profile, "parenttype": "POS Profile"},
        pluck="user",
    )
    if users and frappe.session.user not in users:
        raise frappe.PermissionError(
            _("You are not allowed to use POS Profile {0}").format(pos_profile)
        )


def get_order(order_name, ptype="write"):
    """Load a Table Order after checking role, doctype permission and POS Profile."""
    require_restaurant_user()
    order = frappe.get_doc("Table Order", order_name)
    order.check_permission(ptype)
    check_pos_profile_access(order.pos_profile)
    return order


def user_pos_permissions(pos_profile):
    """
    Effective price-editing permissions for the current user.
    POS Profile flags apply to everyone; managers may always change
    rate and discount.

    Note: api.pos.get_user_permissions() queries fields that don't exist
    on the "Restaurant Permission" child table, so it is not used here.
    """
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    manager = is_manager()
    return {
        "allow_discount_change": 1 if manager else cint(profile.allow_discount_change),
        "allow_rate_change": 1 if manager else cint(profile.allow_rate_change),
        "is_manager": manager,
    }


def current_pos_profile(user=None, company=None):
    """
    Name of the POS Profile the user works with, without requiring read
    permission on POS Profile (waiters with only "Restaurant User" don't
    have it). Same order ERPNext's POS uses: the user's default profile,
    any profile assigned to the user, then a profile with no assigned
    users in the company.
    """
    user = user or frappe.session.user
    rows = frappe.db.sql(
        """
        SELECT pu.parent FROM `tabPOS Profile User` pu
        INNER JOIN `tabPOS Profile` p ON p.name = pu.parent
        WHERE pu.parenttype = 'POS Profile' AND pu.user = %s AND IFNULL(p.disabled, 0) = 0
        ORDER BY pu.`default` DESC, p.modified DESC
        LIMIT 1
        """,
        user,
    )
    if rows:
        return rows[0][0]

    company = company or frappe.defaults.get_user_default("company") \
        or frappe.defaults.get_global_default("company")
    rows = frappe.db.sql(
        """
        SELECT p.name FROM `tabPOS Profile` p
        WHERE IFNULL(p.disabled, 0) = 0 AND (%(company)s IS NULL OR p.company = %(company)s)
          AND NOT EXISTS (SELECT 1 FROM `tabPOS Profile User` pu
                          WHERE pu.parent = p.name AND pu.parenttype = 'POS Profile')
        ORDER BY p.modified DESC
        LIMIT 1
        """,
        {"company": company},
    )
    return rows[0][0] if rows else None


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
