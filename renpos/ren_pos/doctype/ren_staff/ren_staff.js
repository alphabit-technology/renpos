// Ren Staff: grants only list the floors, rooms, tables and stations of the restaurant.
frappe.ui.form.on("Ren Staff", {
	setup(frm) {
		frm.set_query("object_type", "restaurant_permissions", () => ({
			filters: { name: ["in", ["Ren Floor", "Ren Room", "Ren Table", "Ren Station"]] },
		}));
		frm.set_query("object_name", "restaurant_permissions", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "renpos.api.staff.grantable",
				filters: { object_type: row.object_type, restaurant: doc.restaurant },
			};
		});
	},

	refresh(frm) {
		if (frm.is_new()) return;
		// a role that charges also needs ERPNext's cashier rights and a POS Profile
		frappe.call("renpos.api.staff.staff_charging", { staff: frm.doc.name }).then(({ message: r }) => {
			if (!r?.gaps?.length) return;
			frm.dashboard.set_headline_alert(
				`${__("Their role charges, but they can't charge yet. Missing:")} ${r.gaps.join("; ")}`, "orange");
			if (r.can_fix) {
				frm.add_custom_button(__("Let them charge"), () =>
					frappe.call({ method: "renpos.api.staff.enable_charging", args: { staff: frm.doc.name } })
						.then(() => frm.reload_doc()));
			}
		});
	},
});
