import { memo, useState, useCallback, useRef, useEffect } from "react";
import ItemToolbar from "./ItemToolbar";
import ItemGroupTabs from "./ItemGroupTabs";
import ItemGrid from "./ItemGrid";
import GroupAccordion from "./GroupAccordion";
import { useItemTree } from "./useItemTree";
import { DEFAULT_VIEW_MODE } from "./itemConstants";
import { Loader2 } from "lucide-react";

/**
 * ItemTree — Unified item catalog with server-side pagination.
 *
 * ORDER MODE (default):
 *   - menuName: string → server filters items to only those in the menu
 *   - Click adds to order, qty badges visible
 *
 * MENU MANAGEMENT MODE (menuMode=true):
 *   - menuName: null → loads ALL items (no menu filter)
 *   - menuItems: Set<string> → highlights items in menu with ring + check
 *   - Click toggles item in/out of menu
 *
 * Or with tab "Menu" in MenuManager:
 *   - menuName: string → loads only items in that menu
 *   - menuMode: true → still shows ring + check
 */
const ItemTree = memo(function ItemTree({
  enabled = true,
  onItemClick,
  defaultViewMode = DEFAULT_VIEW_MODE,
  menuName,        // Server-side filter: only items in this menu
  menuItems,       // Client-side highlight: Set<string> of item_codes in menu
  menuMode = false,
  renderAction,
  showOrderQty = true,
  priceList = null,
  restaurant = null, // sold-out events of other restaurants are ignored
  className = "",
  sideGroups = false, // on lg screens the groups go in a column on the left
}) {
  const {
    activeTab,
    setActiveTab,
    itemType,
    setItemType,
    search,
    setSearch,
    searchRef,
    parentTabs,
    childGroups,
    filteredItems,
    itemsByGroup,
    isAllTab,
    loading,
    loadingItems,
    hasMore,
    loadMore,
  } = useItemTree({ enabled, menuName, priceList, restaurant, menuMode });

  const [viewMode, setViewMode] = useState(defaultViewMode);
  const scrollRef = useRef(null);

  const handleViewChange = useCallback((mode) => {
    setViewMode(mode);
  }, []);

  // ── Infinite scroll ──
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onScroll = () => {
      if (loadingItems || !hasMore) return;
      const { scrollTop, scrollHeight, clientHeight } = el;
      // Load more when within 200px of bottom
      if (scrollHeight - scrollTop - clientHeight < 200) {
        loadMore();
      }
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [loadingItems, hasMore, loadMore]);

  // Shared props for grids and accordions
  const gridProps = {
    onItemClick,
    viewMode,
    menuItems,
    menuMode,
    renderAction,
    showOrderQty,
  };

  return (
    <div className={`flex flex-col min-h-0 h-full ${className}`}>
      {/* ── Sticky header ── */}
      <div className="shrink-0">
        <div className="px-3 pt-2.5 pb-2 border-b border-border">
          <ItemToolbar
            itemType={itemType}
            onItemTypeChange={setItemType}
            search={search}
            onSearchChange={setSearch}
            searchRef={searchRef}
            viewMode={viewMode}
            onViewModeChange={handleViewChange}
          />
        </div>

        <ItemGroupTabs
          tabs={parentTabs}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          className={sideGroups && parentTabs.length > 1 ? "ren-top-groups" : ""}
        />
      </div>

      <div className="flex-1 min-h-0 flex">
      {sideGroups && parentTabs.length > 1 && (
        <ItemGroupTabs
          vertical
          tabs={parentTabs}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          className="ren-side-groups w-36 xl:w-44 2xl:w-48 shrink-0 border-r border-border bg-muted/10"
        />
      )}

      {/* ── Scrollable content ── */}
      <div
        ref={scrollRef}
        className="flex-1 min-w-0 min-h-0 overflow-y-auto overscroll-contain px-3 py-3"
      >
        {loading && filteredItems.length === 0 ? (
          <div className="flex items-center justify-center h-48 text-muted-foreground">
            <Loader2 size={18} className="animate-spin mr-2" />
            {__("Loading...")}
          </div>
        ) : filteredItems.length === 0 && !loading ? (
          <div className="flex items-center justify-center h-48 text-muted-foreground">
            {menuName
              ? __("No items in this menu")
              : __("No items found")}
          </div>
        ) : isAllTab ? (
          <>
            <ItemGrid items={filteredItems} {...gridProps} />
            {/* Load more indicator */}
            {hasMore && (
              <LoadMoreIndicator loading={loadingItems} onLoadMore={loadMore} />
            )}
          </>
        ) : childGroups.length === 0 ? (
          <>
            <ItemGrid items={filteredItems} {...gridProps} />
            {hasMore && (
              <LoadMoreIndicator loading={loadingItems} onLoadMore={loadMore} />
            )}
          </>
        ) : (
          <div className="flex flex-col gap-1">
            {childGroups.map((group) => (
              <GroupAccordion
                key={group.name}
                group={group}
                items={itemsByGroup[group.name] || []}
                {...gridProps}
              />
            ))}
            {hasMore && (
              <LoadMoreIndicator loading={loadingItems} onLoadMore={loadMore} />
            )}
          </div>
        )}
      </div>
      </div>
    </div>
  );
});

// ── Load More Indicator ─────────────────────────

function LoadMoreIndicator({ loading, onLoadMore }) {
  return (
    <div className="flex justify-center py-4">
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 size={14} className="animate-spin" />
          {__("Loading more...")}
        </div>
      ) : (
        <button
          onClick={onLoadMore}
          className="text-xs text-muted-foreground hover:text-card-foreground
                     px-4 py-1.5 rounded-lg hover:bg-muted/50 transition-colors"
        >
          {__("Load more")}
        </button>
      )}
    </div>
  );
}

export default ItemTree;
export { ItemTree };