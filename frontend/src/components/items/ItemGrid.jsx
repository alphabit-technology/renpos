import { memo } from "react";
import ItemCard from "./ItemCard";
import { VIEW_MODES, DEFAULT_VIEW_MODE } from "./itemConstants";

/**
 * ItemGrid — Responsive grid for item cards.
 */

const ItemGrid = memo(function ItemGrid({
  items,
  onItemClick,
  viewMode = DEFAULT_VIEW_MODE,
  menuItems,
  menuMode = false,
  renderAction,
  showOrderQty = true,
}) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-muted-foreground">
        <span className="text-2xl mb-2 opacity-30">🔍</span>
        <span className="text-sm">{__("No items found")}</span>
      </div>
    );
  }

  const isCompact = viewMode === "compact";
  const minColWidth = VIEW_MODES[viewMode]?.minColWidth || 130;

  return (
    <div
      className={isCompact ? "flex flex-col gap-1" : "grid gap-2"}
      style={
        isCompact
          ? undefined
          : { gridTemplateColumns: `repeat(auto-fill, minmax(${minColWidth}px, 1fr))` }
      }
    >
      {items.map((item) => (
        <ItemCard
          key={item.item_code}
          item={item}
          onClick={onItemClick}
          viewMode={viewMode}
          inMenu={menuItems ? menuItems.has(item.item_code) : false}
          menuMode={menuMode}
          renderAction={renderAction}
          showOrderQty={showOrderQty}
        />
      ))}
    </div>
  );
});

export default ItemGrid;