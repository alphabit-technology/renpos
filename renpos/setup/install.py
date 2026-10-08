import frappe
from itertools import chain


custom_fields = {
    "POS Profile": dict(
        ren_tax_inclusive=dict(
            label="Tax Inclusive", fieldtype="Check", insert_after="tax_category", default_value=1
        ),
        ren_restaurant=dict(label="Restaurant", fieldtype="Link", options="Ren Restaurant", insert_after="company"),
        # "Restaurant" tab at the end of the POS Profile
        ren_restaurant_tab=dict(label="Restaurant", fieldtype="Tab Break", insert_after="utm_medium"),
        ren_tips_section=dict(label="Tips", fieldtype="Section Break", insert_after="ren_restaurant_tab"),
        ren_tip_account=dict(
            label="Tips Account", fieldtype="Link", options="Account", insert_after="ren_tips_section",
            description="Liability account (e.g. Tips Payable) where tips are recorded. Empty: tips are disabled.",
        ),
        ren_tip_percentages=dict(
            label="Suggested Tips (%)", fieldtype="Data", default="18, 20, 22", insert_after="ren_tip_account",
        ),
        ren_tips_column=dict(fieldtype="Column Break", insert_after="ren_tip_percentages"),
        ren_tip_on=dict(
            label="Calculate Tip On", fieldtype="Select", options="Subtotal\nTotal with tax",
            default="Subtotal", insert_after="ren_tips_column",
        ),
        ren_printing_section=dict(label="Printing", fieldtype="Section Break", insert_after="ren_tip_on"),
        ren_receipt_printer=dict(
            label="Receipt Printer", fieldtype="Link", options="Ren Printer", insert_after="ren_printing_section",
            description="Bills, receipts and the cash drawer. Kitchen tickets go to each Ren Station's printer.",
        ),
        ren_print_kitchen_tickets=dict(
            label="Print Kitchen Tickets on Send", fieldtype="Check", default="1", insert_after="ren_receipt_printer",
        ),
        ren_printing_column=dict(fieldtype="Column Break", insert_after="ren_print_kitchen_tickets"),
        ren_print_receipt_on_payment=dict(
            label="Print Receipt After Payment", fieldtype="Check", default="1", insert_after="ren_printing_column",
        ),
        ren_open_drawer_on_cash=dict(
            label="Open Cash Drawer on Cash Payments", fieldtype="Check", default="1", insert_after="ren_print_receipt_on_payment",
        ),
    ),
    "POS Invoice": dict(
        ren_server=dict(label="Server", fieldtype="Link", options="User", read_only=1, insert_after="pos_profile",
                       description="Who took the order (for tips and sales by server)"),
        ren_tip_amount=dict(label="Tip", fieldtype="Currency", read_only=1, insert_after="ren_server"),
    ),
    "Sales Invoice": dict(
        ren_server=dict(label="Server", fieldtype="Link", options="User", read_only=1, insert_after="pos_profile",
                       description="Who took the order (for tips and sales by server)"),
        ren_tip_amount=dict(label="Tip", fieldtype="Currency", read_only=1, insert_after="ren_server"),
    ),
    "POS Invoice Item": dict(
        identifier=dict(label="Identifier", fieldtype="Data"),
    ),
    "Sales Invoice Item": dict(
        identifier=dict(label="Identifier", fieldtype="Data"),
    ),
    "User": dict(
        ren_pin_hash=dict(label="Restaurant PIN", fieldtype="Data", hidden=1, read_only=1,
                         insert_after="last_login", no_copy=1, print_hide=1, report_hide=1),
    ),
    "Customer": dict(
        ren_guest_section=dict(label="Restaurant Guest", fieldtype="Section Break", insert_after="mobile_no",
                              collapsible=1),
        ren_guest_tags=dict(label="Guest Tags", fieldtype="Data", insert_after="ren_guest_section",
                           description="Comma separated, e.g. VIP, Regular, Window seat"),
        ren_guest_notes=dict(label="Guest Notes", fieldtype="Small Text", insert_after="ren_guest_tags",
                            description="Allergies and preferences; the host stand shows them"),
    ),
    "Item Group": dict(
        icon=dict(label="Icon", fieldtype="Data"),
        color=dict(label="Color", fieldtype="Color"),
    ),
    "Item": dict(
        # everything restaurant-related in its own "Restaurant" tab at the end of the Item form
        ren_restaurant_tab=dict(label="Restaurant", fieldtype="Tab Break", insert_after="dashboard_tab"),
        ren_options_section=dict(
            label="Options & Components", fieldtype="Section Break", insert_after="ren_restaurant_tab",
            description="What the waiter can choose when the item is ordered. Components are items: "
                        "Included (comes with it, can be removed) or Optional (can be added or chosen). "
                        "A row without a component is an instruction for the kitchen (cooking point, no salt). "
                        "Sizes are ERPNext variants: set the options on the template, every variant uses them.",
        ),
        ren_price_from_components=dict(
            label="Price from Components", fieldtype="Check", insert_after="ren_options_section",
            description="On: the item's price is the sum of what is chosen (build your own). "
                        "Off: the item's own price, adjusted by the options that change the price.",
        ),
        ren_route_components=dict(
            label="Send components to their stations", fieldtype="Check", insert_after="ren_price_from_components",
            description="For combos: each component that is a menu item (burger, fries, drink) goes to the "
                        "production center of its own item group, with its own status.",
        ),
        ren_option_factor=dict(
            label="Option price factor", fieldtype="Float", default="1", insert_after="ren_route_components",
            depends_on="eval:doc.variant_of", no_copy=1,
            description="For a size: the prices of sections marked \"Price by size\" are multiplied by this "
                        "(Small 1, Large 1.5).",
        ),
        ren_option_sections=dict(
            label="Sections", fieldtype="Table", options="Ren Item Option Section", insert_after="ren_option_factor",
            no_copy=1,
            description="Rules of each section (choose 1, up to 3, 2 free...) and shared Option Lists. "
                        "Options without a section go in \"Ingredients\".",
        ),
        ren_options=dict(
            label="Options", fieldtype="Table", options="Ren Item Option", insert_after="ren_option_sections", no_copy=1,
        ),
        ren_recipe_section=dict(label="Recipe", fieldtype="Section Break", insert_after="ren_options"),
        ren_recipe=dict(
            label="Recipe (BOM)", fieldtype="Link", options="BOM", insert_after="ren_recipe_section", no_copy=1,
            description="Ingredients for one unit, taken out of stock when it's sold (once per shift). "
                        "Empty: the item's default BOM. Only for items that aren't kept in stock.",
        ),
        ren_recipe_column=dict(fieldtype="Column Break", insert_after="ren_recipe"),
        ren_recipe_cost=dict(label="Recipe Cost", fieldtype="Currency", read_only=1, insert_after="ren_recipe_column",
                            description="Cost of one unit from the recipe's costing"),
        ren_menu_section=dict(label="Menu", fieldtype="Section Break", insert_after="ren_recipe_cost"),
        item_type=dict(label="Item Type", fieldtype="Select", options="Veg\nNon-Veg\nVeg/Non-Veg", insert_after="ren_menu_section"),
        ren_tags=dict(label="Dietary & Allergens", fieldtype="Table MultiSelect", options="Ren Item Menu Tag",
                     insert_after="item_type", description="Menu Tags: shown on the item and used as catalog filters"),
        column_break_29=dict(fieldtype="Column Break", insert_after="ren_tags"),
        cuisine=dict(label="Cuisine", fieldtype="Link", options="Ren Cuisine Type", insert_after="column_break_29"),
    ),
}

# custom fields of older versions: deleted if a site still has them
obsolete_fields = {
    "POS Profile User": ["parent", "parenttype", "restaurant_permissions", "restaurant_permission"],
    "POS Profile": ["restaurant_settings", "crm_room", "column_break_1", "crm_table"],
    "Item": ["customizable", "is_customizable", "customizable_options", "rm_modifiers_section", "section_break_27"],
    "POS Invoice Item": ["from_customize", "customize_parent"],
    "Sales Invoice Item": ["from_customize", "customize_parent"],
    "Address": ["branch"],
}

def after_install():
    clear_custom_fields()
    set_custom_fields()
    set_custom_scripts()
    set_default_data()


def clear_custom_fields():
    for doctype, names in obsolete_fields.items():
        for fieldname in names:
            name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
            if name:
                frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


def set_default_data():
    from renpos.api.voids import install_default_reasons
    install_default_reasons()
    from renpos.api.menus import install_default_tags
    install_default_tags()
    from renpos.api.access import install_default_roles
    install_default_roles()
    from renpos.api.modifiers import install_default_modes
    install_default_modes()
    
    set_default_process_status()
    set_cuisine_types()

def set_default_process_status():
    """
    Order line statuses. message: how the status is shown; action_message:
    the button that leads to it ("Send" -> Sent/Waiting, "Start" ->
    Processing, "Complete" -> Completed).
    """
    status = [
        dict(
            action="Draft", icon="fa fa-pencil", color="grey",
            message="Draft", action_message="Create", allows_to_edit_item="1"
        ),
        dict(
            action="Opened", icon="fa fa-open", color="grey",
            message="Opened", action_message="Open", allows_to_edit_item="1"
        ),
        dict(
            action="Pending",icon="fa fa-cart-arrow-down", color="red",
            message="Pending", action_message="Add", allows_to_edit_item="1"
        ),
        dict(
            action="Attending",icon="fa fa-cart-arrow-down", color="orange",
            message="Attending", action_message="Take", allows_to_edit_item="1"
        ),
        dict(
            action="Sent", icon="fa fa-paper-plane-o", color="steelblue",
            message="Waiting", action_message="Send", allows_to_edit_item="0"
        ),
        dict(
            action="Processing", icon="fa fa-gear", color="#618685",
            message="Processing", action_message="Start", allows_to_edit_item="0"
        ),
        dict(
            action="Completed", icon="fa fa-check", color="green",
            message="Completed", action_message="Complete", allows_to_edit_item="0", kind="Ready"
        ),
        dict(
            action="Delivering", icon="fa fa-reply", color="#ff7b25",
            message="Delivering", action_message="Pick up", allows_to_edit_item="0"
        ),
        dict(
            action="On the way", icon="fa fa-truck", color="#7c3aed",
            message="On the way", action_message="Dispatch", allows_to_edit_item="0", ask_driver=1
        ),
        dict(
            action="Delivered", icon="fa fa-cutlery", color="green",
            message='Delivered', action_message="Deliver", allows_to_edit_item="0", kind="Finished"
        ),
        dict(
            action="Invoiced", icon="fa fa-money", color="green",
            message="Invoiced", action_message="Invoice", allows_to_edit_item="0"
        ),
        dict(
            action="Cancelled", icon="fa fa-close", color="red",
            message="Cancelled", action_message="Cancel", allows_to_edit_item="0"
        ),
        dict(
            action="Closed", icon="fa fa-close", color="red",
            message="Closed", action_message="Close", allows_to_edit_item="0"
        ),
        dict(
            action="Rejected", icon="fa fa-close", color="red",
            message="Rejected", action_message="Reject", allows_to_edit_item="0"
        ),
        dict(
            action="Returned", icon="fa fa-close", color="red",
            message="Returned", action_message="Return", allows_to_edit_item="0"
        ),
        dict(
            action="Refunded", icon="fa fa-close", color="red",
            message="Refunded", action_message="Refund", allows_to_edit_item="0"
        )
    ]

    for status in status:
        if not frappe.db.exists("Ren Order Status", status["action"]):
            frappe.get_doc({"doctype": "Ren Order Status", **status}).insert(ignore_permissions=True)
            continue
        # existing statuses keep what the restaurant customized; only the
        # button text written by older versions is moved to the new meaning
        current = frappe.db.get_value("Ren Order Status", status["action"], "action_message")
        if not current or current == LEGACY_ACTIONS.get(status["action"]):
            frappe.db.set_value("Ren Order Status", status["action"], "action_message", status["action_message"])


# Before 2.0 the action text was what to do *from* a status; now it is the
# verb that leads *to* it (the kitchen button shows the next status's action).
LEGACY_ACTIONS = {"Draft": "Submit", "Opened": "Take", "Pending": "Add", "Attending": "Sent", "Sent": "Confirm", "Processing": "Complete", "Completed": "Deliver", "Delivering": "Deliver", "Delivered": "Invoice", "Invoiced": "Invoiced", "Cancelled": "Cancelled", "Closed": "Closed", "Rejected": "Rejected", "Returned": "Returned", "Refunded": "Refunded"}

def set_cuisine_types():
    for cuisine in ["American", "Asian", "Barbecue", "Chinese", "Continental", "French", "Indian", "Italian",
                    "Japanese", "Mediterranean", "Mexican", "Middle Eastern", "Thai", "Vietnamese"]:
        if not frappe.db.exists("Ren Cuisine Type", cuisine):
            frappe.get_doc({"doctype": "Ren Cuisine Type", "description": cuisine}).insert(ignore_permissions=True)


def set_custom_fields():
    for doc in custom_fields:
        for field_name in custom_fields[doc]:
            test_field = frappe.get_value(
                "Custom Field", doc + "-" + field_name)

            if test_field is None or field_name != "ren_tax_inclusive":
                CF = frappe.new_doc("Custom Field") if test_field is None else frappe.get_doc(
                    "Custom Field", test_field)

                _values = dict(chain.from_iterable(d.items() for d in (
                    custom_fields[doc][field_name], dict(dt=doc, fieldname=field_name))))

                for key in _values:
                    CF.set(key, _values[key])

                CF.insert() if test_field is None else CF.save()


def set_custom_scripts():
    """Nothing to add: staff access lives in Ren Staff now (the old POS Profile script is removed by a patch)."""
    return


def set_custom_script(document, script,  apply_to="Form"):
    script_name = document + "-" + apply_to
    test_script = frappe.get_value("Client Script", script_name)
    
    if test_script is None:
        CS = frappe.new_doc("Client Script")
        CS.set("name", script_name)
    else:
        CS = frappe.get_doc("Client Script", test_script)

    CS.set("enabled", 1)
    CS.set("view", "Form")
    CS.set("dt", document)
    CS.set("script", script)

    CS.insert() if test_script is None else CS.save()
