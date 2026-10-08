# -*- coding: utf-8 -*-
"""
Order line statuses: which ones the waiter can still edit.

Every status is a Ren Order Status record; its "Allows to edit Item" check
decides whether a line in that status is still the waiter's (editable,
deletable, sent with the next Send) or already belongs to the production
centers. Two statuses have a fixed role:
  - NEW_ITEM_STATUS ("Pending"): status of a line just added; always editable.
  - SENT_STATUS ("Sent"): what Send sets; never editable.
"""

import frappe
from frappe import _
from frappe.utils.caching import request_cache

NEW_ITEM_STATUS = "Pending"
SENT_STATUS = "Sent"


@request_cache
def editable_statuses():
	flagged = frappe.get_all("Ren Order Status", filters={"allows_to_edit_item": 1}, pluck="name")
	return tuple(sorted((set(flagged) | {NEW_ITEM_STATUS}) - {SENT_STATUS}))


def is_editable(status):
	"""A line still being taken by the waiter (no status counts as new)."""
	return not status or status in editable_statuses()


def validate_status(doc):
	if doc.name == SENT_STATUS and doc.allows_to_edit_item:
		frappe.throw(_("Sent can't allow editing: it's the status items get when they go to the production centers"))
	if doc.name == NEW_ITEM_STATUS and not doc.allows_to_edit_item:
		frappe.throw(_("Pending must allow editing: it's the status of items just added to an order"))
