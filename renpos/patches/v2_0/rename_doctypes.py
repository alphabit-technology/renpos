"""
Every DocType of the app carries the Ren prefix (Ren POS, 2026-10). Runs before
the model sync: renames the DocType records, their tables and every Link /
Table option, parenttype and dynamic link pointing at them (frappe.rename_doc).
"""

import frappe

RENAMES = {
	"Cuisine Type": "Ren Cuisine Type",
	"Item Menu Tag": "Ren Item Menu Tag",
	"Item Option": "Ren Item Option",
	"Item Option Section": "Ren Item Option Section",
	"Kitchen Status Log": "Ren Kitchen Status Log",
	"Menu Schedule": "Ren Menu Schedule",
	"Menu Tag": "Ren Menu Tag",
	"Modifier Mode": "Ren Modifier Mode",
	"Option List": "Ren Option List",
	"Order Entry Item": "Ren Order Item",
	"Production Center Group": "Ren Station Item Group",
	"Reservation Opening Hour": "Ren Opening Hour",
	"Reservation Turn Time": "Ren Turn Time",
	"Restaurant Audit Log": "Ren Audit Log",
	"Restaurant Booking": "Ren Booking",
	"Restaurant Booking Table": "Ren Booking Table",
	"Restaurant Card Payment": "Ren Card Payment",
	"Restaurant Card Reader": "Ren Card Reader",
	"Restaurant Menu": "Ren Menu",
	"Restaurant Menu Item": "Ren Menu Item",
	"Restaurant Permission": "Ren Access Grant",
	"Restaurant Permission Manage": "Ren Staff Access",
	"Restaurant Print Job": "Ren Print Job",
	"Restaurant Printer": "Ren Printer",
	"Restaurant Reservation Settings": "Ren Reservation Settings",
	"Restaurant Role": "Ren Role",
	"Restaurant Settings": "Ren Settings",
	"Restaurant Shift": "Ren Shift",
	"Restaurant Sold Out": "Ren Sold Out",
	"Restaurant Terminal": "Ren Terminal",
	"Restaurant Void Log": "Ren Void Log",
	"Restaurant Void Reason": "Ren Void Reason",
	"Station Status Step": "Ren Station Status Step",
	"Status Managed Production Center": "Ren Legacy Status Step",
	"Status Order PC": "Ren Order Status",
	"Table Order": "Ren Order",
}


def execute():
	for old, new in RENAMES.items():
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)
	frappe.clear_cache()
