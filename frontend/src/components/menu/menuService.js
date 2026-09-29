/**
 * menuService.js — Menu CRUD.
 *
 * Parent doctype (Restaurant Menu): frappe.client.*
 * Child table queries: whitelisted methods in restaurant_menu.py
 */

const DOCTYPE = "Restaurant Menu";
// Adjust this path to match your app structure
const METHOD_PATH = "restaurant_management.restaurant_management.doctype.restaurant_menu.restaurant_menu";

function call(method, args) {
  return new Promise((resolve, reject) => {
    frappe.call({
      method,
      args,
      async: true,
      callback: (r) => resolve(r?.message ?? r),
      error: (err) => reject(err),
    });
  });
}

// ─── Menu List (parent doctype — get_list works fine) ────

export function fetchMenuList(company, opts = {}) {
  const { limit = 20, start = 0, search = "" } = opts;
  const filters = { company };
  if (search) filters.menu_name = ["like", `%${search}%`];

  return call("frappe.client.get_list", {
    doctype: DOCTYPE,
    filters,
    fields: ["name", "menu_name", "company", "enabled", "is_default", "total_items"],
    order_by: "is_default desc, menu_name asc",
    limit_page_length: limit,
    limit_start: start,
  });
}

export function fetchMenuCount(company, search = "") {
  const filters = { company };
  if (search) filters.menu_name = ["like", `%${search}%`];
  return call("frappe.client.get_count", { doctype: DOCTYPE, filters });
}

// ─── Menu Item Codes (whitelisted — uses frappe.db.get_all) ──

export function fetchMenuItemCodes(menuName) {
  return call(`${METHOD_PATH}.get_menu_item_codes`, {
    menu_name: menuName,
  });
}

// ─── Create / Delete ────────────────────────────

export function createMenu(menuName, company, opts = {}) {
  return call("frappe.client.save", {
    doc: {
      doctype: DOCTYPE,
      menu_name: menuName,
      company,
      enabled: 1,
      is_default: opts.is_default || 0,
      items: [],
    },
  });
}

export function deleteMenu(menuName) {
  return call("frappe.client.delete", { doctype: DOCTYPE, name: menuName });
}

// ─── Set Default / Toggle Enabled ───────────────

export async function setDefault(menuName) {
  const doc = await call("frappe.client.get", { doctype: DOCTYPE, name: menuName });
  doc.is_default = 1;
  return call("frappe.client.save", { doc });
}

export async function toggleEnabled(menuName, currentEnabled) {
  const doc = await call("frappe.client.get", { doctype: DOCTYPE, name: menuName });
  doc.enabled = currentEnabled ? 0 : 1;
  return call("frappe.client.save", { doc });
}

// ─── Single Item Add/Remove (immediate save via parent doc) ──

export async function addMenuItem(menuName, itemCode) {
  const doc = await call("frappe.client.get", { doctype: DOCTYPE, name: menuName });
  const exists = (doc.items || []).some((r) => r.item === itemCode);
  if (exists) return doc;

  doc.items = doc.items || [];
  doc.items.push({
    doctype: "Restaurant Menu Item",
    parent: menuName,
    parenttype: DOCTYPE,
    parentfield: "items",
    item: itemCode,
    enabled: 1,
    idx: doc.items.length + 1,
  });

  return call("frappe.client.save", { doc });
}

export async function removeMenuItem(menuName, itemCode) {
  const doc = await call("frappe.client.get", { doctype: DOCTYPE, name: menuName });
  doc.items = (doc.items || []).filter((r) => r.item !== itemCode);
  doc.items.forEach((r, i) => { r.idx = i + 1; });
  return call("frappe.client.save", { doc });
}