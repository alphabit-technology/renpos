// Theoretical vs actual usage of ingredients for a period (see the .py).
frappe.query_reports["Ingredient Usage Variance"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse", reqd: 1,
		  get_query: () => ({ filters: { company: frappe.query_report.get_filter_value("company"), is_group: 0 } }) },
		{ fieldname: "from_date", label: __("From"), fieldtype: "Date", reqd: 1,
		  default: frappe.datetime.add_days(frappe.datetime.get_today(), -7) },
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "only_variance", label: __("Only items with a variance"), fieldtype: "Check", default: 0 },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && ["variance_qty", "variance_value", "variance_pct"].includes(column.fieldname)) {
			const v = data[column.fieldname];
			if (v < 0) value = `<span style="color: var(--red-500)">${value}</span>`;
			else if (v > 0) value = `<span style="color: var(--green-600)">${value}</span>`;
		}
		return value;
	},
};
