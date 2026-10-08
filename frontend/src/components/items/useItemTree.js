import { useState, useEffect, useCallback, useMemo, useRef } from "react";

const PAGE_SIZE = 50;
// Adjust to match your app structure
const METHOD_PATH = "renpos.ren_pos.doctype.ren_menu.ren_menu";

/**
 * useItemTree — Item catalog with server-side pagination and menu filtering.
 *
 * All heavy queries go through `get_items_for_tree` whitelisted method.
 * Groups come from `get_item_groups` (no Item Group permission needed).
 *
 * @param {object} opts
 * @param {boolean}  opts.enabled    - Mount/unmount control
 * @param {string}   opts.menuName   - If set, only load items in this Ren Menu
 * @param {string}   opts.priceList  - Price list for pricing (optional)
 * @param {boolean}  opts.menuMode   - Menu Manager: the list stays put while
 *                                     items are checked / unchecked (only the
 *                                     check marks change), so nothing jumps
 */
export function useItemTree({ enabled = true, menuName = null, priceList = null, restaurant = null, menuMode = false } = {}) {
  // ── Groups ──
  const [allGroups, setAllGroups] = useState([]);
  const [loadingGroups, setLoadingGroups] = useState(true);

  // ── Items (paginated) ──
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const pageRef = useRef(0);

  // ── Filters ──
  const [activeTab, setActiveTab] = useState("All Item Groups");
  const [itemType, setItemType] = useState(null);
  const [search, setSearch] = useState("");
  const searchRef = useRef(null);

  // Prevent stale responses
  const requestId = useRef(0);

  // ── Load groups (one-time) ─────────────────────

  const loadGroups = useCallback(async () => {
    setLoadingGroups(true);
    try {
      // restaurant endpoint: waiters have no read permission on Item Group.
      // With a menu, only the groups that have items on it (no empty tabs).
      const r = await frappe.call({
        method: `${METHOD_PATH}.get_item_groups`,
        args: menuName && menuName !== "__not_assigned_menu__" ? { menu_name: menuName } : {},
      });
      setAllGroups(r.message || []);
    } catch (err) {
      console.error("[ItemTree] loadGroups:", err);
    } finally {
      setLoadingGroups(false);
    }
  }, [menuName]);

  // ── Resolve tab to leaf group names ────────────

  const getLeafGroupNames = useCallback(
    (tabName) => {
      if (!tabName || tabName === "All Item Groups") return null;
      const group = allGroups.find((g) => g.name === tabName);
      if (!group) return [tabName];

      if (group.is_group) {
        const leaves = allGroups
          .filter((g) => g.lft >= group.lft && g.rgt <= group.rgt && !g.is_group)
          .map((g) => g.name);
        return leaves.length > 0 ? leaves : [tabName];
      }
      return [tabName];
    },
    [allGroups]
  );

  // ── Load items via whitelisted method ──────────

  const loadItems = useCallback(
    async (page = 0, append = false) => {
      if (allGroups.length === 0) return;

      const rid = ++requestId.current;
      setLoadingItems(true);

      try {
        const args = {
          limit_start: page * PAGE_SIZE,
          limit_page_length: PAGE_SIZE,
        };

        // Menu filter (no menu set up: every item can be sold)
        if (menuName && menuName !== "__not_assigned_menu__") {
          args.menu_name = menuName;
        }

        // Group filter
        const leafGroups = getLeafGroupNames(activeTab);
        if (leafGroups) {
          args.item_groups = JSON.stringify(leafGroups);
        }

        // Ren Menu Tag filter (Vegetarian, Gluten-free...)
        if (itemType) {
          args.tag = itemType;
        }

        // Search
        if (search.trim()) {
          args.search = search.trim();
        }

        // Price list
        if (priceList) {
          args.price_list = priceList;
        }

        const result = await frappe.call({
          method: `${METHOD_PATH}.get_items_for_tree`,
          args,
        });

        // Stale check
        if (rid !== requestId.current) return;

        const data = result.message || [];

        if (append) {
          setItems((prev) => [...prev, ...data]);
        } else {
          setItems(data);
        }
        setHasMore(data.length >= PAGE_SIZE);
        pageRef.current = page;
      } catch (err) {
        console.error("[ItemTree] loadItems:", err);
      } finally {
        if (rid === requestId.current) {
          setLoadingItems(false);
        }
      }
    },
    [allGroups, activeTab, itemType, search, menuName, priceList, getLeafGroupNames]
  );

  // ── Load More ──────────────────────────────────

  const loadMore = useCallback(() => {
    if (loadingItems || !hasMore) return;
    loadItems(pageRef.current + 1, true);
  }, [loadingItems, hasMore, loadItems]);

  // ── Effects ────────────────────────────────────

  useEffect(() => {
    if (enabled) loadGroups();
  }, [enabled, loadGroups]);

  // Reset and reload when filters change. Keyed on the group names: groups
  // reloaded after a menu edit are a new array with the same content, and
  // treating that as a filter change used to drop the pages already loaded.
  const groupsKey = useMemo(() => allGroups.map((g) => g.name).join("|"), [allGroups]);
  useEffect(() => {
    if (allGroups.length === 0) return;
    pageRef.current = 0;
    setHasMore(true);
    loadItems(0, false);
  }, [activeTab, itemType, search, menuName, groupsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reload what is already on screen (every page loaded so far) in place
  const refreshLoaded = useCallback(async () => {
    if (allGroups.length === 0) return;
    const pages = pageRef.current + 1;
    const rid = ++requestId.current;
    try {
      const args = { limit_start: 0, limit_page_length: pages * PAGE_SIZE };
      if (menuName && menuName !== "__not_assigned_menu__") args.menu_name = menuName;
      const leafGroups = getLeafGroupNames(activeTab);
      if (leafGroups) args.item_groups = JSON.stringify(leafGroups);
      if (itemType) args.tag = itemType;
      if (search.trim()) args.search = search.trim();
      if (priceList) args.price_list = priceList;
      const r = await frappe.call({ method: `${METHOD_PATH}.get_items_for_tree`, args });
      if (rid !== requestId.current) return;
      const data = r.message || [];
      setItems(data);
      setHasMore(data.length >= pages * PAGE_SIZE);
    } catch (err) {
      console.error("[ItemTree] refreshLoaded:", err);
    }
  }, [allGroups, activeTab, itemType, search, menuName, priceList, getLeafGroupNames]);
  const refreshRef = useRef(refreshLoaded);
  useEffect(() => { refreshRef.current = refreshLoaded; }, [refreshLoaded]);

  // Sold out / back in stock on any screen; menu edited
  useEffect(() => {
    if (!enabled) return undefined;
    const onAvailability = (d) => {
      if (!d?.item_code || (restaurant && d.restaurant && d.restaurant !== restaurant)) return;
      setItems((prev) => prev.map((i) => (i.item_code === d.item_code ? { ...i, is_available: !d.sold_out } : i)));
    };
    const onMenu = (d) => {
      // an item edited in the Menu Manager's editor: its card changes everywhere
      if (d?.item) { loadGroups(); refreshRef.current(); return; }
      if (d?.menu && d.menu !== menuName) return;
      loadGroups();
      // Menu Manager: an unchecked item stays on screen (unchecked) so it can be
      // put back; the order screen refreshes its catalog in place
      if (!menuMode) refreshRef.current();
    };
    frappe.realtime.on("menu_availability", onAvailability);
    frappe.realtime.on("menu_changed", onMenu);
    return () => {
      frappe.realtime.off("menu_availability", onAvailability);
      frappe.realtime.off("menu_changed", onMenu);
    };
  }, [enabled, menuName, menuMode, loadGroups, restaurant]);

  // ── Derived data ───────────────────────────────

  const parentTabs = useMemo(() => {
    return allGroups.filter((g) => g.is_group);
  }, [allGroups]);

  const childGroups = useMemo(() => {
    if (activeTab === "All Item Groups") return [];
    return allGroups.filter((g) => g.parent_item_group === activeTab);
  }, [allGroups, activeTab]);

  // Client-side grouping of already-fetched items for accordion view
  const itemsByGroup = useMemo(() => {
    const map = {};
    for (const group of childGroups) {
      const parent = allGroups.find((g) => g.name === group.name);
      let groupNames;

      if (parent && parent.is_group) {
        groupNames = allGroups
          .filter((g) => g.lft >= parent.lft && g.rgt <= parent.rgt && !g.is_group)
          .map((g) => g.name);
      } else {
        groupNames = [group.name];
      }

      map[group.name] = items.filter((i) => groupNames.includes(i.item_group));
    }
    return map;
  }, [items, childGroups, allGroups]);

  const isAllTab = activeTab === "All Item Groups";
  const loading = loadingGroups || loadingItems;

  return {
    // State
    activeTab, setActiveTab,
    itemType, setItemType,
    search, setSearch,
    searchRef,

    // Data
    parentTabs,
    childGroups,
    filteredItems: items,
    itemsByGroup,
    isAllTab,
    loading,
    loadingItems,

    // Pagination
    hasMore,
    loadMore,

    // Actions
    reload: loadGroups,
  };
}