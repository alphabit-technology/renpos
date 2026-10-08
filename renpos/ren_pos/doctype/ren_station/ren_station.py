import frappe
from frappe import _
from renpos.ren_pos.doctype.ren_base import RenBase


class RenStation(RenBase):
    def get_obj_data(self):
        fields = ("name,description,orders_count,data_style,min_size,color,shape,floor")
        data = self.get_data(fields)

        return data

    def get_station_data(self):
        fields = ("name,description,identifier,orders_count,"
                  "data_style,group_items_by_order,min_size,current_user,color,"
                  "restricted_to_rooms,restricted_to_tables,floor")
        data = self.get_data(fields)
        data["working_statuses"] = self.working_statuses
        data["items_group"] = self._items_group
        data["restricted_rooms"] = self.restricted_rooms
        data["restricted_tables"] = self.restricted_tables
        return data

    @property
    def orders_count(self):
        """Orders with something waiting at this station (floor plan badge)."""
        return len({r.parent for r in self.queue_items()})

    def origins(self):
        """(rooms, tables) the station is limited to (None: not limited that way)."""
        rooms = [r.room for r in self.get("restricted_rooms") or [] if r.room] \
            if frappe.utils.cint(self.get("restricted_to_rooms")) else None
        tables = [t.table for t in self.get("restricted_tables") or [] if t.table] \
            if frappe.utils.cint(self.get("restricted_to_tables")) else None
        return rooms, tables

    def origin_condition(self, alias="o"):
        """SQL (condition, values) for orders of its rooms / tables, or None when it takes every room."""
        rooms, tables = self.origins()
        if rooms is None and tables is None:
            return None
        parts, values = [], {}
        if rooms is not None:
            parts.append(f"{alias}.room IN %(st_rooms)s")
            values["st_rooms"] = rooms or ["__none__"]
        if tables is not None:
            parts.append(f"{alias}.`table` IN %(st_tables)s")
            values["st_tables"] = tables or ["__none__"]
        return "(" + " OR ".join(parts) + ")", values

    def takes_order_from(self, room, table):
        rooms, tables = self.origins()
        if rooms is None and tables is None:
            return True
        return (rooms is not None and room in rooms) or (tables is not None and table in tables)

    def queue_items(self, extra_where="", params=None, for_update=False, statuses=None):
        """
        Order lines waiting at this production center: already sent, in a
        status of its flow (except the last one), of its item groups, and
        within its room / table restrictions. The line's status is
        shared by every center that handles it, so centers chained by status
        (cafeteria: Sent -> Delivering, dining room: Delivering -> Delivered)
        stay in sync.
        """
        statuses = list(statuses or self.working_statuses)
        groups = self._items_group
        if not statuses or not groups:
            return []
        # split combos (api/parts.py) come with their lines: their parts are routed below
        from renpos.api import parts as ren_parts
        conditions = [
            "i.parenttype = 'Ren Order'", "i.qty > 0",
            "((i.status IN %(statuses)s AND i.item_group IN %(groups)s)"
            " OR (IFNULL(i.ren_parts, '') NOT IN ('', 'null') AND i.status IN %(waiting)s))",
        ]
        values = {"statuses": statuses, "groups": groups, "waiting": ren_parts.waiting_statuses(), **(params or {})}

        # only some rooms and / or tables: an order of any of them
        where = self.origin_condition("o")
        if where:
            conditions.append(where[0])
            values.update(where[1])
        if extra_where:
            conditions.append(extra_where)

        rows = frappe.db.sql(
            f"""
            SELECT i.name, i.identifier, i.item_code, i.item_name, i.item_group, i.qty, i.notes,
                   i.status, i.parent, i.ordered_time, i.modifiers, i.idx, i.ren_parts, i.ren_part_status,
                   o.table, o.table_description, o.room_description, o.dinners, o.owner AS order_owner,
                   o.notes AS order_notes
            FROM `tabRen Order Item` i
            JOIN `tabRen Order` o ON o.name = i.parent
            WHERE {" AND ".join(conditions)}
            ORDER BY i.ordered_time ASC, i.idx ASC
            {"FOR UPDATE" if for_update else ""}
            """,
            values,
            as_dict=True,
        )
        group_set = set(groups)
        return ren_parts.route(rows, lambda g: g in group_set, set(statuses))

    DEFAULT_FLOW = ("Sent", "Processing", "Completed")

    @property
    def flow(self):
        """The station's statuses in order: [arrives, ..., leaves]."""
        steps = [r.status for r in (self.get("status_flow") or []) if r.status]
        return steps if len(steps) >= 2 else list(self.DEFAULT_FLOW)

    def validate(self):
        steps = [r.status for r in (self.get("status_flow") or []) if r.status]
        if steps:
            if len(steps) < 2:
                frappe.throw(_("The status flow needs at least two statuses: how items arrive and when they leave"))
            if len(set(steps)) != len(steps):
                frappe.throw(_("A status can appear only once in the flow"))
            from renpos.api.statuses import editable_statuses
            editable = [s for s in steps if s in editable_statuses()]
            if editable:
                frappe.throw(_("{0} can't be part of a production flow: the waiter can still edit items in that "
                               "status (\"Allows to edit Item\" in the status), so the station would show items "
                               "that weren't sent, or hand them back to the order as editable.").format(
                                   ", ".join(editable)))

    def next_status(self, last_status):
        flow = self.flow
        if last_status in flow[:-1]:
            return flow[flow.index(last_status) + 1]
        frappe.throw(_("Invalid action, the process is complete"))

    @property
    def working_statuses(self):
        """Statuses shown at this station (every step except the last one)."""
        return self.flow[:-1]

    @property
    def _items_group(self):
        items_groups = []
        for group in self.production_center_group:
            lft, rgt = frappe.db.get_value('Item Group', group.item_group, ['lft', 'rgt'])
            for item in frappe.get_list("Item Group", "name", filters={
                "lft": (">=", lft), "rgt": ("<=", rgt)
            }):
                items_groups.append(item.name)
        return items_groups
