/**
 * menuService.js — Menu CRUD.
 *
 * Parent doctype (Ren Menu): frappe.client.*
 * Child table queries: whitelisted methods in restaurant_menu.py
 */

import { callWithApproval } from "@/utils/approval";

const DOCTYPE = "Ren Menu";
// Adjust this path to match your app structure
const METHOD_PATH = "renpos.ren_pos.doctype.ren_menu.ren_menu";

// edit_menu is a role action: a manager PIN is asked when needed
function call(method, args) {
  return callWithApproval(method, args);
}

// ─── Menu List (parent doctype — get_list works fine) ────

const MENUS = "renpos.api.menus";

// is_active: the restaurant's menu (the star); rooms: rooms with this menu of their own
export function fetchMenuList(company, opts = {}) {
  const { limit = 20, start = 0, search = "" } = opts;
  return call(`${MENUS}.list_menus`, { company, search, limit, start }).then((r) => r?.menus || []);
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

// The star: this restaurant sells from this menu (also the company default)
export function setDefault(menuName) {
  return call(`${MENUS}.set_active_menu`, { menu: menuName });
}

export async function toggleEnabled(menuName, currentEnabled) {
  const doc = await call("frappe.client.get", { doctype: DOCTYPE, name: menuName });
  doc.enabled = currentEnabled ? 0 : 1;
  return call("frappe.client.save", { doc });
}

// ─── Single Item Add/Remove (immediate save via parent doc) ──

// adds the item, or turns a disabled row back on
export function addMenuItem(menuName, itemCode) {
  return call(`${MENUS}.set_menu_item`, { menu: menuName, item_code: itemCode, enabled: 1 });
}

export function removeMenuItem(menuName, itemCode) {
  return call(`${MENUS}.set_menu_item`, { menu: menuName, item_code: itemCode, enabled: 0 });
}