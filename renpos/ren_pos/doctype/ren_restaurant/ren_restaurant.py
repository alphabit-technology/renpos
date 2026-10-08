# Copyright (c) 2026, Quantum Bit Core and contributors
# For license information, please see license.txt

import frappe
from renpos.api.menus import resolve_menu
from renpos.api.delivery import takes_phone_orders
from frappe import _
from frappe.model.document import Document


def get_doc_permissions(doctype):
  return frappe.permissions.get_doc_permissions(frappe.new_doc(doctype))

class RenRestaurant(Document):
    def validate(self):
        self.validate_delivery()

    def validate_delivery(self):
        from renpos.api.access import restaurant_of_table
        from renpos.api.delivery import invalid_zip_patterns
        for field in ("delivery_table", "pickup_table"):
            table = self.get(field)
            if table and restaurant_of_table(table) not in (None, self.name):
                frappe.throw(_("{0}: table {1} belongs to another restaurant").format(
                    _(self.meta.get_label(field)), table))
        for z in self.get("delivery_zones") or []:
            bad = invalid_zip_patterns(z.zip_codes)
            if bad:
                frappe.throw(_("Zone {0}: {1} isn't a ZIP code (5 digits) or a prefix like 021*").format(
                    frappe.bold(z.zone_name), ", ".join(bad)))
        if self.delivery and not [z for z in self.get("delivery_zones") or [] if z.active]:
            frappe.msgprint(_("Add the delivery zones (the ZIP codes this restaurant delivers to)"),
                            indicator="orange", alert=True)

    def load_floors(self):
        filters = {
            "restaurant": self.name
        }

        if not self.user_has_admin_role():
            floors_enabled = self.restaurant_access("Ren Floor")

            filters["name"] = ("in", floors_enabled)

        return frappe.get_all(
            "Ren Floor",
            filters=filters,
            fields=["name", "floor_number", "description"],
            order_by="floor_number asc",
        )
        
    def user_has_admin_role(self):
        """Sees the whole floor plan: managers, and roles with "Every table of the restaurant"."""
        return frappe.get_single("Ren Settings").user_has_admin_role()

    def get_data(self, pos_profile=None):
        # ── Resolve POS Profile ──
        if not pos_profile:
            pos_profile = self.get_current_pos_profile_name()

        pos_doc = frappe.get_cached_doc("POS Profile", pos_profile)

        # ── Load Menu ──

        # ── Load Floors → Rooms → Tables ──
        floors_data = self.load_floors()

        # ── Build Settings ──
        settings = self.build_settings()

        # ── Build POS Profile summary ──
        pos_summary = {
            "name": pos_doc.name,
            "company": pos_doc.company,
            "warehouse": pos_doc.warehouse,
            "selling_price_list": self.default_price_list or pos_doc.selling_price_list,
            "currency": pos_doc.currency,
            "write_off_account": pos_doc.write_off_account,
        }

        # ── User info ──
        user = frappe.session.user
        user_info = {
            "name": user,
            "full_name": frappe.db.get_value("User", user, "full_name") or user,
        }

        return {
            "restaurant": {
                "name": self.name,
                "restaurant_name": self.restaurant_name,
                "company": self.company,
                "logo": self.logo,
                # the restaurant's active menu, else the company's default (enabled ones only)
                "active_menu": (resolve_menu(restaurant=self.name) or {}).get("name")
            },
            "floors": floors_data,
            "settings": settings,
            "delivery": {"phone_orders": takes_phone_orders()},
            "pos_profile": pos_summary,
            "user": user_info,
            "permissions": {
                "invoice": get_doc_permissions("Sales Invoice"),
                "order": get_doc_permissions("Ren Order"),
                "Ren Floor": get_doc_permissions("Ren Floor"),
                "Ren Room": get_doc_permissions("Ren Room"),
                "Ren Table": get_doc_permissions("Ren Table"),
                "Ren Station": get_doc_permissions("Ren Station"),
                "Ren Menu": get_doc_permissions("Ren Menu"),
                "rooms_access": self.restaurant_access(),
            },
        }

    def build_settings(self):
        """Operational settings the POS reads."""
        return {"table_service": self.table_service or "Own tables"}

    def restaurant_access(self, target_type=None, extra_filters=None):
        """
        What the person was granted (one rule for the whole app): the grants of
        every POS Profile of this restaurant they are listed in add up, with
        floor -> rooms -> tables / centers cascading. See Ren Settings.
        """
        return frappe.get_single("Ren Settings").restaurant_access(target_type, extra_filters)

    def get_current_pos_profile_name(self):
        from renpos.api.guards import current_pos_profile
        return current_pos_profile()