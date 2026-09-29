import { useState, useEffect, useCallback, useMemo, useRef } from "react";

const PAGE_SIZE = 50;
// Adjust to match your app structure
const METHOD_PATH = "restaurant_management.restaurant_management.doctype.restaurant_menu.restaurant_menu";

/**
 * useItemTree — Item catalog with server-side pagination and menu filtering.
 *
 * All heavy queries go through `get_items_for_tree` whitelisted method.
 * Groups come from `get_item_groups` (no Item Group permission needed).
 *
 * @param {object} opts
 * @param {boolean}  opts.enabled    - Mount/unmount control
 * @param {string}   opts.menuName   - If set, only load items in this Restaurant Menu
 * @param {string}   opts.priceList  - Price list for pricing (optional)
 */
export function useItemTree({ enabled = true, menuName = null, priceList = null } = {}) {
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
      // restaurant endpoint: waiters have no read permission on Item Group
      const r = await frappe.call({
        method: `${METHOD_PATH}.get_item_groups`,
      });
      setAllGroups(r.message || []);
    } catch (err) {
      console.error("[ItemTree] loadGroups:", err);
    } finally {
      setLoadingGroups(false);
    }
  }, []);

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

        // Menu filter
        if (menuName) {
          args.menu_name = menuName;
        }

        // Group filter
        const leafGroups = getLeafGroupNames(activeTab);
        if (leafGroups) {
          args.item_groups = JSON.stringify(leafGroups);
        }

        // Item type
        if (itemType) {
          args.item_type = itemType;
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

  // Reset and reload when filters change
  useEffect(() => {
    if (allGroups.length === 0) return;
    pageRef.current = 0;
    setHasMore(true);
    loadItems(0, false);
  }, [activeTab, itemType, search, menuName, allGroups]); // eslint-disable-line react-hooks/exhaustive-deps

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