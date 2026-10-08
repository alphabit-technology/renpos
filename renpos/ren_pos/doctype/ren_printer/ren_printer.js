// Copyright (c) 2026, Quantum Bit Core and contributors
// For license information, please see license.txt

frappe.ui.form.on("Ren Printer", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Print test page"), () =>
			frm.call("print_test").then(() => frappe.show_alert({ message: __("Test page sent"), indicator: "green" }))
		);
	},
});
