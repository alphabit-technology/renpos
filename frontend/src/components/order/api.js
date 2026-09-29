/**
 * OrderAPI — All server calls for the Order Management system.
 *
 * Single source of truth for API endpoints.
 * Each method returns a Promise.
 *
 * Migration map from legacy:
 *   frappeHelper.api.call({ model: "Restaurant Object", method: "add_order" })
 *     → OrderAPI.addOrder(tableName)
 *
 *   frappeHelper.api.call({ model: "Table Order", method: "push_item" })
 *     → OrderAPI.pushItem(orderName, itemData)
 */

/**
 * Identifies this browser tab. Sent with every order call and echoed back
 * by the server in the "order_update" realtime event, so a tab can ignore
 * its own changes while other tabs (even with the same user) refresh.
 */
export const CLIENT_ID =
  (typeof crypto !== "undefined" && crypto.randomUUID)
    ? crypto.randomUUID()
    : `tab_${Date.now()}_${Math.random().toString(36).slice(2)}`;

function call(method, args = {}) {
  return new Promise((resolve, reject) => {
    frappe.call({
      method,
      args: { ...args, client_id: CLIENT_ID },
      async: true,
      callback: (r) => resolve(r.message),
      error: (r) => reject(r),
    });
  });
}

function docMethod(doctype, name, method, args = {}) {
  return call(
    "frappe.client.run_doc_method",
    { dt: doctype, dn: name, method, args }
  ).then(r => r || {});
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
   * ENDPOINT: restaurant_management.api.pos.get_pos_data
   */
  getPosData(posProfile) {
    return call("restaurant_management.api.pos.get_pos_data", {
      pos_profile: posProfile,
    });
  },

  // ═══════════════════════════════════════════════
  // ORDERS
  // ═══════════════════════════════════════════════

  /**
   * Get all orders for a table.
   * Legacy: Restaurant Object.orders_list
   *
   * Returns: { orders: [...], order: currentOrderName }
   *
   * ENDPOINT: restaurant_management.api.order.get_orders
   */
  getOrders(tableName, customer = null) {
    return call("restaurant_management.api.order.get_orders", {
      table_name: tableName,
      customer,
    });
  },

  /**
   * Create a new order for a table.
   * Legacy: Restaurant Object.add_order
   *
   * Returns: { order: {...}, items: [] }
   *
   * ENDPOINT: restaurant_management.api.order.add_order
   */
  addOrder(tableName) {
    return call("restaurant_management.api.order.add_order", {
      table_name: tableName,
    });
  },

  /**
   * Delete an order.
   * Legacy: Table Order._delete
   *
   * ENDPOINT: restaurant_management.api.order.delete_order
   */
  deleteOrder(orderName) {
    return call("restaurant_management.api.order.delete_order", {
      order_name: orderName,
    });
  },

  /**
   * Get items for an order.
   * Legacy: Table Order.get_items
   *
   * Returns: { order: {...}, items: [...] }
   *
   * ENDPOINT: restaurant_management.api.order.get_items
   */
  getItems(orderName) {
    return call("restaurant_management.api.order.get_items", {
      order_name: orderName,
    });
  },

  // ═══════════════════════════════════════════════
  // ITEMS (add/update/delete)
  // ═══════════════════════════════════════════════

  /**
   * Push (add or update) an item in an order.
   * Legacy: Table Order.push_item
   *
   * The item is calculated CLIENT-SIDE before sending.
   * Server validates and persists.
   *
   * ENDPOINT: restaurant_management.api.order.push_item
   */
  pushItem(orderName, item) {
    return call("restaurant_management.api.order.push_item", {
      order_name: orderName,
      item,
    });
  },

  /**
   * Delete an item from an order.
   * Legacy: Table Order.delete_item
   *
   * ENDPOINT: restaurant_management.api.order.delete_item
   */
  deleteItem(orderName, identifier) {
    return call("restaurant_management.api.order.delete_item", {
      order_name: orderName,
      identifier,
    });
  },

  // ═══════════════════════════════════════════════
  // ORDER ACTIONS
  // ═══════════════════════════════════════════════

  /**
   * Send order to kitchen (mark items as "Sent").
   * Legacy: Table Order.send
   *
   * Returns: { order: {...}, items: [...] }
   *
   * ENDPOINT: restaurant_management.api.order.send_order
   */
  sendOrder(orderName) {
    return call("restaurant_management.api.order.send_order", {
      order_name: orderName,
    });
  },

  /**
   * Transfer order to another table.
   * Legacy: managed via RM.transfer_order state
   *
   * ENDPOINT: restaurant_management.api.order.transfer_order
   */
  transferOrder(orderName, targetTable) {
    return call("restaurant_management.api.order.transfer_order", {
      order_name: orderName,
      target_table: targetTable,
    });
  },

  /**
   * Divide (split) an order.
   * Legacy: Table Order.divide
   *
   * @param {string} orderName
   * @param {object} items - { identifier: { name, qty, identifier } }
   *
   * ENDPOINT: restaurant_management.api.order.divide_order
   */
  /** Tables of the restaurant for the transfer dialog. */
  getTransferTargets(orderName) {
    return call("restaurant_management.api.order.get_transfer_targets", {
      order_name: orderName,
    });
  },

  divideOrder(orderName, items) {
    return call("restaurant_management.api.order.divide_order", {
      order_name: orderName,
      items,
    });
  },

  // ═══════════════════════════════════════════════
  // CUSTOMER
  // ═══════════════════════════════════════════════

  /**
   * Set customer on an order.
   * Legacy: DeskForm "Restaurant Order Customer"
   *
   * ENDPOINT: restaurant_management.api.order.set_customer
   */
  setCustomer(orderName, customer) {
    return call("restaurant_management.api.order.set_customer", {
      order_name: orderName,
      customer,
    });
  },

  /**
   * Set dinners (party size) on an order.
   * Legacy: DeskForm "restaurant-order-dinners"
   *
   * ENDPOINT: restaurant_management.api.order.set_dinners
   */
  setDinners(orderName, dinners) {
    return call("restaurant_management.api.order.set_dinners", {
      order_name: orderName,
      dinners,
    });
  },

  // ═══════════════════════════════════════════════
  // PAYMENT
  // ═══════════════════════════════════════════════

  /**
   * Process payment for an order.
   * Legacy: PayForm
   *
   * @param {string} orderName
   * @param {object[]} payments - [{ mode_of_payment, amount }]
   *
   * ENDPOINT: restaurant_management.api.order.process_payment
   */
  /**
   * Totals exactly as the invoice will be (ERPNext taxes, rounding),
   * enabled modes of payment and the cashier's register status.
   *
   * ENDPOINT: restaurant_management.api.order.get_payment_summary
   */
  getPaymentSummary(orderName) {
    return call("restaurant_management.api.order.get_payment_summary", {
      order_name: orderName,
    });
  },

  processPayment(orderName, payments) {
    return call("restaurant_management.api.order.process_payment", {
      order_name: orderName,
      payments,
    });
  },

  // ═══════════════════════════════════════════════
  // PRINT
  // ═══════════════════════════════════════════════

  /**
   * Get print format URL for order account.
   * Legacy: DeskModal with is_pdf
   */
  getPrintUrl(orderName, format = "Order Account") {
    const params = new URLSearchParams({
      doctype: "Table Order",
      name: orderName,
      format,
      no_letterhead: 0,
      _lang: frappe.boot.lang || "en",
    });
    return `/api/method/frappe.utils.print_format.download_pdf?${params}`;
  },
};

export default OrderAPI;