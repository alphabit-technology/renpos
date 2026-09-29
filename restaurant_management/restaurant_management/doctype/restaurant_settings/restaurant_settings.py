# -*- coding: utf-8 -*-
# Copyright (c) 2021, Quantum Bit Core and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from restaurant_management.setup import install
from erpnext.stock.get_item_details import get_pos_profile


class RestaurantSettings(Document):
    def company(self):
        return frappe.defaults.get_user_default('company')

    def on_update(self):
        frappe.publish_realtime("update_settings")

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

    def get_floors(self):
        #restaurant_settings = frappe.get_single("Restaurant Settings")
        filters = {
            "company": frappe.defaults.get_user_default('company')
        }

        if not self.user_has_admin_role():
            floors_enabled = self.restaurant_access("Ren Floor")

            filters["name"] = ("in", floors_enabled)

        floors = frappe.get_all("Ren Floor",
                                "name,description", filters=filters)

        return floors

    def settings_data(self):
        company = self.company()
        profile = frappe.db.get_value(
            "User", frappe.session.user, "role_profile_name")
        #restaurant_settings = frappe.get_single("Restaurant Settings")
        tax_template = frappe.db.get_value("Sales Taxes and Charges Template", {
                                           "company": company})
        pos = self.pos_profile_data()

        def get_doc_permissions(d):
            return frappe.permissions.get_doc_permissions(frappe.new_doc(d))

        if pos.get("has_pos"):
            menu = frappe.db.get_value("Restaurant Menu", pos.get("pos").restaurant_menu, "name")
            menu_items = frappe.get_all("Restaurant Menu Item", filters=dict(
                parent=menu), fields=["item"]
            )
            groups_of_items = frappe.get_all("Item", "item_group", filters=dict(
                item_code=("in", [item.item for item in menu_items]))
            )

            parent_item_groups = frappe.get_all("Item Group", "parent_item_group",
              filters=dict(name=("in", [item.item_group for item in groups_of_items]))
            )

            items_groups = [item.item_group for item in groups_of_items] + [item.parent_item_group for item in parent_item_groups]
        else :
            menu = None
            menu_items = []
            items_groups = []

        return dict(
            pos=pos,
            permissions={
                'invoice': get_doc_permissions("Sales Invoice"),
                'order': get_doc_permissions("Table Order"),
                'Ren Floor': get_doc_permissions("Ren Floor"),
                'Ren Room': get_doc_permissions("Ren Room"),
                'Ren Table': get_doc_permissions("Ren Table"),
                'Ren Station': get_doc_permissions("Ren Station"),
                'Restaurant Menu': get_doc_permissions("Restaurant Menu"),
                'rooms_access': self.restaurant_access()
            },
            restrictions=self,
            exceptions=[
                item for item in self.restaurant_exceptions if item.role_profile == profile],
            lang=frappe.session.data.lang,
            order_item_editor_form=self.get_order_item_editor_form(),
            tax_template=frappe.get_doc(
                "Sales Taxes and Charges Template", tax_template) if tax_template else {},
            crm_settings=self.get_crm_settings(),
            allows_to_edit_item=frappe.get_all(
                "Status Order PC", "name", filters=dict(allows_to_edit_item=1)),
            menu=menu,
            menu_items=menu_items,
            items_groups=items_groups,
            floors=self.get_floors()
        )

    def get_crm_settings(self):
        return dict(
            crm_floor=self.restaurant_access("Ren Floor", dict(is_crm=1)),
            crm_room=self.restaurant_access("Ren Room", dict(is_crm=1)),
            crm_table=self.restaurant_access("Ren Table", dict(is_crm=1))
        )

    def pos_profile_data(self):
        pos_profile_name = self.get_current_pos_profile_name()

        return dict(
            has_pos=pos_profile_name is not None,
            pos=frappe.get_doc("POS Profile", pos_profile_name) if pos_profile_name is not None else None
        )

    def get_order_item_editor_form(self):
        return frappe.get_doc("Desk Form", "order-item-editor")

    def get_current_pos_profile_name(self):
        from restaurant_management.api.guards import current_pos_profile
        return current_pos_profile()

    def has_access_to_room(self, room):
        return len(self.restaurant_access("Ren Room", dict(object_name=room))) > 0

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


@frappe.whitelist()
def reinstall():
    from restaurant_management.api.guards import require_system_manager
    require_system_manager()
    return install.after_install()
