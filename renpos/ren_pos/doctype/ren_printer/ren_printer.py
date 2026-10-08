# Copyright (c) 2026, Quantum Bit Core and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RenPrinter(Document):
	def validate(self):
		if not self.port:
			self.port = 9100
		if (self.copies or 0) < 1:
			self.copies = 1

	@frappe.whitelist()
	def print_test(self):
		from renpos.api.printing import print_test_page
		return print_test_page(self.name)
