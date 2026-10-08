/**
 * OrderAPI — All server calls for the Order Management system.
 *
 * Single source of truth for API endpoints.
 * Each method returns a Promise.
 */

/**
 * Identifies this browser tab. Sent with every order call and echoed back
 * by the server in the "order_update" realtime event, so a tab can ignore
 * its own changes while other tabs (even with the same user) refresh.
 */
import { callWithApproval } from "@/utils/approval";

export const CLIENT_ID =
  (typeof crypto !== "undefined" && crypto.randomUUID)
    ? crypto.randomUUID()
    : `tab_${Date.now()}_${Math.random().toString(36).slice(2)}`;

// a manager PIN is asked when the person's role needs an approval (utils/approval.js)
function call(method, args = {}) {
  return callWithApproval(method, { ...args, client_id: CLIENT_ID });
}

const OrderAPI = {

  // ═══════════════════════════════════════════════
  // POS DATA (pre-load once on open)
  // ═══════════════════════════════════════════════

  /**
   * Load all data needed for client-side calculations.
   * Called ONCE when OrderManager opens.
   *
   * Returns: { items, price_list, taxes, pricing_rules, currency, tax_inclusive }
   *
   * ENDPOINT: renpos.api.pos.get_pos_data
   */
  getPosData(posProfile) {
    return call("renpos.api.pos.get_pos_data", {
      pos_profile: posProfile,
    });
  },

  // ═══════════════════════════════════════════════
  // ORDERS
  // ═══════════════════════════════════════════════

  /**
   * Get all orders for a table.
   *
   * Returns: { orders: [...], order: currentOrderName }
   *
   * ENDPOINT: renpos.api.order.get_orders
   */
  getOrders(tableName, customer = null) {
    return call("renpos.api.order.get_orders", {
      table_name: tableName,
      customer,
    });
  },

  /**
   * Create a new order for a table.
   *
   * Returns: { order: {...}, items: [] }
   *
   * ENDPOINT: renpos.api.order.add_order
   */
  addOrder(tableName) {
    return call("renpos.api.order.add_order", {
      table_name: tableName,
    });
  },

  /**
   * Delete an order.
   *
   * ENDPOINT: renpos.api.order.delete_order
   */
  deleteOrder(orderName, voidInfo) {
    return call("renpos.api.order.delete_order", {
      order_name: orderName,
      ...(voidInfo || {}),
    });
  },

  // ── Cash register (api/register.py) ──
  getRegister(posProfile) {
    return call("renpos.api.register.get_register", { pos_profile: posProfile });
  },
  openRegister(posProfile, balances) {
    return call("renpos.api.register.open_register", { pos_profile: posProfile, balances });
  },
  closeRegister(posProfile, counted, preview = 0, opening = null) {
    return call("renpos.api.register.close_register", {
      pos_profile: posProfile, counted, preview, ...(opening ? { opening } : {}),
    });
  },

  // ── Printing (api/printing.py) ──
  printBill(orderName) {
    return call("renpos.api.printing.print_bill", { order_name: orderName });
  },
  printReceipt(invoiceDoctype, invoice) {
    return call("renpos.api.printing.print_receipt", { invoice_doctype: invoiceDoctype, invoice });
  },
  openDrawer(posProfile) {
    return call("renpos.api.printing.open_drawer", { pos_profile: posProfile });
  },
  retryPrintJob(job) {
    return call("renpos.api.printing.retry_job", { job });
  },

  // ── Card readers (api/card.py) ──
  startCardPayment(orderName, reader, amount) {
    return call("renpos.api.card.start_card_payment", { order_name: orderName, reader, amount });
  },
  cardPaymentStatus(name) {
    return call("renpos.api.card.card_payment_status", { name });
  },
  cancelCardPayment(name) {
    return call("renpos.api.card.cancel_card_payment", { name });
  },

  getVoidReasons() {
    return call("renpos.api.voids.get_void_reasons");
  },

  /**
   * Get items for an order.
   *
   * Returns: { order: {...}, items: [...] }
   *
   * ENDPOINT: renpos.api.order.get_items
   */
  getItems(orderName) {
    return call("renpos.api.order.get_items", {
      order_name: orderName,
    });
  },

  // ═══════════════════════════════════════════════
  // ITEMS (add/update/delete)
  // ═══════════════════════════════════════════════

  /**
   * Push (add or update) an item in an order.
   *
   * The item is calculated CLIENT-SIDE before sending.
   * Server validates and persists.
   *
   * ENDPOINT: renpos.api.order.push_item
   */
  pushItem(orderName, item) {
    return call("renpos.api.order.push_item", {
      order_name: orderName,
      item,
    });
  },

  /**
   * Delete an item from an order.
   *
   * ENDPOINT: renpos.api.order.delete_item
   */
  deleteItem(orderName, identifier, voidInfo) {
    return call("renpos.api.order.delete_item", {
      order_name: orderName,
      identifier,
      ...(voidInfo || {}),
    });
  },

  // ═══════════════════════════════════════════════
  // ORDER ACTIONS
  // ═══════════════════════════════════════════════

  /**
   * Send order to kitchen (mark items as "Sent").
   *
   * Returns: { order: {...}, items: [...] }
   *
   * ENDPOINT: renpos.api.order.send_order
   */
  sendOrder(orderName, fire = false) {
    return call("renpos.api.order.send_order", {
      order_name: orderName,
      fire: fire ? 1 : 0,
    });
  },

  /**
   * Transfer order to another table.
   *
   * ENDPOINT: renpos.api.order.transfer_order
   */
  transferOrder(orderName, targetTable) {
    return call("renpos.api.order.transfer_order", {
      order_name: orderName,
      target_table: targetTable,
    });
  },

  /**
   * Divide (split) an order.
   *
   * @param {string} orderName
   * @param {object} items - { identifier: { name, qty, identifier } }
   *
   * ENDPOINT: renpos.api.order.divide_order
   */
  /** Tables of the restaurant for the transfer dialog. */
  getTransferTargets(orderName) {
    return call("renpos.api.order.get_transfer_targets", {
      order_name: orderName,
    });
  },

  divideOrder(orderName, items) {
    return call("renpos.api.order.divide_order", {
      order_name: orderName,
      items,
    });
  },

  // ═══════════════════════════════════════════════
  // CUSTOMER
  // ═══════════════════════════════════════════════

  /**
   * Set customer on an order.
   *
   * ENDPOINT: renpos.api.order.set_customer
   */
  setCustomer(orderName, customer) {
    return call("renpos.api.order.set_customer", {
      order_name: orderName,
      customer,
    });
  },

  /**
   * Set dinners (party size) on an order.
   *
   * ENDPOINT: renpos.api.order.set_dinners
   */
  setNotes(orderName, notes) {
    return call("renpos.api.order.set_notes", { order_name: orderName, notes });
  },

  setDinners(orderName, dinners) {
    return call("renpos.api.order.set_dinners", {
      order_name: orderName,
      dinners,
    });
  },

  // ═══════════════════════════════════════════════
  // PAYMENT
  // ═══════════════════════════════════════════════

  /**
   * Process payment for an order.
   *
   * @param {string} orderName
   * @param {object[]} payments - [{ mode_of_payment, amount }]
   *
   * ENDPOINT: renpos.api.order.process_payment
   */
  /**
   * Totals exactly as the invoice will be (ERPNext taxes, rounding),
   * enabled modes of payment and the cashier's register status.
   *
   * ENDPOINT: renpos.api.order.get_payment_summary
   */
  getPaymentSummary(orderName, tip = 0, loyaltyPoints = 0) {
    return call("renpos.api.order.get_payment_summary", {
      order_name: orderName,
      tip,
      loyalty_points: loyaltyPoints,
    });
  },

  joinLoyalty(orderName) {
    return call("renpos.api.loyalty.join", { order_name: orderName });
  },

  processPayment(orderName, payments, tip = 0, loyaltyPoints = 0) {
    return call("renpos.api.order.process_payment", {
      order_name: orderName,
      payments,
      tip,
      loyalty_points: loyaltyPoints,
    });
  },

  // ═══════════════════════════════════════════════
  // PRINT
  // ═══════════════════════════════════════════════

  /**
   * Get print format URL for order account.
   */
  getPrintUrl(orderName, format = "Order Account") {
    const params = new URLSearchParams({
      doctype: "Ren Order",
      name: orderName,
      format,
      no_letterhead: 0,
      _lang: frappe.boot.lang || "en",
    });
    return `/api/method/frappe.utils.print_format.download_pdf?${params}`;
  },
};

export default OrderAPI;