import frappe
from frappe.model.document import Document


def next_free_description(doctype, prefix):
    """'{prefix}{n}' with the smallest n not used yet by any {doctype} (descriptions may be unique)."""
    used = set(frappe.get_all(doctype, filters={"description": ["like", f"{prefix}%"]}, pluck="description"))
    n = 1
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


class RenBase(Document):
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

    def set_attr(self, attr, value):
        frappe.db.set_value(self.doctype, self.name, attr, value)
        self.reload()
        self.on_change()

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