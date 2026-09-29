"""
Fill the empty `company` of floors, rooms and tables from their parent
(restaurant -> floor -> room -> table). Table Order.company is mandatory and
fetched from the table, so tables without a company broke transfers.
"""

import frappe


def execute():
    frappe.db.sql(
        """
        UPDATE `tabRen Floor` f
        INNER JOIN `tabRen Restaurant` r ON r.name = f.restaurant
        SET f.company = r.company
        WHERE IFNULL(f.company, '') = '' AND IFNULL(r.company, '') != ''
        """
    )
    frappe.db.sql(
        """
        UPDATE `tabRen Room` rm
        INNER JOIN `tabRen Floor` f ON f.name = rm.floor
        SET rm.company = f.company
        WHERE IFNULL(rm.company, '') = '' AND IFNULL(f.company, '') != ''
        """
    )
    frappe.db.sql(
        """
        UPDATE `tabRen Table` t
        INNER JOIN `tabRen Room` rm ON rm.name = t.room
        SET t.company = rm.company
        WHERE IFNULL(t.company, '') = '' AND IFNULL(rm.company, '') != ''
        """
    )
