import frappe
from frappe.model.document import Document

class RenFloor(Document):
    def after_delete(self):
        frappe.publish_realtime("check_floors")

    def on_change(self):
        frappe.publish_realtime("check_floors")

    def get_children(self):
        floor_filter = {"floor": self.name}

        restaurant_settings = frappe.get_single("Restaurant Settings")

        if not restaurant_settings.user_has_admin_role():
            allowed_rooms = restaurant_settings.restaurant_access("Ren Room")
            allowed_stations = restaurant_settings.restaurant_access("Ren Station")
            room_filters = {**floor_filter, "name": ("in", list(allowed_rooms))}
            station_filters = {**floor_filter, "name": ("in", list(allowed_stations))}
        else:
            room_filters = floor_filter
            station_filters = floor_filter

        rooms = frappe.get_all("Ren Room", "name,description,menu", filters=room_filters)
        stations = frappe.get_all("Ren Station", "name,description", filters=station_filters)

        for room in rooms:
            room["orders_count"] = frappe.db.count("Table Order", {
                "room": room.name,
                "status": ["not in", ["Cancelled", "Invoiced"]]
            })

        for station in stations:
            doc = frappe.get_doc("Ren Station", station.name)
            data = doc.get_station_data()
            for prop in data:
                station[prop] = data[prop]

        return {
            "rooms": rooms,
            "stations": stations
        }

    def get_rooms(self):
        filters = {
            "floor": self.name
        }

        restaurant_settings = frappe.get_single("Restaurant Settings")

        if not restaurant_settings.user_has_admin_role():
            rooms_enabled = restaurant_settings.restaurant_access("Ren Room")  # ← target type
            filters["name"] = ("in", list(rooms_enabled))

        rooms = frappe.get_all("Ren Room", "name,description", filters=filters)

        for room in rooms:
            t = frappe.get_doc("Ren Room", room.name)
            room["orders_count"] = t.orders_count

        return rooms

    def get_stations(self):
        filters = {
            "floor": self.name
        }

        restaurant_settings = frappe.get_single("Restaurant Settings")

        if not restaurant_settings.user_has_admin_role():
            rooms_enabled = restaurant_settings.restaurant_access()
            filters["name"] = ("in", rooms_enabled)

        stations = frappe.get_all("Ren Station", "name,description", filters=filters)

        for station in stations:
            t = frappe.get_doc("Ren Station", station.name)
            station["orders_count"] = t.orders_count

        return stations

    def add_room(self, client=None):
        room = frappe.new_doc("Ren Room")
        room.floor = self.name
        room.description = f"R {(self.room_count() + 1)}"
        room.save()

    def add_station(self, client=None):
        station = frappe.new_doc("Ren Station")
        station.floor = self.name
        station.description = f"S {(self.station_count() + 1)}"
        station.save()

    def room_count(self):
        return frappe.db.count("Ren Room", filters={
            "floor": self.name
        })

    def station_count(self):
        return frappe.db.count("Ren Station", filters={
            "floor": self.name
        })