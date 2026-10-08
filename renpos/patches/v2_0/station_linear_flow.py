"""
Ren Station: the from -> to status table becomes a linear flow
(status_flow: Sent -> Processing -> Completed). Items reach the kitchen as
"Sent", so a legacy flow that doesn't include it gets "Sent" in front.
"""

import frappe


def execute():
	if not frappe.db.sql("SHOW TABLES LIKE 'tabRen Legacy Status Step'"):
		return
	for name in frappe.get_all("Ren Station", pluck="name"):
		if frappe.db.exists("Ren Station Status Step", {"parenttype": "Ren Station", "parent": name}):
			continue
		rows = frappe.db.sql("""SELECT status_managed, next_status FROM `tabRen Legacy Status Step`
			WHERE parenttype = 'Ren Station' AND parent = %s ORDER BY idx""", name, as_dict=True)
		flow = legacy_flow(rows) or ["Sent", "Processing", "Completed"]
		if "Sent" not in flow:
			flow = ["Sent"] + flow
		for i, status in enumerate(flow, 1):
			if not frappe.db.exists("Ren Order Status", status):
				continue
			frappe.get_doc({
				"doctype": "Ren Station Status Step", "parenttype": "Ren Station", "parentfield": "status_flow",
				"parent": name, "status": status, "idx": i,
			}).db_insert()


def legacy_flow(rows):
	"""Chain legacy (status_managed -> next_status) rows into a linear flow."""
	pairs = {r.status_managed: r.next_status for r in rows if r.status_managed and r.next_status}
	if not pairs:
		return []
	targets = set(pairs.values())
	starts = [a for a in pairs if a not in targets] or [next(iter(pairs))]
	flow, cur = [starts[0]], starts[0]
	while cur in pairs and pairs[cur] not in flow:
		cur = pairs[cur]
		flow.append(cur)
	return flow
