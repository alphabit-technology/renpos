import frappe
import random
from frappe import _
from restaurant_management.restaurant_management.doctype.ren_base import RenBase


class RenRoom(RenBase):
    def get_obj_data(self):
        return self.get_data("name,description,orders_count")

    def before_save(self):
        if self.is_new() or not self.company:
            self.company = frappe.defaults.get_user_default('company')

    def get_tables(self, name=None):
        settings = frappe.get_single("Restaurant Settings")

        filters = {}

        if name is None:
            filters["room"] = self.name
            if not settings.user_has_admin_role() and not settings.has_access_to_room(self.name):
                filters["name"] = ("in", settings.restaurant_access("Ren Table"))
        else:
            filters["name"] = name

        tables = frappe.get_all("Ren Table", "name", filters=filters)

        for table in tables:
            doc = frappe.get_doc("Ren Table", table.name)
            data = doc.get_obj_data()
            for prop in data:
                table[prop] = data[prop]

        return dict(tables=tables, orders_count=self.orders_count)

    def add_table(self):
        objects_count = frappe.db.count("Ren Table", filters={"room": self.name})

        colors = ["#5b1e34", "#97264f", "#1a4469",
                  "#1579d0", "#2d401d", "#2e844e", "#505a62"]
        color = colors[random.randint(0, 6)]

        zIndex = objects_count + 60
        left = objects_count * 25
        top = objects_count * 25
        name = f"T-{random.randint(random.randint(1, 100), random.randint(100, 1000))}"

        data_style = f'{{"x":"{left}","y":"{top}","z-index":"{zIndex}","width":"150px","height":"100px"}}'

        table = frappe.new_doc("Ren Table")
        table.room = self.name
        table.data_style = data_style
        table.color = color
        table.description = name
        table.no_of_seats = 4
        table.shape = 'Square'
        
        table.save()

    def count_objects(self):
        return frappe.db.count("Ren Table", filters={
            "room": self.name
        })

    @property
    def orders_count(self):
        settings = frappe.get_single("Restaurant Settings")
        filters = {
            "company": self.company,
            "show_in_pos": 1,
            "status": ["not in", ["Cancelled", "Invoiced", "Opened"]],
            "room": self.name,
        }

        if not settings.user_has_admin_role() and not settings.has_access_to_room(self.name):
            filters["table"] = ("in", settings.restaurant_access("Ren Table") or [])

        return frappe.db.count("Table Order", filters)