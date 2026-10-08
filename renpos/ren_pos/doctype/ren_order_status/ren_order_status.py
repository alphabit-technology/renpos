# -*- coding: utf-8 -*-
# Copyright (c) 2022, Quantum Bit Core and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RenOrderStatus(Document):
	def validate(self):
		from renpos.api.statuses import validate_status
		validate_status(self)
