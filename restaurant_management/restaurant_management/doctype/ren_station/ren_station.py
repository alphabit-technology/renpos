import frappe
import random
import string
from frappe import _
from restaurant_management.restaurant_management.doctype.ren_base import RenBase


class RenStation(RenBase):
    def get_obj_data(self):
        fields = ("name,description,orders_count,data_style,min_size,color,shape,floor")
        data = self.get_data(fields)

        return data

    """ def on_update(self):
        data = self.get_station_data()
        self.publish_update(data)
        self.publish_notifications() """

    def get_station_data(self):
        fields = ("name,description,identifier,orders_count,"
                  "data_style,group_items_by_order,min_size,current_user,color,"
                  "restricted_to_rooms,restricted_to_tables,restricted_to_branches,floor")
        data = self.get_data(fields)
        data["status_managed"] = self._status_managed
        data["items_group"] = self._items_group
        data["restricted_rooms"] = self.restricted_rooms
        data["restricted_tables"] = self.restricted_tables
        data["restricted_branches"] = self.restricted_branches
        return data

    @property
    def orders_count(self):
        filters = self.get_command_filters()
        if self.group_items_by_order == 1:
            return len(frappe.db.get_all(
                "Order Entry Item",
                fields="name",
                filters=filters,
                group_by="parent"
            ))
        return frappe.db.count("Order Entry Item", filters)

    def set_status_command(self, identifier):
        if self.group_items_by_order == 1:
            last_status = frappe.db.get_value("Table Order", {"name": identifier}, "status")
        else:
            last_status = frappe.db.get_value(
                "Order Entry Item", {"identifier": identifier}, "status")

        status = self.next_status(last_status)

        order = frappe.get_doc("Table Order",
            identifier if self.group_items_by_order else
            frappe.db.get_value("Order Entry Item", {"identifier": identifier}, "parent")
        )

        if order.show_in_pos == 1:
            order.status = status

        if self.group_items_by_order == 1:
            frappe.db.set_value("Table Order", {"name": identifier}, "status", status)
        else:
            frappe.db.set_value("Order Entry Item", {"identifier": identifier}, "status", status)

        order.reload()
        items = None if self.group_items_by_order == 1 else self.commands_food(identifier, last_status)
        order.synchronize(dict(items=items, status=[last_status, status]))

    def command_data(self, command):
        item = self.commands_food(command)
        return {"data": item[0]} if len(item) > 0 else None

    def get_command_filters(self, identifier=None):
        random_str = ''.join(random.choice(
            string.ascii_uppercase + string.digits) for _ in range(100))

        if identifier is not None:
            return {"identifier": identifier}

        status_managed = self._status_managed
        items_group = self._items_group

        filters = {
            "parenttype": "Table Order",
            "item_group": ("in", items_group if items_group else [random_str]),
            "qty": (">", "0")
        }

        parent_filter = {}

        if self.group_items_by_order == 1:
            parent_filter["status"] = ("in", status_managed if status_managed else [random_str])
        else:
            filters["status"] = ("in", status_managed if status_managed else [""])

        def make_filter(type_name, parent=None):
            if parent is not None:
                parent_filter[type_name.lower()] = parent
            else:
                restricted = frappe.get_all("Order Origin", filters=dict(
                    parenttype="Ren Station",
                    parent=self.name,
                    type=type_name
                ), pluck="origin")
                parent_filter[type_name.lower()] = (
                    "in", restricted if restricted else [random_str])

        if self.restricted_to_branches == 1:
            branches = [item.branch for item in self.restricted_branches]
            parent_filter["branch"] = ("in", branches if branches else [random_str])

        if self.restricted_to_rooms == 1:
            make_filter("Room")
        elif self.restricted_to_tables == 1:
            make_filter("Table")

        orders = frappe.get_all("Table Order", parent_filter, pluck="name")
        filters["parent"] = ("in", orders if orders else [random_str])

        return filters

    def commands_food(self, identifier=None, last_status=None):
        filters = self.get_command_filters(identifier)
        items = []
        groups = {}

        for entry in frappe.get_all("Order Entry Item", "*", filters=filters, order_by="ordered_time"):
            items.append(self._get_command_data(entry, last_status))

        for item in items:
            key = item["order_name"]
            if key not in groups:
                groups[key] = dict(items=[])
            groups[key]["items"].append(item)

            if self.group_items_by_order != 1:
                groups[key].update(dict(data=item))

        if self.group_items_by_order == 1:
            for group in groups:
                order = frappe.get_doc("Table Order", group)
                groups[group].update(dict(data=order.short_data()["data"]))

        return groups

    def _get_command_data(self, entry, last_status=None):
        short_name = entry.parent[8:]
        return dict(
            identifier=entry.identifier,
            item_group=entry.item_group,
            item_code=entry.item_code,
            item_name=entry.item_name,
            order_name=entry.identifier if self.group_items_by_order != 1 else entry.parent,
            order=short_name,
            room=entry.room,
            branch=entry.branch,
            table=entry.table,
            table_description=entry.table_description or entry.table,
            room_description=entry.room_description or entry.room,
            short_name=short_name,
            qty=entry.qty,
            rate=entry.rate,
            amount=(entry.qty * entry.rate),
            entry_name=entry.name,
            name=entry.identifier,
            status=entry.status,
            last_status=last_status,
            notes=entry.notes,
            ordered_time=entry.ordered_time or frappe.utils.now_datetime(),
            process_status_data=self._process_status_data(entry)
        )

    def _process_status_data(self, item):
        status = self._status(item.status)
        return dict(
            next_action_message=status.action_message,
            color=status.color,
            icon=status.icon,
            status_message=status.message
        )

    def next_status(self, last_status):
        for status in self.status_managed:
            if last_status == status.status_managed:
                return status.next_status
        frappe.throw(_("Invalid action, the process is complete"))

    @staticmethod
    def _status(status="Pending"):
        return frappe.get_doc("Status Order PC", status)

    @property
    def _status_managed(self):
        return [item.status_managed for item in self.status_managed]

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