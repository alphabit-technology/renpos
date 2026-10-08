# -*- coding: utf-8 -*-
"""Thermal printing: ESC/POS tickets, kitchen routing, receipts, drawer, failures."""

import json
import socket
import threading

import frappe
from frappe.tests.utils import FrappeTestCase

from renpos.api import order as order_api
from renpos.api import printing
from renpos.tests.test_kitchen import make_station
from renpos.tests.test_order_flow import (
	ITEM_A, ITEM_B, PROFILE, WAITER, open_register, setup_fixtures, _ensure_item,
)

ITEM_DRINK = "_REN-LEMONADE"
DRINKS_GROUP = "_REN Drinks"


class FakePrinter:
	"""A TCP server that records what printers would receive."""

	def __init__(self):
		self.sock = socket.socket()
		self.sock.bind(("127.0.0.1", 0))
		self.sock.listen(5)
		self.port = self.sock.getsockname()[1]
		self.received = []
		self.thread = threading.Thread(target=self._serve, daemon=True)
		self.thread.start()

	def _serve(self):
		while True:
			try:
				conn, _addr = self.sock.accept()
			except OSError:
				return
			data = b""
			with conn:
				while chunk := conn.recv(65536):
					data += chunk
			self.received.append(data)

	def wait(self, n, timeout=3):
		import time
		end = time.time() + timeout
		while len(self.received) < n and time.time() < end:
			time.sleep(0.02)
		return self.received

	def close(self):
		self.sock.close()


def _printer(name, port, **kw):
	if frappe.db.exists("Ren Printer", name):
		frappe.delete_doc("Ren Printer", name, force=True, ignore_permissions=True)
	return frappe.get_doc({"doctype": "Ren Printer", "printer_name": name, "host": "127.0.0.1",
	                       "port": port, **kw}).insert(ignore_permissions=True).name


def _free_port():
	s = socket.socket()
	s.bind(("127.0.0.1", 0))
	port = s.getsockname()[1]
	s.close()
	return port


class TestPrinting(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fx = setup_fixtures()
		cls.kitchen_hw = FakePrinter()
		cls.bar_hw = FakePrinter()
		cls.front_hw = FakePrinter()
		cls.kitchen_printer = _printer("_REN Kitchen Printer", cls.kitchen_hw.port, beep=1)
		cls.bar_printer = _printer("_REN Bar Printer", cls.bar_hw.port, paper_width="58 mm")
		cls.front_printer = _printer("_REN Front Printer", cls.front_hw.port)

		if not frappe.db.exists("Item Group", DRINKS_GROUP):
			frappe.get_doc({"doctype": "Item Group", "item_group_name": DRINKS_GROUP,
			                "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)
		_ensure_item(ITEM_DRINK, 3)
		frappe.db.set_value("Item", ITEM_DRINK, "item_group", DRINKS_GROUP)

		kitchen = make_station(cls.fx["floor"])  # prepares "Products"
		frappe.db.set_value("Ren Station", kitchen, "printer", cls.kitchen_printer)
		bar = frappe.db.get_value("Ren Station", {"description": "_REN Bar"})
		if not bar:
			bar = frappe.get_doc({
				"doctype": "Ren Station", "description": "_REN Bar", "floor": cls.fx["floor"],
				"production_center_group": [{"item_group": DRINKS_GROUP}],
				"status_flow": [{"status": "Sent"}, {"status": "Completed"}],
			}).insert(ignore_permissions=True).name
		frappe.db.set_value("Ren Station", bar, "printer", cls.bar_printer)

		frappe.db.set_value("POS Profile", PROFILE, {
			"ren_receipt_printer": cls.front_printer, "ren_print_kitchen_tickets": 1,
			"ren_print_receipt_on_payment": 1, "ren_open_drawer_on_cash": 1,
		})
		frappe.clear_document_cache("POS Profile", PROFILE)

	@classmethod
	def tearDownClass(cls):
		for hw in (cls.kitchen_hw, cls.bar_hw, cls.front_hw):
			hw.close()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def order(self, items):
		frappe.set_user(WAITER)
		order = order_api.add_order(self.fx["table"])["order"]["data"]["name"]
		for code, qty, plr, notes in items:
			order_api.push_item(order, json.dumps({
				"identifier": frappe.generate_hash(length=8), "item_code": code, "qty": qty, "notes": notes,
				"price_list_rate": plr, "rate": plr, "discount_percentage": 0, "item_tax_rate": "{}",
			}))
		return order

	def test_ticket_bytes(self):
		t = printing.Ticket(32).line("Hola señor", bold=True, align="center").cols("Burger", "10.00").drawer().cut()
		data = t.bytes()
		self.assertTrue(data.startswith(b"\x1b@"))
		self.assertIn("señor".encode("cp1252"), data)
		self.assertIn(b"\x1bp\x00", data)          # drawer kick
		self.assertIn(b"\x1dV", data)              # cut
		self.assertIn("Burger" + " " * 21 + "10.00", t.text())

	def test_send_routes_tickets_by_station(self):
		start = (len(self.kitchen_hw.received), len(self.bar_hw.received))
		order = self.order([(ITEM_A, 2, 10, "no onions"), (ITEM_DRINK, 1, 3, None)])
		order_api.send_order(order)

		kitchen = self.kitchen_hw.wait(start[0] + 1)[-1]
		bar = self.bar_hw.wait(start[1] + 1)[-1]
		self.assertIn(b"2 x " + ITEM_A.encode(), kitchen)
		self.assertIn(b"no onions", kitchen)
		self.assertNotIn(ITEM_DRINK.encode(), kitchen)
		self.assertIn(b"\x1bB", kitchen)                 # beep enabled on the kitchen printer
		self.assertIn(b"1 x " + ITEM_DRINK.encode(), bar)
		self.assertNotIn(ITEM_A.encode(), bar)

		jobs = frappe.get_all("Ren Print Job", filters={"reference_name": order, "job_type": "Kitchen"},
		                      fields=["printer", "status"])
		self.assertEqual({(j.printer, j.status) for j in jobs},
		                 {(self.kitchen_printer, "Printed"), (self.bar_printer, "Printed")})

		# sending more items prints only the new ones
		order_api.push_item(order, json.dumps({
			"identifier": "p-more", "item_code": ITEM_B, "qty": 1, "price_list_rate": 2.5, "rate": 2.5,
			"discount_percentage": 0, "item_tax_rate": "{}",
		}))
		order_api.send_order(order)
		again = self.kitchen_hw.wait(start[0] + 2)[-1]
		self.assertIn(ITEM_B.encode(), again)
		self.assertNotIn(b"2 x " + ITEM_A.encode(), again)

	def test_bill_and_receipt_with_drawer(self):
		frappe.set_user("Administrator")
		open_register(WAITER, self.fx["company"])
		order = self.order([(ITEM_A, 1, 10, None)])
		n = len(self.front_hw.received)
		printing.print_bill(order)
		bill = self.front_hw.wait(n + 1)[-1]
		self.assertIn(b"TOTAL", bill)
		self.assertNotIn(b"\x1bp\x00", bill)             # a bill never opens the drawer

		res = order_api.process_payment(order, json.dumps([{"mode_of_payment": "Cash", "amount": 20}]))
		self.assertTrue(res["print_job"])
		receipt = self.front_hw.wait(n + 2)[-1]
		self.assertIn(b"\x1bp\x00", receipt)             # cash -> drawer
		self.assertIn(b"Change", receipt)

	def test_card_payment_keeps_drawer_closed(self):
		frappe.set_user("Administrator")
		open_register(WAITER, self.fx["company"])
		order = self.order([(ITEM_B, 1, 2.5, None)])
		n = len(self.front_hw.received)
		order_api.process_payment(order, json.dumps([{"mode_of_payment": "Credit Card", "amount": 2.5}]))
		receipt = self.front_hw.wait(n + 1)[-1]
		self.assertNotIn(b"\x1bp\x00", receipt)

	def test_offline_printer_fails_without_blocking(self):
		frappe.set_user("Administrator")
		dead = _printer("_REN Dead Printer", _free_port())
		t = printing.Ticket(48).line("hello")
		job = printing.queue_job(dead, "Test", t)
		self.assertEqual(frappe.db.get_value("Ren Print Job", job, "status"), "Failed")
		self.assertTrue(frappe.db.get_value("Ren Print Job", job, "error"))

		# the order is still sent when a station printer is down
		kitchen = frappe.db.get_value("Ren Station", {"description": "_REN Kitchen"})
		frappe.db.set_value("Ren Station", kitchen, "printer", dead)
		try:
			order = self.order([(ITEM_A, 1, 10, None)])
			order_api.send_order(order)
			self.assertEqual(frappe.db.get_value("Ren Order Item", {"parent": order}, "status"), "Sent")
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Ren Station", kitchen, "printer", self.kitchen_printer)

		# retry once the printer is back (point the job's printer at a live one)
		frappe.db.set_value("Ren Printer", dead, "port", self.front_hw.port)
		frappe.clear_document_cache("Ren Printer", dead)
		n = len(self.front_hw.received)
		frappe.set_user(WAITER)
		self.assertEqual(printing.retry_job(job), "Printed")
		self.assertIn(b"hello", self.front_hw.wait(n + 1)[-1])

	def test_drawer_needs_cashier(self):
		from renpos.tests.test_order_flow import MANAGER
		frappe.set_user(MANAGER)
		self.assertRaises(frappe.PermissionError, printing.open_drawer, PROFILE)

	def test_waiter_cant_reopen_drawer(self):
		frappe.set_user("Administrator")
		job = printing.queue_job(self.front_printer, "Drawer", printing.Ticket(48).drawer())
		frappe.db.set_value("Ren Print Job", job, "status", "Failed")
		from renpos.tests.test_order_flow import MANAGER
		frappe.set_user(MANAGER)
		self.assertRaises(frappe.PermissionError, printing.retry_job, job)
