# Copyright (c) 2026, Quantum Bit Core and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class RenModifierMode(Document):
	"""Light, Extra, On the side…: how a part of a dish can be ordered (see api/modifiers.py)."""

	def validate(self):
		if "{0}" not in (self.kitchen_text or ""):
			frappe.throw(_("Kitchen Text must contain {0}, where the option goes (e.g. EXTRA {0})"))
		if flt(self.qty_factor) < 0 or flt(self.price_factor) < 0:
			frappe.throw(_("Factors can't be negative"))

	def on_change(self):
		frappe.publish_realtime("modifiers_update", {"mode": self.name}, after_commit=True)
