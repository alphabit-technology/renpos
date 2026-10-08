# A person who works at a restaurant: their role there and what they work
# (floors, rooms, tables, stations). One record per person and restaurant.
# Charging is separate: the POS Profile's "Applicable for Users" (api/guards.py).

import frappe
from frappe import _
from frappe.model.document import Document

OBJECT_TYPES = ("Ren Floor", "Ren Room", "Ren Table", "Ren Station")


def restaurant_of(object_type, name):
	"""The restaurant a floor / room / table / station belongs to."""
	if object_type == "Ren Floor":
		return frappe.db.get_value("Ren Floor", name, "restaurant")
	if object_type == "Ren Room":
		return frappe.db.get_value("Ren Floor", frappe.db.get_value("Ren Room", name, "floor"), "restaurant")
	if object_type == "Ren Table":
		return restaurant_of("Ren Room", frappe.db.get_value("Ren Table", name, "room"))
	if object_type == "Ren Station":
		return frappe.db.get_value("Ren Floor", frappe.db.get_value("Ren Station", name, "floor"), "restaurant")
	return None


class RenStaff(Document):
	def validate(self):
		other = frappe.db.get_value("Ren Staff", {"user": self.user, "restaurant": self.restaurant,
		                                          "name": ["!=", self.name]})
		if other:
			frappe.throw(_("{0} already works at {1} ({2})").format(
				frappe.bold(self.user), frappe.bold(self.restaurant), other))
		# the first restaurant someone works at is where they start
		if self.is_new() and not frappe.db.exists("Ren Staff", {"user": self.user}):
			self.is_default = 1
		for row in self.restaurant_permissions or []:
			if row.object_type not in OBJECT_TYPES:
				frappe.throw(_("Row {0}: choose a floor, room, table or station").format(row.idx))
			if restaurant_of(row.object_type, row.object_name) != self.restaurant:
				frappe.throw(_("Row {0}: {1} isn't part of {2}").format(
					row.idx, frappe.bold(row.object_name), frappe.bold(self.restaurant)))
			row.description = frappe.db.get_value(row.object_type, row.object_name, "description") or row.object_name
		# someone who only works production centers (a cook) doesn't take the default server role
		grants = {r.object_type for r in self.restaurant_permissions or []}
		if not self.restaurant_role and grants == {"Ren Station"} and frappe.db.exists("Ren Role", "Kitchen"):
			self.restaurant_role = "Kitchen"

	def on_update(self):
		if self.is_default:
			frappe.db.sql("""UPDATE `tabRen Staff` SET is_default = 0 WHERE user = %s AND name != %s""",
			              (self.user, self.name))

