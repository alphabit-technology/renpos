# Copyright (c) 2026, Quantum Bit Core and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RenOptionList(Document):
	"""
	Options shared by many items: Sauces, Cooking point, Sides... An item
	offers them by adding the list to one of its sections (Restaurant tab).
	"""

	def validate(self):
		from renpos.api.modifiers import validate_option_list
		validate_option_list(self)

	def on_update(self):
		from renpos.api.modifiers import publish_change
		publish_change(self)
