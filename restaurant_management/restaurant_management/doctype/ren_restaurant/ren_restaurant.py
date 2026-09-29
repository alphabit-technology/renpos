# Copyright (c) 2026, Quantum Bit Core and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from erpnext.stock.get_item_details import get_pos_profile


def get_doc_permissions(doctype):
  return frappe.permissions.get_doc_permissions(frappe.new_doc(doctype))

class RenRestaurant(Document):
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
        user = frappe.session.user

        if user == "Administrator":
            return (True)

        roles = frappe.get_roles(user)
        admin_roles = ["System Manager", "Restaurant Manager"]

        a_set = set(admin_roles)
        b_set = set(roles)

        if len(a_set.intersection(b_set)) > 0:
            return (True)

        return (False)

    def get_data(self, pos_profile=None):
        # ── Resolve POS Profile ──
        if not pos_profile:
            pos_profile = self.get_current_pos_profile_name()

        pos_doc = frappe.get_cached_doc("POS Profile", pos_profile)

        # ── Load Menu ──
        menu_data = self.load_menu(pos_profile)

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
                "branch": self.branch,
                "logo": self.logo,
                "active_menu": frappe.db.get_value("Restaurant Menu",
                    filters=dict(
                        company=self.company,
                        is_default=1,
                        enabled=1
                    ),
                    fieldname="name"
                )
            },
            "menu": menu_data,
            "floors": floors_data,
            "settings": settings,
            "pos_profile": pos_summary,
            "user": user_info,
            "permissions": {
                "invoice": get_doc_permissions("Sales Invoice"),
                "order": get_doc_permissions("Table Order"),
                "Ren Floor": get_doc_permissions("Ren Floor"),
                "Ren Room": get_doc_permissions("Ren Room"),
                "Ren Table": get_doc_permissions("Ren Table"),
                "Ren Station": get_doc_permissions("Ren Station"),
                "Restaurant Menu": get_doc_permissions("Restaurant Menu"),
                "rooms_access": self.restaurant_access(),
            },
        }

    def load_menu(self, pos_profile):
        """Load active menu items with proper pricing."""
        if not self.active_menu:
            return {"name": None, "items": [], "categories": []}

        menu_doc = frappe.get_cached_doc("Restaurant Menu", self.active_menu)
        if not menu_doc.enabled:
            return {"name": menu_doc.name, "items": [], "categories": []}

        # Get enabled item codes from menu
        menu_item_codes = [row.item for row in menu_doc.items if row.enabled]
        if not menu_item_codes:
            return {"name": menu_doc.menu_name, "items": [], "categories": []}

        # Fetch item data
        item_fields = [
            "name as item_code", "item_name", "item_group",
            "image", "standard_rate as price_list_rate", "description",
        ]

        meta = frappe.get_meta("Item")
        if meta.has_field("item_type"):
            item_fields.append("item_type")
        if meta.has_field("is_available"):
            item_fields.append("is_available")

        items = frappe.get_all(
            "Item",
            filters={"name": ["in", menu_item_codes], "disabled": 0},
            fields=item_fields,
            order_by="item_name asc",
        )

        # Override prices from Price List
        price_list = self.default_price_list or frappe.db.get_value(
            "POS Profile", pos_profile, "selling_price_list"
        )

        if price_list and items:
            prices = {
                r.item_code: r.price_list_rate
                for r in frappe.get_all(
                    "Item Price",
                    filters={
                        "item_code": ["in", menu_item_codes],
                        "price_list": price_list,
                        "selling": 1,
                    },
                    fields=["item_code", "price_list_rate"],
                )
            }
            for item in items:
                if item["item_code"] in prices:
                    item["price_list_rate"] = prices[item["item_code"]]

        # Auto-compute categories from item groups
        categories = sorted(set(
            item["item_group"] for item in items if item.get("item_group")
        ))

        return {
            "name": menu_doc.menu_name,
            "items": items,
            "categories": categories,
        }

    def build_settings(self):
        """Extract operational settings and resolve user permissions."""
        user = frappe.session.user
        user_roles = set(frappe.get_roles(user))

        # Check if user has any permission exception
        can_bypass_tables = False
        can_bypass_orders = False

        if hasattr(self, "permission_exceptions"):
            for exc in self.permission_exceptions:
                if exc.user == user or exc.role in user_roles:
                    if exc.bypass_table_restriction:
                        can_bypass_tables = True
                    if exc.bypass_order_restriction:
                        can_bypass_orders = True

        return {
            "restrict_tables_by_owner": self.restrict_tables_by_owner and not can_bypass_tables,
            "restrict_orders_by_owner": self.restrict_orders_by_owner and not can_bypass_orders,
            "allow_multiple_pending_orders": self.allow_multiple_pending_orders,
            "restriction_color": self.restriction_color or "",
            "shortcuts": {
                "new_order": self.shortcut_new_order,
                "pay": self.shortcut_pay,
                "transfer": self.shortcut_transfer,
                "change_status": self.shortcut_change_status,
            },
            "permissions": {
                "can_bypass_tables": can_bypass_tables,
                "can_bypass_orders": can_bypass_orders,
                "is_manager": "Restaurant Manager" in user_roles,
            },
            "enable_kds": self.enable_kds,
            "print_format": self.print_format or "",
            "kitchen_print_format": self.kitchen_print_format or "",
        }

    def restaurant_access(self, target_type=None, extra_filters=None):
        pos_profile_name = self.get_current_pos_profile_name()
        permission_parent = frappe.db.get_value("POS Profile User",
            filters=dict(
                parenttype="POS Profile",
                parent=pos_profile_name,
                user=frappe.session.user
            ),
            fieldname="name"
        )

        filters = dict(
            parenttype="Restaurant Permission Manage",
            parent=permission_parent,
        )
        if extra_filters:
            filters.update(extra_filters)

        permissions = frappe.get_all("Restaurant Permission",
            fields=["object_type", "object_name"],
            filters=filters
        ) if permission_parent else []

        # ... rest of the method
        if not permissions:
            return set()

        # 3. If no target type, return raw object names
        if not target_type:
            return set(p.object_name for p in permissions)

        # 4. Group by type
        granted = {}
        for p in permissions:
            granted.setdefault(p.object_type, set()).add(p.object_name)

        # 5. Resolve cascade based on what we're asking for
        return self._resolve_access(target_type, granted)


    def _resolve_access(self, target_type, granted):
        """
        Resolve hierarchical permissions.
        granted = { 'Ren Floor': {'FLOOR-1'}, 'Ren Room': {'ROOM-2'}, 'Ren Table': {'TABLE-5'} }
        """
        result = set()

        floors = granted.get("Ren Floor", set())
        rooms = granted.get("Ren Room", set())
        tables = granted.get("Ren Table", set())
        stations = granted.get("Ren Station", set())

        if target_type == "Ren Floor":
            result.update(floors)
            if rooms:
                result.update(
                    frappe.get_all("Ren Room", pluck="floor",
                        filters={"name": ("in", list(rooms))})
                )
            if tables:
                rooms_from_tables = frappe.get_all("Ren Table", pluck="room",
                    filters={"name": ("in", list(tables))})
                if rooms_from_tables:
                    result.update(
                        frappe.get_all("Ren Room", pluck="floor",
                            filters={"name": ("in", rooms_from_tables)})
                    )
            # Floors that contain granted stations
            if stations:
                result.update(
                    frappe.get_all("Ren Station", pluck="floor",
                        filters={"name": ("in", list(stations))})
                )

        elif target_type == "Ren Room":
            # Direct room assignments
            result.update(rooms)
            # All rooms on granted floors
            if floors:
                result.update(
                    frappe.get_all("Ren Room", pluck="name",
                        filters={"floor": ("in", list(floors))})
                )
            # Rooms that contain granted tables (for visibility, not full access)
            if tables:
                result.update(
                    frappe.get_all("Ren Table", pluck="room",
                        filters={"name": ("in", list(tables))})
                )

        elif target_type == "Ren Table":
            # Direct table assignments
            result.update(tables)
            # All tables in granted rooms
            if rooms:
                result.update(
                    frappe.get_all("Ren Table", pluck="name",
                        filters={"room": ("in", list(rooms))})
                )
            # All tables on granted floors (floor → rooms → tables)
            if floors:
                rooms_on_floors = frappe.get_all("Ren Room", pluck="name",
                    filters={"floor": ("in", list(floors))})
                if rooms_on_floors:
                    result.update(
                        frappe.get_all("Ren Table", pluck="name",
                            filters={"room": ("in", rooms_on_floors)})
                    )

        elif target_type == "Ren Station":
            # Direct station assignments
            result.update(stations)
            # All stations on granted floors
            if floors:
                result.update(
                    frappe.get_all("Ren Station", pluck="name",
                        filters={"floor": ("in", list(floors))})
                )

        return result


    def get_current_pos_profile_name(self):
        pp = get_pos_profile(frappe.defaults.get_user_default('company'))
        return pp.name if pp else None