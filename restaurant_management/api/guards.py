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
