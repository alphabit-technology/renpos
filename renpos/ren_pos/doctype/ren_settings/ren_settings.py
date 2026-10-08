# -*- coding: utf-8 -*-
# Copyright (c) 2021, Quantum Bit Core and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RenSettings(Document):
    def user_has_admin_role(self):
        """Sees the whole floor plan: managers, and roles with "Every table of the restaurant"."""
        user = frappe.session.user
        if user == "Administrator":
            return True
        roles = set(frappe.get_roles(user))
        if roles & {"System Manager", "Restaurant Manager"}:
            return True
        from renpos.api.access import can
        return "Restaurant User" in roles and bool(can("all_tables")) and not self.has_layout_grants()

    def has_layout_grants(self):
        """Some floor, room or table is assigned to the person (stations don't count)."""
        parents = self.permission_parents()
        return bool(parents) and bool(frappe.db.exists("Ren Access Grant", {
            "parenttype": "Ren Staff", "parent": ["in", parents],
            "object_type": ["in", ["Ren Floor", "Ren Room", "Ren Table"]]}))

    def permission_parents(self, user=None, restaurant=None):
        """The person's Ren Staff record at the restaurant they work at now (its grants count)."""
        from renpos.api.guards import current_restaurant
        user = user or frappe.session.user
        restaurant = restaurant or current_restaurant(user)
        if not restaurant:
            return []
        return frappe.get_all("Ren Staff", filters={"user": user, "restaurant": restaurant, "enabled": 1},
                              pluck="name")

    def has_access_to_room(self, room):
        return len(self.restaurant_access("Ren Room", dict(object_name=room))) > 0

    def restaurant_access(self, target_type=None, extra_filters=None):
        permission_parents = self.permission_parents()

        filters = dict(
            parenttype="Ren Staff",
            parent=("in", permission_parents),
        )
        if extra_filters:
            filters.update(extra_filters)

        permissions = frappe.get_all("Ren Access Grant",
            fields=["object_type", "object_name"],
            filters=filters
        ) if permission_parents else []

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
            # only the stations assigned one by one (a floor doesn't give its kitchen)
            result.update(stations)

        return result
