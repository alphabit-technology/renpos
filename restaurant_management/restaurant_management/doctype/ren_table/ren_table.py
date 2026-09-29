import frappe
from frappe import _
from frappe.utils import get_datetime
from datetime import timedelta
from restaurant_management.restaurant_management.doctype.ren_base import RenBase


class RenTable(RenBase):
    @property
    def room_doc(self):
        return frappe.get_doc("Ren Room", self.room)

    """ def on_update(self):
        if self.customer:
            current_reservation = self.current_reservation("customer")

            if (current_reservation and current_reservation != self.customer
                    and self.orders_count > 0):
                frappe.throw(_(
                    "You can't set {0} because there is an active reservation for {1}"
                ).format(self.customer, current_reservation))

            frappe.msgprint(_(
                "The table {0} is assigned to {1}"
            ).format(self.description, self.customer), indicator='green', alert=True)

        data = self.get_table_data()
        self.publish_update(data)
        self.synchronize() """

    def synchronize(self):
        self.publish_notifications()
        # Also notify the parent room
        room = self.room_doc
        room.publish_notifications(room.orders_count)

    def get_obj_data(self):
        fields = ("name,description,no_of_seats,identifier,orders_count,data_style,min_size,current_user,color,shape,customer,room")
        data = self.get_data(fields)
        data["status"] = self.status

        return data

    def validate_transaction(self, user=None, from_crm=None):
        user = user or frappe.session.user

        if not self.can_access():
            frappe.throw(_("You don't have access to this table"))

        if self.current_user is None or self.current_user == "Administrator" or self.orders_count == 0:
            frappe.db.set_value("Ren Table", self.name, "current_user", user)
            frappe.db.commit()
            self.reload()
            return True

        if self.current_user != user and self.orders_count > 0:
            from restaurant_management.restaurant_management.restaurant_manage import check_exceptions
            if not check_exceptions(
                dict(name="Ren Table", short_name="table", action="read", data=self),
                _("The table {0} is Assigned to another User").format(self.description)
            ):
                frappe.throw(_(
                    "The table {0} is Assigned to another User"
                ).format(self.description))

    def validate_table(self, from_crm=None):
        settings = frappe.get_single("Restaurant Settings")
        if from_crm is None and not settings.multiple_pending_order and self.orders_count > 0:
            frappe.throw(_("Complete pending orders"))

    def add_order(self, client=None, from_crm=None):
        self.validate_transaction(frappe.session.user, from_crm)

        if self.customer is None:
            frappe.throw(_("You must set a customer to this table"))

        self.validate_table(from_crm)

        from erpnext.stock.get_item_details import get_pos_profile

        company = frappe.defaults.get_user_default('company')
        pos_profile = get_pos_profile(company)

        order = frappe.new_doc("Table Order")
        order.customer = self.customer

        if pos_profile:
            order.pos_profile = pos_profile.name
            order.customer = frappe.db.get_value('POS Profile', pos_profile.name, 'customer')
            order.taxes_and_charges = frappe.db.get_value(
                'POS Profile', pos_profile.name, 'taxes_and_charges')
        else:
            frappe.throw(_("POS Profile is required to use Point-of-Sale"))

        order.selling_price_list = frappe.db.get_value('Price List', dict(enabled="1"))
        order.table = self.name

        if from_crm is not None:
            order.customer = from_crm
            order.is_delivery = 1

        order.save()
        order.synchronize(dict(action="Add", client=client))
        return order

    def orders_list(self, name=None, customer=None):
        orders = frappe.get_all("Table Order", fields=["name", "customer"], filters={
            "table" if name is None else "name": name or self.name,
            "show_in_pos": 1,
            "status": ("not in", ["Cancelled", "Invoiced"])
        })

        current_order = None

        for order in orders:
            data = frappe.get_doc("Table Order", order.name).short_data()
            if customer and order.customer == customer:
                current_order = order.name

            for field in data:
                order[field] = data[field]

        return dict(orders=orders, order=current_order)

    @property
    def orders_count(self):
        return frappe.db.count("Table Order", {
            "company": self.company,
            "table": self.name,
            "show_in_pos": 1,
            "status": ["not in", ["Cancelled", "Invoiced", "Opened"]],
        })

    @property
    def status(self):
        return "Available" if self.is_enabled_to_reservation() else "Reserved"

    def is_enabled_to_reservation(self, reservation=None):
        if reservation is not None:
            count = frappe.db.count("Restaurant Booking", filters=dict(
                table=self.name,
                status=("in", ("Open", "Waitlisted")),
                reservation_end_time=(">", get_datetime(
                    get_datetime(reservation.reservation_time) - timedelta(minutes=30))),
                reservation_time=("<", get_datetime(
                    get_datetime(reservation.reservation_end_time) + timedelta(minutes=30))),
                name=("!=", reservation.name)
            ))

            if count == 0:
                return True

            if self.orders_count > 0:
                orders = frappe.get_list("Table Order", fields=["customer", "creation"], filters={
                    "table": self.name,
                    "show_in_pos": 1,
                    "status": ("not in", ["Cancelled", "Invoiced"])
                })

                if orders:
                    last_order = sorted(orders, key=lambda x: x["creation"])[-1]
                    order_time = get_datetime(last_order.creation)
                    res_start = get_datetime(
                        get_datetime(reservation.reservation_time) - timedelta(minutes=30))
                    res_end = get_datetime(
                        get_datetime(reservation.reservation_end_time) + timedelta(minutes=30))

                    if res_start < order_time < res_end:
                        frappe.throw(_(
                            "You can't set {0} in table {1} because there is an active order for {2} for reservation time"
                        ).format(reservation.customer, self.description, last_order.customer))

            return True
        else:
            return frappe.db.count("Restaurant Booking", filters=dict(
                table=self.name,
                status=("in", ("Open", "Waitlisted")),
                reservation_time=(">", get_datetime(
                    get_datetime() - timedelta(minutes=30)))
            )) == 0

    def current_reservation(self, field=None):
        return frappe.db.get_value("Restaurant Booking", dict(
            table=self.name,
            status=("in", ("Open", "Waitlisted")),
            reservation_time=("<=", get_datetime(
                get_datetime() + timedelta(minutes=30))),
            reservation_end_time=(">=", get_datetime(
                get_datetime() - timedelta(minutes=30)))
        ), field or "name")