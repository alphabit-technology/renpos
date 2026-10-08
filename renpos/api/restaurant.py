"""
POS bootstrap: init_restaurant returns everything the POS needs to start
(restaurant, menu, floors, settings, the person's access). Also the
restaurants someone works at and the switch between them ("Work at").
"""

import frappe
from renpos.api.guards import require_restaurant_user
from frappe import _


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
    from renpos.api.guards import current_restaurant, current_pos_profile, restaurant_profiles
    # ── Where the person works (Ren Staff), and the profile they work with there ──
    restaurant_name = current_restaurant()
    if not restaurant_name:
        frappe.throw(
            _("You don't work at any restaurant yet. A manager adds you in Ren Staff."),
            title=_("Restaurant setup required"),
        )
    if not restaurant_profiles(restaurant_name):
        frappe.throw(
            _("Restaurant {0} has no POS Profile: create one with this restaurant (POS Profile > Restaurant).").format(
                frappe.bold(restaurant_name)),
            title=_("Restaurant setup required"),
        )
    pos_profile = current_pos_profile()

    rest_doc = frappe.get_cached_doc("Ren Restaurant", restaurant_name)
    if not rest_doc.active:
        frappe.throw(
            _("Restaurant {0} is not active.").format(frappe.bold(restaurant_name)),
        )

    data = rest_doc.get_data()

    # Lets the client log which backend it is talking to (see RestaurantContext).
    from renpos.api.invoicing import get_invoice_doctype
    # the person's Ren Role (hide actions / ask for a manager PIN)
    from renpos.api.access import role_of, has_pin
    data["access"] = {**role_of(pos_profile=pos_profile), "has_pin": has_pin()}
    data["_server"] = {
        "version": "fase0-2026-09-28",
        "invoice_doctype": get_invoice_doctype(),
        "pos_profile": pos_profile,
        "user": frappe.session.user,
    }
    return data

# ─── Where the person works ───────────────────────────────────────────

@frappe.whitelist()
def my_restaurants():
    """The restaurants the person works at (Ren Staff): to switch between them in "Work at"."""
    require_restaurant_user()
    from renpos.api.guards import current_restaurant, staff_restaurants
    current = current_restaurant()
    out = [{"restaurant": r, "current": r == current,
            "restaurant_name": frappe.db.get_value("Ren Restaurant", r, "restaurant_name") or r}
           for r in staff_restaurants()]
    out.sort(key=lambda b: (not b["current"], b["restaurant_name"]))
    return out


@frappe.whitelist(methods=["POST"])
def switch_restaurant(restaurant):
    """Work at another restaurant (one of my_restaurants): the POS loads it from now on."""
    require_restaurant_user()
    from renpos.api.guards import RESTAURANT_KEY, works_at, clear_context
    if not works_at(restaurant):
        raise frappe.PermissionError(_("You don't work at {0}").format(restaurant))
    frappe.defaults.set_user_default(RESTAURANT_KEY, restaurant)
    clear_context()
    return {"restaurant": restaurant}

