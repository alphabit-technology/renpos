import frappe
from frappe import _
from frappe.model.document import Document


class RenBase(Document):
    """ @property
    def description(self):
        base = self.room if self.doctype == "Ren Table" else self.floor
        return f"{self.description} - {base}".strip(" -") """
        
    """ def on_load(self):
        base = self.room if self.doctype == "Ren Table" else self.floor
        self.description =f"{self.description} - {base}".strip(" -") """
        
    def after_delete(self):
        frappe.publish_realtime(self.room if self.doctype == "Ren Table" else self.floor, dict(
            _deleted=1,
            type=self.doctype,
            name=self.name
        ))

    def on_change(self):
        data = self.get_obj_data()
        frappe.publish_realtime(self.room if self.doctype == "Ren Table" else self.floor, data)
        self.publish_notifications()

    def publish_notifications(self, orders_count=None):
       frappe.publish_realtime(self.room if self.doctype == "Ren Table" else self.floor, dict(
          name=self.name,
          type=self.doctype,
          orders_count=orders_count or self.orders_count
       ))
       """  frappe.publish_realtime(self.name, dict(
            #action="Notifications",
            orders_count=orders_count or self.orders_count,
            #current_user=frappe.session.user
        )) """

    def set_attr(self, attr, value):
        frappe.db.set_value(self.doctype, self.name, attr, value)
        self.reload()
        self.on_change()
        #self.on_update()

    def can_access(self):
        settings = frappe.get_single("Restaurant Settings")
        if settings.user_has_admin_role():
            return True
        return self.name in settings.restaurant_access(self.doctype)

    def get_data(self, fields):
        data = {}
        for field in fields.split(","):
            data[field] = getattr(self, field, None)
            data["type"] = self.doctype

        return data

    @property
    def identifier(self):
        return self.name

    @property
    def min_size(self):
        return 80