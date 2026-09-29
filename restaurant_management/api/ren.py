# -*- coding: utf-8 -*-
# Copyright (c) 2021, Quantum Bit Core and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
#
# ren.call: allow-listed method calls on restaurant layout documents
# (floors, rooms, tables, stations) used by the floor editor.
# Booking endpoints live in api/booking.py.
import frappe
from restaurant_management.api.guards import require_restaurant_user
import json
import hashlib

from frappe import _
from frappe.utils import cint, today, now_datetime, getdate, get_time
from datetime import timedelta, datetime


# Methods the React client may invoke through `call`, per DocType.
# value = (permission type, DocType the permission is checked on;
#          None means "the document itself").
ALLOWED_METHODS = {
    "Ren Restaurant": {
        "load_floors": ("read", "Ren Floor"),
    },
    "Ren Floor": {
        "get_children": ("read", None),
        "add_room": ("create", "Ren Room"),
        "add_station": ("create", "Ren Station"),
        "delete": ("delete", None),
    },
    "Ren Room": {
        "get_tables": ("read", None),
        "add_table": ("create", "Ren Table"),
        "set_attr": ("write", None),
        "delete": ("delete", None),
    },
    "Ren Table": {
        "set_attr": ("write", None),
        "delete": ("delete", None),
    },
    "Ren Station": {
        "set_attr": ("write", None),
        "delete": ("delete", None),
    },
}

# Only layout attributes may be changed through set_attr.
SET_ATTR_FIELDS = {"data_style", "shape"}


@frappe.whitelist()
def call(model, name, method, args=None):
    """
    Invoke an allow-listed method on a restaurant layout document.
    Anything outside ALLOWED_METHODS is rejected.
    """
    from restaurant_management.api.guards import require_restaurant_user

    require_restaurant_user()

    rule = ALLOWED_METHODS.get(model, {}).get(method)
    if not rule:
        raise frappe.PermissionError(_("Method {0} is not allowed on {1}").format(method, model))

    ptype, check_doctype = rule
    doc = frappe.get_doc(model, name)

    if check_doctype:
        if not frappe.has_permission(check_doctype, ptype):
            raise frappe.PermissionError(_("Not permitted: {0} {1}").format(ptype, check_doctype))
    else:
        doc.check_permission(ptype)

    kwargs = json.loads(args) if isinstance(args, str) else (args or {})

    if method == "set_attr":
        attr = kwargs.get("attr")
        value = kwargs.get("value")
        if attr not in SET_ATTR_FIELDS:
            raise frappe.PermissionError(_("Attribute {0} cannot be changed").format(attr))
        if attr == "data_style":
            json.loads(value)  # must be valid JSON
        return doc.set_attr(attr, value)

    # The remaining methods only accept an optional `client` id.
    allowed_kwargs = {k: v for k, v in kwargs.items() if k == "client"}
    return getattr(doc, method)(**allowed_kwargs)
