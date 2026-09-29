"""
Restaurant Init API
====================
Single endpoint to bootstrap the POS frontend with everything it needs.

Usage:
  frappe.call({
    method: "erpnext_restaurant.api.restaurant.init_restaurant",
    args: { pos_profile: "Restaurant POS" }
  }).then(r => {
    const { restaurant, menu, floors, settings } = r.message;
    // Initialize POS with all data
  });
"""

import frappe
from restaurant_management.api.guards import require_restaurant_user
from frappe import _


def on_pos_profile_change(doc, method):
  frappe.publish_realtime("on_pos_profile_change", {})

@frappe.whitelist()
def init_restaurant(pos_profile=None):
    """
    Bootstrap the restaurant POS — single round-trip.

    Resolves: POS Profile → Restaurant → Menu + Floors + Settings

    Args:
        pos_profile: POS Profile name. If not provided, auto-detects
                     from the current user's default POS Profile.

    Returns:
        {
            "restaurant": { ...restaurant doc fields },
            "menu": {
                "name": "Main Menu",
                "items": [ ...items with prices ],
                "categories": ["Appetizers", "Main Course", ...]
            },
            "floors": [
                {
                    "name": "Ground Floor",
                    "rooms": [
                        {
                            "name": "Main Hall",
                            "tables": [
                                { "name": "T-01", "capacity": 4, ... },
                                ...
                            ]
                        }
                    ]
                }
            ],
            "settings": {
                "restrict_tables_by_owner": false,
                "shortcuts": { ... },
                "permissions": { ... }
            },
            "pos_profile": { ...relevant fields },
            "user": { "name": "...", "full_name": "..." }
        }
    """
    require_restaurant_user()
    # ── Resolve POS Profile ──
    if not pos_profile:
        pos_profile = _get_default_pos_profile()

    if not pos_profile:
        frappe.throw(
            _("No POS Profile found, need assign a POS Profile to your user."),
            title=_("POS Setup Required"),
        )

    from restaurant_management.api.guards import check_pos_profile_access
    check_pos_profile_access(pos_profile)

    pos_doc = frappe.get_cached_doc("POS Profile", pos_profile)

    # ── Resolve Restaurant ──
    restaurant_name = pos_doc.get("ren_restaurant")
    if not restaurant_name:
        frappe.throw(
            _("POS Profile {0} has no Restaurant assigned.").format(frappe.bold(pos_doc.get("ren_restaurant"))),
            title=_("Restaurant Not Configured"),
        )

    rest_doc = frappe.get_cached_doc("Ren Restaurant", restaurant_name)
    if not rest_doc.active:
        frappe.throw(
            _("Restaurant {0} is not active.").format(frappe.bold(restaurant_name)),
        )

    data = rest_doc.get_data()

    # Lets the client log which backend it is talking to (see RestaurantContext).
    from restaurant_management.api.invoicing import get_invoice_doctype
    data["_server"] = {
        "version": "fase0-2026-09-28",
        "invoice_doctype": get_invoice_doctype(),
        "pos_profile": pos_profile,
        "user": frappe.session.user,
    }
    return data

# ─── Helpers ──────────────────────────────────────────────────────────

def _get_default_pos_profile():
    """Auto-detect POS Profile for current user."""
    user = frappe.session.user

    # 1. User's default POS Profile
    pos_profile = frappe.db.get_value(
        "POS Profile User",
        {"user": user, "default": 1},
        "parent",
    )
    if pos_profile:
        return pos_profile

    # 2. Any POS Profile assigned to this user
    pos_profile = frappe.db.get_value(
        "POS Profile User",
        {"user": user},
        "parent",
    )
    if pos_profile:
        return pos_profile

    return None


@frappe.whitelist()
def switch_menu(restaurant, menu_name):
    """
    Switch the active menu (e.g. Lunch → Dinner).
    Can be called from the POS UI.
    """
    require_restaurant_user()
    rest_doc = frappe.get_doc("Ren Restaurant", restaurant)

    # Validate menu belongs to this restaurant
    menu_restaurant = frappe.db.get_value("Restaurant Menu", menu_name, "restaurant")
    if menu_restaurant != restaurant:
        frappe.throw(
            _("Menu {0} does not belong to restaurant {1}").format(
                frappe.bold(menu_name), frappe.bold(restaurant)
            )
        )

    rest_doc.active_menu = menu_name
    rest_doc.save(ignore_permissions=False)

    return {"active_menu": menu_name}


@frappe.whitelist()
def get_available_menus(restaurant):
    """Get all menus for a restaurant (for menu switcher UI)."""
    require_restaurant_user()
    return frappe.get_all(
        "Restaurant Menu",
        filters={"restaurant": restaurant, "enabled": 1},
        fields=["name", "menu_name", "description", "total_items"],
        order_by="menu_name asc",
    )