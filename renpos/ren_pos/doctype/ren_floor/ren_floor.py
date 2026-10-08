import frappe
from frappe.model.document import Document
from renpos.ren_pos.doctype.ren_base import next_free_description

class RenFloor(Document):
    def get_children(self):
        floor_filter = {"floor": self.name}

        restaurant_settings = frappe.get_single("Ren Settings")

        from renpos.api.kitchen import allowed_stations
        room_filters = station_filters = floor_filter
        if not restaurant_settings.user_has_admin_role():
            room_filters = {**floor_filter, "name": ("in", list(restaurant_settings.restaurant_access("Ren Room")))}
        stations_allowed = allowed_stations()
        if stations_allowed is not None:
            station_filters = {**floor_filter, "name": ("in", list(stations_allowed))}

        rooms = frappe.get_all("Ren Room", "name,description,menu", filters=room_filters)
        stations = frappe.get_all("Ren Station", "name,description", filters=station_filters)

        for room in rooms:
            room["orders_count"] = frappe.db.count("Ren Order", {
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

    def add_room(self, client=None):
        room = frappe.new_doc("Ren Room")
        room.floor = self.name
        room.description = next_free_description("Ren Room", "R ")
        room.save()

    def add_station(self, client=None):
        station = frappe.new_doc("Ren Station")
        station.floor = self.name
        station.description = next_free_description("Ren Station", "S ")
        station.save()
