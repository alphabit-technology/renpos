# -*- coding: utf-8 -*-
# Copyright (c) 2021, Quantum Bit Core and contributors
# For license information, please see license.txt
#
# A table's order. Lines, prices and statuses change only through
# api/order.py (see only_through_the_restaurant_api).

import frappe
from frappe import _
from frappe.model.document import Document


class RenOrder(Document):
    def after_delete(self):
        self._table.synchronize()

    def on_change(self):
        self._table.synchronize()

    def validate(self):
        self.only_through_the_restaurant_api()
        if self.status is None:
            self.status = "Opened"
            self.show_in_pos = 1

        if self.status == "Cancelled":
            self.show_in_pos = 0

        if self.status == "Sent" and len(self.entry_items) == 0:
            if self.status != frappe.db.get_value("Ren Order", self.name, "status"):
                frappe.throw(_("You can't send an empty order"))

            self.show_in_pos = 0
            self.ordered_time = frappe.utils.now_datetime()

        self.set_default_customer()
        self.set_restaurant()

    def set_restaurant(self):
        """The restaurant the order belongs to (its table's): lists and access go by it."""
        if self.table and not self.restaurant:
            from renpos.api.access import restaurant_of_table
            self.restaurant = restaurant_of_table(self.table)
        if not self.restaurant and self.pos_profile:
            self.restaurant = frappe.db.get_value("POS Profile", self.pos_profile, "ren_restaurant")

    PROTECTED_LINE_FIELDS = ("item_code", "qty", "rate", "price_list_rate", "discount_percentage", "amount",
                             "status", "modifiers_amount")

    def only_through_the_restaurant_api(self):
        """
        Lines, prices and statuses change only through api/order.py (which
        validates prices, discounts, voids and permissions). Saving the order
        from the desk or /api/resource can still change notes, customer, guests.
        """
        if frappe.flags.ren_order_api or frappe.flags.in_install or frappe.flags.in_migrate \
                or frappe.flags.in_patch or frappe.session.user == "Administrator":
            return
        if self.is_new():
            if any(frappe.utils.flt(i.qty) for i in self.entry_items):
                frappe.throw(_("Orders are taken from the restaurant screen"))
            return
        before = self.get_doc_before_save()
        if not before:
            return
        old = {r.name: r for r in before.entry_items}
        new = {r.name: r for r in self.entry_items}
        changed = set(old) != set(new) or any(
            str(old[n].get(f)) != str(new[n].get(f)) for n in new for f in self.PROTECTED_LINE_FIELDS)
        if changed or before.status != self.status or str(before.amount) != str(self.amount) \
                or before.table != self.table or before.pos_profile != self.pos_profile:
            frappe.throw(_("Items, prices and status are changed from the restaurant screen"))

    def on_trash(self):
        if frappe.flags.ren_order_api or frappe.session.user == "Administrator":
            return
        from renpos.api.statuses import is_editable
        if any(not is_editable(i.status) and frappe.utils.flt(i.qty) for i in self.entry_items):
            frappe.throw(_("Orders with items sent to the kitchen are voided from the restaurant screen"))

    def set_default_customer(self):
        if self.customer:
            return

        if self._table and self._table.customer:
            self.customer = self._table.customer
        else:
            self.customer = frappe.db.get_value(
                'POS Profile', self.pos_profile, 'customer')

    @property
    def short_name(self):
        return self.name[8:]

    @property
    def _table(self):
        return frappe.get_doc("Ren Table", self.table)
