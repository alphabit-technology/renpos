# -*- coding: utf-8 -*-
"""Recipes: the dish's BOM, adjusted by its options, leaves stock once per shift."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from renpos.api import order as order_api
from renpos.api import recipes
from renpos.tests.test_modifiers import ensure_variants, opt, set_options
from renpos.tests.test_order_flow import (
    PROFILE, WAITER, _abbr, _ensure_item, open_register, setup_fixtures,
)

DISH = "_REN-RECIPE-BURGER"
COMBO = "_REN-RECIPE-COMBO"
CAN = "_REN-RECIPE-CAN"
BUN, BEEF, TOMATO, CHEESE = "_REN-ING-BUN", "_REN-ING-BEEF", "_REN-ING-TOMATO", "_REN-ING-CHEESE"


def _ingredient(code, rate):
    if not frappe.db.exists("Item", code):
        frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": "Products",
                        "stock_uom": "Nos", "is_stock_item": 1, "is_sales_item": 0,
                        "valuation_rate": rate}).insert(ignore_permissions=True)


class TestRecipes(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        cls.company = cls.fx["company"]
        cls.warehouse = f"Stores - {_abbr(cls.company)}"
        for code, rate in ((BUN, 0.5), (BEEF, 0.02), (TOMATO, 0.01), (CHEESE, 0.3)):
            _ingredient(code, rate)
        receipt = frappe.get_doc({
            "doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": cls.company,
            "items": [{"item_code": c, "qty": q, "t_warehouse": cls.warehouse, "basic_rate": r, "uom": "Nos",
                       "conversion_factor": 1}
                      for c, q, r in ((BUN, 100, 0.5), (BEEF, 10000, 0.02), (TOMATO, 5000, 0.01), (CHEESE, 100, 0.3))],
        })
        receipt.insert(ignore_permissions=True)
        receipt.submit()

        _ensure_item(DISH, 10)  # not a stock item
        bom = frappe.get_doc({"doctype": "BOM", "item": DISH, "company": cls.company, "quantity": 1,
                              "ren_cost_as_per": "Valuation Rate",
                              "items": [{"item_code": BUN, "qty": 1}, {"item_code": BEEF, "qty": 150},
                                        {"item_code": TOMATO, "qty": 30}]})
        bom.insert(ignore_permissions=True)
        bom.submit()
        cls.bom = bom.name
        frappe.db.set_value("Item", DISH, "ren_recipe", bom.name)

        set_options(DISH, [
            {"role": "Included", "label": "Tomato", "item": TOMATO, "qty": 30},
            {"label": "Cheese", "price": 1, "max_qty": 2, "item": CHEESE, "qty": 1},
        ])
        # a combo with no recipe: the dish (with its own options) and a can with sizes
        cls.cans = ensure_variants(CAN, {"Small": 1, "Large": 1.5}, stock=1)
        receipt = frappe.get_doc({
            "doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "company": cls.company,
            "items": [{"item_code": c, "qty": 50, "t_warehouse": cls.warehouse, "basic_rate": 0.4, "uom": "Nos",
                       "conversion_factor": 1} for c in cls.cans.values()],
        })
        receipt.insert(ignore_permissions=True)
        receipt.submit()
        _ensure_item(COMBO, 15)
        set_options(COMBO, [
            {"section": "Main", "role": "Included", "item": DISH, "label": "Burger"},
            {"section": "Drink", "role": "Included", "item": CAN, "label": "Soda"},
        ])
        frappe.db.set_value("POS Profile", PROFILE, "update_stock", 1)
        frappe.clear_document_cache("POS Profile", PROFILE)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.set_value("POS Profile", PROFILE, "update_stock", 0)
        frappe.clear_document_cache("POS Profile", PROFILE)
        set_options(DISH, [])
        set_options(COMBO, [])
        super().tearDownClass()

    def tearDown(self):
        frappe.set_user("Administrator")

    def opt(self, label):
        return opt(DISH, label)

    def test_line_usage_follows_the_options(self):
        mods = json.dumps([{"option": self.opt("Cheese"), "item": CHEESE, "qty": 2, "ingredient_qty": 1},
                           {"option": self.opt("Tomato"), "item": TOMATO, "included": 1, "removed": 1, "qty": 0}])
        self.assertEqual(recipes.line_usage(DISH, 2, mods), {BUN: 2, BEEF: 300, CHEESE: 4})
        self.assertEqual(recipes.line_usage(DISH, 1, None), {BUN: 1, BEEF: 150, TOMATO: 30})
        light = json.dumps([{"option": self.opt("Tomato"), "item": TOMATO, "included": 1, "qty": 1, "qty_factor": 0.5}])
        self.assertEqual(recipes.line_usage(DISH, 1, light)[TOMATO], 15)
        self.assertEqual(recipes.line_usage("_REN-NO-RECIPE", 1, None), {})

    def test_combo_uses_what_its_parts_use(self):
        burger, soda = opt(COMBO, "Burger"), opt(COMBO, "Soda")
        large = self.cans["Large"]
        mods = json.dumps([
            {"option": burger, "item": DISH, "included": 1, "qty": 1, "ingredient_qty": 1},
            {"option": self.opt("Tomato"), "parent": burger, "item": TOMATO, "included": 1, "removed": 1, "qty": 0},
            {"option": self.opt("Cheese"), "parent": burger, "item": CHEESE, "qty": 1, "ingredient_qty": 1},
            {"option": soda, "item": CAN, "included": 1, "qty": 1, "ingredient_qty": 1},
            {"option": f"{CAN}::{large}", "parent": soda, "item": large, "variant": 1, "qty": 1},
        ])
        self.assertEqual(recipes.line_usage(COMBO, 2, mods), {BUN: 2, BEEF: 300, CHEESE: 2, large: 2})

    def test_paid_orders_leave_stock_once_per_shift(self):
        open_register(WAITER, self.company)
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        order_api.push_item(order, json.dumps({
            "identifier": frappe.generate_hash(length=10), "item_code": DISH, "qty": 2, "price_list_rate": 0,
            "rate": 0, "discount_percentage": 0, "item_tax_rate": "{}",
            "modifiers": [{"option": self.opt("Cheese"), "qty": 2}],  # no tomato, double cheese
        }))
        due = flt(order_api.get_payment_summary(order)["amount_due"])
        res = order_api.process_payment(order, json.dumps([{"mode_of_payment": "Cash", "amount": due}]))
        inv = frappe.get_doc(res["invoice_doctype"], res["invoice"])
        self.assertEqual([r.item_code for r in inv.items], [DISH])  # the cheese leaves with the recipe, not here

        frappe.set_user("Administrator")
        entry = recipes.post_usage(PROFILE)
        self.assertTrue(entry)
        se = frappe.get_doc("Stock Entry", entry)
        self.assertEqual(se.docstatus, 1)
        used = {r.item_code: flt(r.qty) for r in se.items}
        self.assertEqual(used.get(BUN), 2)
        self.assertEqual(used.get(BEEF), 300)
        self.assertEqual(used.get(CHEESE), 4)
        self.assertNotIn(TOMATO, used)
        self.assertEqual(frappe.db.get_value("Ren Order", order, "ren_usage_entry"), entry)
        self.assertEqual(recipes.post_usage(PROFILE), "")  # counted once

    def test_item_recipe_rules(self):
        item = frappe.get_doc("Item", DISH)
        item.save(ignore_permissions=True)
        self.assertAlmostEqual(flt(item.ren_recipe_cost), 1 * 0.5 + 150 * 0.02 + 30 * 0.01, places=2)
        item.is_stock_item = 1
        self.assertRaises(frappe.ValidationError, item.save)

    def test_variance_report(self):
        from frappe.utils import today
        from renpos.ren_pos.report.ingredient_usage_variance import (
            ingredient_usage_variance as report,
        )
        open_register(WAITER, self.company)
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        order_api.push_item(order, json.dumps({
            "identifier": frappe.generate_hash(length=10), "item_code": DISH, "qty": 2, "price_list_rate": 0,
            "rate": 0, "discount_percentage": 0, "item_tax_rate": "{}",
            "modifiers": [{"option": self.opt("Tomato")}],
        }))
        due = flt(order_api.get_payment_summary(order)["amount_due"])
        order_api.process_payment(order, json.dumps([{"mode_of_payment": "Cash", "amount": due}]))
        frappe.set_user("Administrator")
        recipes.post_usage(PROFILE)

        # the count finds 30 g of beef fewer than the recipes explain
        from erpnext.stock.utils import get_stock_balance
        beef_now = flt(get_stock_balance(BEEF, self.warehouse))
        sr = frappe.get_doc({"doctype": "Stock Reconciliation", "company": self.company, "purpose": "Stock Reconciliation",
                             "items": [{"item_code": BEEF, "warehouse": self.warehouse, "qty": beef_now - 30,
                                        "valuation_rate": 0.02}]})
        sr.insert(ignore_permissions=True)
        sr.submit()

        _cols, rows = report.execute({"company": self.company, "warehouse": self.warehouse,
                                      "from_date": today(), "to_date": today()})
        beef = next(r for r in rows if r["item_code"] == BEEF)
        self.assertGreaterEqual(beef["theoretical"], 300)
        self.assertAlmostEqual(beef["actual"] - beef["theoretical"], 30)
        self.assertAlmostEqual(beef["variance_qty"], -30)
        self.assertAlmostEqual(beef["variance_value"], -0.6, places=2)
