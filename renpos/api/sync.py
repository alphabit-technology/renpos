# -*- coding: utf-8 -*-
# renpos/api/sync.py
#
# Open POS screens follow the restaurant's setup. Any change that can alter
# what someone sees or may do (restaurant, settings, roles, staff access,
# floors / rooms / tables, production centers, statuses, POS Profiles)
# publishes one event, "ren_config" {doctype, name}, after the commit. The
# screens reload what depends on it: the restaurant data and access, the
# floor's rooms and stations, the tables, the kitchen queues.
#
# A Ren Staff change only goes to that person. Layout moves (dragging a
# table) keep their own per-floor / per-room events (ren_base.py).

import frappe

EVENT = "ren_config"


def config_changed(doc, method=None):
	"""doc_events hook (on_update / on_trash) of the setup doctypes."""
	payload = {"doctype": doc.doctype, "name": doc.name, "deleted": int(method == "on_trash")}
	if doc.doctype == "Ren Staff":
		frappe.publish_realtime(EVENT, payload, user=doc.user, after_commit=True)
		return
	frappe.publish_realtime(EVENT, payload, after_commit=True)
