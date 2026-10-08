import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import {
  fetchMenuList,
  fetchMenuCount,
  createMenu,
  deleteMenu as deleteMenuSvc,
  setDefault as setDefaultSvc,
  toggleEnabled as toggleEnabledSvc,
  addMenuItem,
  removeMenuItem,
  fetchMenuItemCodes,
} from "./menuService";
import { getUrlParam, setUrlParams } from "@/utils/urlState";

const PAGE_SIZE = 20;

/**
 * useMenuManager — Manages menu list and immediate item toggling.
 *
 * No dirty/save state — clicks persist immediately.
 * The `menuItems` Set is kept in sync for ItemCard ring/check display.
 *
 * @param {string} company
 */
export function useMenuManager(company) {
  // ── Menu list ──
  const [menus, setMenus] = useState([]);
  const [menuCount, setMenuCount] = useState(0);
  const [listPage, setListPage] = useState(0);
  const [listLoading, setListLoading] = useState(false);
  const [listSearch, setListSearch] = useState("");

  // ── Active menu ──
  const [activeMenuName, setActiveMenuName] = useState(null);
  const [menuItemCodes, setMenuItemCodes] = useState(new Set());
  const [toggling, setToggling] = useState(false); // prevents double-click

  const didAutoSelect = useRef(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  // ── Load menu list ─────────────────────────────

  const loadMenuList = useCallback(async (page = 0, search = "") => {
    if (!company) return [];
    setListLoading(true);
    try {
      const [list, count] = await Promise.all([
        fetchMenuList(company, { limit: PAGE_SIZE, start: page * PAGE_SIZE, search }),
        fetchMenuCount(company, search),
      ]);
      if (!alive.current) return [];
      setMenus(list || []);
      setMenuCount(count || 0);
      setListPage(page);
      return list || [];
    } catch (err) {
      console.error("[MenuManager] loadMenuList:", err);
      return [];
    } finally {
      if (alive.current) setListLoading(false);
    }
  }, [company]);

  // ── Select menu + load its item codes ──────────

  const selectMenu = useCallback(async (menuName) => {
    if (!menuName) return;
    setActiveMenuName(menuName);
    setUrlParams({ menu: menuName });
    try {
      const codes = await fetchMenuItemCodes(menuName);
      if (alive.current) setMenuItemCodes(new Set(codes));
    } catch (err) {
      console.error("[MenuManager] selectMenu:", err);
      if (alive.current) setMenuItemCodes(new Set());
    }
  }, []);

  // ── Initial load + auto-select ─────────────────

  useEffect(() => {
    if (!company) return;
    didAutoSelect.current = false;

    loadMenuList(0, "").then((list) => {
      if (!alive.current || !list?.length || didAutoSelect.current) return;
      const fromUrl = getUrlParam("menu");
      const def = list.find((m) => m.name === fromUrl) || list.find((m) => m.is_active)
        || list.find((m) => m.is_default) || list[0];
      didAutoSelect.current = true;
      selectMenu(def.name);
    });
  }, [company]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Toggle item (immediate server save) ────────

  const toggleItem = useCallback(async (item) => {
    if (!activeMenuName || toggling) return;

    const code = typeof item === "string" ? item : item.item_code;
    const isInMenu = menuItemCodes.has(code);

    // Optimistic UI update
    setMenuItemCodes((prev) => {
      const next = new Set(prev);
      isInMenu ? next.delete(code) : next.add(code);
      return next;
    });

    setToggling(true);
    try {
      if (isInMenu) {
        await removeMenuItem(activeMenuName, code);
      } else {
        await addMenuItem(activeMenuName, code);
      }
      // show what the server saved, not what we assumed
      const codes = await fetchMenuItemCodes(activeMenuName);
      if (alive.current) setMenuItemCodes(new Set(codes));
      // Refresh menu list to update total_items count
      loadMenuList(listPage, listSearch);
    } catch (err) {
      console.error("[MenuManager] toggleItem:", err);
      // Revert on error
      setMenuItemCodes((prev) => {
        const next = new Set(prev);
        isInMenu ? next.add(code) : next.delete(code);
        return next;
      });
      frappe.show_alert({ message: __("Failed to update menu"), indicator: "red" });
    } finally {
      if (alive.current) setToggling(false);
    }
  }, [activeMenuName, menuItemCodes, toggling, loadMenuList, listPage, listSearch]);

  // ── Create menu ────────────────────────────────

  const addMenu = useCallback(async (menuName) => {
    if (!company || !menuName) return;
    try {
      const doc = await createMenu(menuName, company, {
        is_default: menus.length === 0 ? 1 : 0,
      });
      if (!alive.current) return;
      await loadMenuList(0, listSearch);
      selectMenu(doc.name);
      frappe.show_alert({ message: __("Menu created"), indicator: "green" });
      return doc;
    } catch (err) {
      console.error("[MenuManager] addMenu:", err);
      frappe.show_alert({ message: __("Failed to create menu"), indicator: "red" });
    }
  }, [company, menus.length, loadMenuList, listSearch, selectMenu]);

  // ── Delete menu ────────────────────────────────

  const removeMenu = useCallback(async (menuName) => {
    try {
      await deleteMenuSvc(menuName);
      if (!alive.current) return;
      const wasActive = activeMenuName === menuName;
      if (wasActive) {
        setActiveMenuName(null);
        setMenuItemCodes(new Set());
      }
      const list = await loadMenuList(listPage, listSearch);
      if (wasActive && list?.length) {
        const def = list.find((m) => m.is_default) || list[0];
        selectMenu(def.name);
      }
      frappe.show_alert({ message: __("Menu deleted"), indicator: "green" });
    } catch (err) {
      console.error("[MenuManager] removeMenu:", err);
      frappe.show_alert({ message: __("Failed to delete"), indicator: "red" });
    }
  }, [activeMenuName, loadMenuList, listPage, listSearch, selectMenu]);

  // ── Set default (optimistic) ───────────────────

  const setAsDefault = useCallback(async (menuName) => {
    setMenus((prev) =>
      prev.map((m) => ({ ...m, is_default: m.name === menuName ? 1 : 0, is_active: m.name === menuName ? 1 : 0 }))
    );
    try {
      await setDefaultSvc(menuName);
      if (alive.current) loadMenuList(listPage, listSearch);
    } catch (err) {
      console.error("[MenuManager] setDefault:", err);
      loadMenuList(listPage, listSearch);
    }
  }, [loadMenuList, listPage, listSearch]);

  // ── Toggle enabled (optimistic) ────────────────

  const toggleMenuEnabled = useCallback(async (menuName) => {
    const menu = menus.find((m) => m.name === menuName);
    if (!menu) return;
    setMenus((prev) =>
      prev.map((m) => m.name === menuName ? { ...m, enabled: m.enabled ? 0 : 1 } : m)
    );
    try {
      await toggleEnabledSvc(menuName, menu.enabled);
    } catch (err) {
      console.error("[MenuManager] toggleEnabled:", err);
      loadMenuList(listPage, listSearch);
    }
  }, [menus, loadMenuList, listPage, listSearch]);

  // ── Pagination ─────────────────────────────────

  const totalPages = Math.ceil(menuCount / PAGE_SIZE);

  const nextPage = useCallback(() => {
    if (listPage < totalPages - 1) loadMenuList(listPage + 1, listSearch);
  }, [listPage, totalPages, listSearch, loadMenuList]);

  const prevPage = useCallback(() => {
    if (listPage > 0) loadMenuList(listPage - 1, listSearch);
  }, [listPage, listSearch, loadMenuList]);

  const searchMenus = useCallback((term) => {
    setListSearch(term);
    loadMenuList(0, term);
  }, [loadMenuList]);

  // Stable ref for ItemTree
  const menuItems = useMemo(() => menuItemCodes, [menuItemCodes]);

  return {
    // List
    menus, menuCount, listPage, totalPages,
    listLoading, listSearch,
    hasNextPage: listPage < totalPages - 1,
    hasPrevPage: listPage > 0,
    nextPage, prevPage, searchMenus,
    refreshList: () => loadMenuList(listPage, listSearch),

    // Active menu
    activeMenuName,
    menuItems,     // Set<string> for ring/check in ItemCard
    toggling,

    // Actions
    selectMenu, toggleItem,
    addMenu, removeMenu,
    setAsDefault, toggleMenuEnabled,
  };
}

export default useMenuManager;