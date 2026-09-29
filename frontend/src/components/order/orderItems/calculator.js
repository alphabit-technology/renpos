/**
 * OrderCalculator — Pure client-side calculation engine.
 *
 * Replaces the server-side calculations that OrderItem.tax_calculate()
 * and TableOrder.aggregate() were doing via frappe.call.
 *
 * All functions are pure (no side effects, no API calls).
 * Pre-loaded POS data is passed in as arguments.
 */

// ─── Item-level calculations ─────────────────────

/**
 * Calculate rate after discount.
 * Mirrors legacy: rate = price_list_rate * (1 - discount / 100)
 */
export function applyDiscount(priceListRate, discountPercentage) {
  const rate = flt(priceListRate) * (1 - flt(discountPercentage) / 100);
  return Math.max(0, rate);
}

/**
 * Calculate discount percentage from rate.
 * Mirrors legacy: discount = ((base - rate) / base) * 100
 */
export function discountFromRate(priceListRate, rate) {
  const base = flt(priceListRate);
  if (base === 0) return 0;
  const discount = ((base - flt(rate)) / base) * 100;
  return Math.max(0, discount);
}

/**
 * Calculate tax for a single item.
 * Mirrors legacy OrderItem.tax_calculate()
 *
 * @param {number} baseAmount - qty * rate
 * @param {object} itemTaxRate - parsed JSON: { "VAT - 15%": 15, ... }
 * @param {boolean} taxInclusive - from pos_profile.posa_tax_inclusive
 * @returns {{ taxAmount: number, netAmount: number }}
 */
export function calculateItemTax(baseAmount, itemTaxRate, taxInclusive = false) {
  const rates = typeof itemTaxRate === "string"
    ? safeParseJSON(itemTaxRate)
    : (itemTaxRate || {});

  // Same formula as the server (api/order.py _row_amounts)
  const totalRate = Object.values(rates).reduce((acc, rate) => acc + (parseFloat(rate) || 0), 0);
  const taxAmount = taxInclusive
    ? baseAmount - baseAmount / (1 + totalRate / 100)
    : baseAmount * totalRate / 100;

  return {
    taxAmount: flt(taxAmount),
    netAmount: taxInclusive ? flt(baseAmount) : flt(baseAmount + taxAmount),
  };
}

/**
 * Full item calculation — the main function.
 * Takes an item and returns all computed fields.
 *
 * @param {object} item - order item data
 * @param {object} opts - { taxInclusive }
 * @returns {object} item with computed fields
 */
export function calculateItem(item, opts = {}) {
  const qty = flt(item.qty);
  const priceListRate = flt(item.price_list_rate);
  const discountPercentage = flt(item.discount_percentage);

  // Rate after discount
  const rate = applyDiscount(priceListRate, discountPercentage);

  // Base amount
  const baseAmount = qty * rate;

  // Tax
  const { taxAmount, netAmount } = calculateItemTax(
    baseAmount,
    item.item_tax_rate,
    opts.taxInclusive
  );

  return {
    ...item,
    rate: flt(rate),
    qty,
    discount_percentage: flt(discountPercentage),
    price_list_rate: priceListRate,
    base_amount: flt(baseAmount),
    tax_amount: flt(taxAmount),
    amount: flt(netAmount),
  };
}

// ─── Order-level aggregation ─────────────────────

/**
 * Aggregate all items in an order.
 * Mirrors legacy TableOrder.aggregate()
 *
 * @param {object[]} items - array of calculated items
 * @param {object} orderData - { charge_amount, is_delivery, delivery_branch }
 * @returns {{ netTotal, totalTax, grandTotal, itemCount }}
 */
export function aggregateOrder(items, orderData = {}) {
  let netTotal = 0;
  let totalTax = 0;

  for (const item of items) {
    totalTax += flt(item.tax_amount || 0);
    netTotal += flt(item.amount || 0);
  }

  // Delivery charges
  if (orderData.is_delivery === 1 && orderData.delivery_branch !== 1) {
    const charge = flt(orderData.charge_amount || 0);
    totalTax += charge;
    netTotal += charge;
  }

  return {
    netTotal: flt(netTotal),
    totalTax: flt(totalTax),
    grandTotal: flt(netTotal),
    itemCount: items.length,
  };
}

// ─── Numpad input helpers ────────────────────────

/**
 * Recalculate item based on which field the user edited via numpad.
 * Mirrors legacy OrderManage.update_detail()
 *
 * @param {object} item - current item data
 * @param {string} field - "qty" | "discount" | "rate"
 * @param {number} value - new value from numpad
 * @param {object} opts - { taxInclusive }
 * @returns {object} updated item (recalculated)
 */
export function updateItemField(item, field, value, opts = {}) {
  const updated = { ...item };
  const baseRate = flt(item.price_list_rate);

  switch (field) {
    case "qty":
      updated.qty = flt(value);
      break;

    case "discount":
      updated.discount_percentage = flt(value);
      updated.rate = applyDiscount(baseRate, value);
      break;

    case "rate":
      updated.rate = flt(value);
      updated.discount_percentage = discountFromRate(baseRate, value);
      break;
  }

  updated.status = "Pending";
  return calculateItem(updated, opts);
}

// ─── Pricing Rules (simplified) ──────────────────

/**
 * Apply applicable pricing rules to an item.
 * Simple version — handles percentage and amount discounts.
 *
 * @param {object} item - { item_code, item_group, qty, rate, ... }
 * @param {object[]} rules - pre-loaded pricing rules
 * @returns {object} item with pricing rule applied
 */
export function applyPricingRules(item, rules = []) {
  if (!rules.length) return item;

  const applicable = rules.filter(rule => {
    // Match by item or item group
    const matchesItem = !rule.item_code || rule.item_code === item.item_code;
    const matchesGroup = !rule.item_group || rule.item_group === item.item_group;

    // Min qty check
    const meetsMinQty = !rule.min_qty || flt(item.qty) >= flt(rule.min_qty);

    // Max qty check
    const meetsMaxQty = !rule.max_qty || flt(item.qty) <= flt(rule.max_qty);

    return (matchesItem || matchesGroup) && meetsMinQty && meetsMaxQty;
  });

  if (!applicable.length) return item;

  // Apply highest priority rule (lowest priority number)
  const rule = applicable.sort((a, b) => (a.priority || 99) - (b.priority || 99))[0];
  const updated = { ...item };

  if (rule.discount_percentage) {
    updated.discount_percentage = flt(rule.discount_percentage);
    updated.rate = applyDiscount(flt(item.price_list_rate), rule.discount_percentage);
    updated.pricing_rule = rule.name;
  } else if (rule.discount_amount) {
    updated.rate = Math.max(0, flt(item.price_list_rate) - flt(rule.discount_amount));
    updated.discount_percentage = discountFromRate(item.price_list_rate, updated.rate);
    updated.pricing_rule = rule.name;
  } else if (rule.rate) {
    updated.rate = flt(rule.rate);
    updated.price_list_rate = flt(rule.rate);
    updated.pricing_rule = rule.name;
  }

  return updated;
}

// ─── Utilities ───────────────────────────────────

function flt(value, precision = 2) {
  const num = parseFloat(value) || 0;
  return Math.round(num * Math.pow(10, precision)) / Math.pow(10, precision);
}

function safeParseJSON(str) {
  if (!str || typeof str !== "string") return {};
  try {
    return JSON.parse(str);
  } catch {
    return {};
  }
}

function formatCurrency(value) {
  return typeof RM !== "undefined" && RM.format_currency
    ? RM.format_currency(flt(value))
    : `$ ${flt(value).toFixed(2)}`;
}

export { flt, safeParseJSON, formatCurrency };