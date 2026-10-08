# -*- coding: utf-8 -*-
"""A combo whose parts are prepared at their own production centers (api/parts.py)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from renpos.api import kitchen as kitchen_api
from renpos.api import order as order_api
from renpos.api import parts as parts_api
from renpos.tests.test_kitchen import ensure_group, make_station
from renpos.tests.test_modifiers import ensure_variants, opt, set_options
from renpos.tests.test_order_flow import WAITER, _ensure_item, setup_fixtures

COMBO = "_REN-ROUTED-COMBO"
BURGER = "_REN-ROUTED-BURGER"
SODA = "_REN-ROUTED-SODA"   # sizes Small / Large


def _group_of(codes, group):
    for c in codes:
        frappe.db.set_value("Item", c, "item_group", group)


class TestComboParts(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.fx = setup_fixtures()
        grill, bar, combos = ensure_group("_REN Grill"), ensure_group("_REN Bar"), ensure_group("_REN Combos")
        cls.grill = make_station(cls.fx["floor"], "_REN Grill Station", groups=(grill,))
        cls.bar = make_station(cls.fx["floor"], "_REN Bar Station", flow=("Sent", "Completed"), groups=(bar,))
        cls.expo = make_station(cls.fx["floor"], "_REN Expo", flow=("Completed", "Delivered"), groups=(combos,))
        _ensure_item(BURGER, 9)
        _ensure_item(COMBO, 12)
        cls.sizes = ensure_variants(SODA, {"Small": 2, "Large": 3})
        _group_of([BURGER], grill)
        _group_of([SODA, *cls.sizes.values()], bar)
        _group_of([COMBO], combos)
        set_options(BURGER, [{"role": "Included", "label": "Tomato", "price": 0.5}])
        set_options(COMBO, [
            {"section": "Burger", "role": "Included", "item": BURGER},
            {"section": "Drink", "role": "Included", "item": SODA},
            {"section": "Drink", "role": "Included", "label": "Extra napkins"},
        ])
        frappe.db.set_value("Item", COMBO, "ren_route_components", 1)
        frappe.clear_cache(doctype="Item")

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        set_options(COMBO, [])
        set_options(BURGER, [])
        super().tearDownClass()

    def tearDown(self):
        frappe.set_user("Administrator")

    def order(self):
        frappe.set_user(WAITER)
        order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
        burger, soda = opt(COMBO, BURGER), opt(COMBO, SODA)
        ident = "parts-" + frappe.generate_hash(length=6)
        order_api.push_item(order, json.dumps({
            "identifier": ident, "item_code": COMBO, "qty": 2, "price_list_rate": 0, "rate": 0,
            "discount_percentage": 0, "item_tax_rate": "{}",
            "modifiers": [{"option": burger}, {"option": soda}, {"option": opt(COMBO, "Extra napkins")},
                          {"option": f"{SODA}::{self.sizes['Large']}", "parent": soda}],  # no tomato
        }))
        order_api.send_order(order)
        frappe.set_user("Administrator")
        return order, ident, burger, soda

    def items(self, station, order):
        q = kitchen_api.get_station_queue(station)
        return [i for t in q["tickets"] if t["order"] == order for i in t["items"]]

    def status(self, ident):
        return frappe.db.get_value("Ren Order Item", {"identifier": ident}, "status")

    def test_each_part_goes_to_its_center(self):
        order, ident, burger, soda = self.order()
        parts = json.loads(frappe.db.get_value("Ren Order Item", {"identifier": ident}, "ren_parts"))
        self.assertEqual([p["item"] for p in parts], [BURGER, self.sizes["Large"]])  # not the napkins

        grill = self.items(self.grill, order)
        self.assertEqual([(i["identifier"], i["item_name"], i["qty"], i["modifiers"]) for i in grill],
                         [(f"{ident}~{burger}", BURGER, 2, ["NO Tomato"])])
        bar = self.items(self.bar, order)
        self.assertEqual([(i["item_name"], i["item_code"]) for i in bar], [(f"{SODA} Large", self.sizes["Large"])])
        self.assertEqual(self.items(self.expo, order), [])

        # printing routes the same way
        row = frappe.get_all("Ren Order Item", filters={"identifier": ident}, fields=["*"])[0]
        printed = parts_api.route([row], lambda g: g == "_REN Grill")
        self.assertEqual([r.item_name for r in printed], [BURGER])

    def test_the_line_follows_its_least_advanced_part(self):
        order, ident, burger, soda = self.order()
        kitchen_api.advance(self.grill, identifier=f"{ident}~{burger}")
        kitchen_api.advance(self.grill, identifier=f"{ident}~{burger}")
        self.assertEqual(self.status(ident), "Sent")  # the soda isn't ready
        self.assertEqual(self.items(self.grill, order), [])

        kitchen_api.advance(self.bar, identifier=f"{ident}~{soda}")
        self.assertEqual(self.status(ident), "Completed")
        expo = self.items(self.expo, order)
        self.assertEqual([i["identifier"] for i in expo], [ident])  # the whole combo, to be delivered

        # recall the soda at the bar: the combo is back to Sent
        log = next(l for l in kitchen_api.get_recent(self.bar) if l["identifier"] == f"{ident}~{soda}")
        self.assertTrue(log["can_undo"])
        kitchen_api.undo(self.bar, log["name"])
        self.assertEqual(self.status(ident), "Sent")
        self.assertEqual(len(self.items(self.bar, order)), 1)

    def test_a_double_tap_doesnt_skip_a_step(self):
        order, ident, burger, soda = self.order()
        kitchen_api.advance(self.grill, identifier=f"{ident}~{burger}", expected="Sent")
        self.assertRaises(kitchen_api.KitchenConflict, kitchen_api.advance, self.grill,
                          identifier=f"{ident}~{burger}", expected="Sent")
