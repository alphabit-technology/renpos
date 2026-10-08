import frappe
from datetime import timedelta
from renpos.ren_pos.doctype.ren_base import RenBase


class RenTable(RenBase):
    def validate(self):
        # the same name can be used by another restaurant (every branch has a "Table 1")
        if self.description and self.room:
            restaurant = frappe.db.sql("""SELECT f.restaurant FROM `tabRen Room` r JOIN `tabRen Floor` f ON f.name = r.floor
                WHERE r.name = %s""", self.room)
            restaurant = restaurant[0][0] if restaurant else None
            taken = frappe.db.sql("""SELECT t.name FROM `tabRen Table` t JOIN `tabRen Room` r ON r.name = t.room
                JOIN `tabRen Floor` f ON f.name = r.floor
                WHERE t.description = %s AND t.name != %s AND IFNULL(f.restaurant, '') = IFNULL(%s, '') LIMIT 1""",
                (self.description, self.name or "", restaurant))
            if taken:
                frappe.throw(frappe._("There is already a table {0} in this restaurant").format(frappe.bold(self.description)),
                             frappe.UniqueValidationError)

    @property
    def room_doc(self):
        return frappe.get_doc("Ren Room", self.room)

    def synchronize(self):
        self.publish_notifications()
        # Also notify the parent room
        room = self.room_doc
        room.publish_notifications(room.orders_count)

    def get_obj_data(self):
        fields = ("name,description,no_of_seats,identifier,orders_count,data_style,min_size,current_user,color,shape,customer,room")
        data = self.get_data(fields)
        data["reservation"] = self.reservation
        data["status"] = "Reserved" if data["reservation"] else "Available"

        return data

    @property
    def orders_count(self):
        return frappe.db.count("Ren Order", {
            "company": self.company,
            "table": self.name,
            "show_in_pos": 1,
            "status": ["not in", ["Cancelled", "Invoiced", "Opened"]],
        })

    @property
    def status(self):
        return "Reserved" if self.current_reservation() else "Available"

    def current_reservation(self, field=None):
        """
        The reservation holding this table now: from the restaurant's
        "hold table before" minutes before its time until it is seated,
        cancelled or marked No Show.
        """
        from renpos.api import booking as B
        now = frappe.utils.now_datetime()
        rows = frappe.db.sql(
            """SELECT DISTINCT b.name, b.restaurant, b.starts_at, b.customer_name, b.party_size, b.status
            FROM `tabRen Booking` b
            LEFT JOIN `tabRen Booking Table` x ON x.parent = b.name AND x.parenttype = 'Ren Booking'
            WHERE b.status IN ('Open', 'Confirmed') AND (b.`table` = %(t)s OR x.`table` = %(t)s)
              AND b.starts_at < %(until)s AND b.ends_at > %(now)s
            ORDER BY b.starts_at LIMIT 3""",
            {"t": self.name, "now": now, "until": now + timedelta(hours=12)}, as_dict=True)
        for r in rows:
            before = frappe.utils.cint(B.get_policy(r.restaurant).reserved_before_minutes)
            if frappe.utils.get_datetime(r.starts_at) - timedelta(minutes=before) <= now:
                return r.get(field) if field else r
        return None

    @property
    def reservation(self):
        """Shown on the floor plan: who the table is held for, and when."""
        r = self.current_reservation()
        if not r:
            return None
        return {"name": r.name, "guest": r.customer_name, "party_size": r.party_size,
                "time": frappe.utils.get_datetime(r.starts_at).strftime("%H:%M")}