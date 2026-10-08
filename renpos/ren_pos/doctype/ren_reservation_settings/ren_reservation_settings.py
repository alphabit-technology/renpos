# Copyright (c) 2026, Quantum Bit Core and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class RenReservationSettings(Document):
	def validate(self):
		if cint(self.slot_minutes) < 5:
			frappe.throw(_("Slots must be at least 5 minutes"))
		if cint(self.default_duration) < 15:
			frappe.throw(_("The default table time must be at least 15 minutes"))
		for row in self.turn_times or []:
			if cint(row.min_party) < 1 or cint(row.max_party) < cint(row.min_party) or cint(row.minutes) < 15:
				frappe.throw(_("Row {0}: guests from/to and at least 15 minutes are required").format(row.idx))
