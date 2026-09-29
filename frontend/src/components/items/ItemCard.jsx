import { memo, useCallback } from "react";
import { useOrderQty } from "../order/OrderQtyStore";
import { getCategoryColor } from "./itemConstants";
import { Check } from "lucide-react";

/**
 * ItemCard — POS-optimized item card with 3 view modes.
 *
 * Category color always visible at full strength.
 * Active state (in order or in menu) indicated by ring-2 + badge.
 *
 * Visual states:
 * 1. In Order  → ring-2 emerald + qty badge
 * 2. In Menu   → ring-2 category color + check badge
 * 3. Default   → no ring, category tint bg + colored text
 * 4. 86'd      → dimmed + label
 */

function formatCurrency(value) {
  return typeof RM !== "undefined" && RM.format_currency
    ? RM.format_currency(value)
    : `$ ${Number(value).toFixed(2)}`;
}

function QtyBadge({ qty, size = "md", className = "" }) {
  if (qty <= 0) return null;
  const sizes = {
    sm: "min-w-[18px] h-[18px] text-[9px] px-1",
    md: "min-w-[22px] h-[22px] text-[11px] px-1.5",
  };
  return (
    <span className={`inline-flex items-center justify-center rounded-full bg-emerald-500 text-white font-bold leading-none shadow-[0_0_8px_rgba(16,185,129,0.35)] ${sizes[size] || sizes.md} ${className}`}>
      {qty}
    </span>
  );
}

function MenuBadge({ badgeClass, className = "" }) {
  return (
    <span className={`inline-flex items-center justify-center w-[20px] h-[20px] rounded-full text-white shadow-sm ${badgeClass} ${className}`}>
      <Check size={11} strokeWidth={3} />
    </span>
  );
}

// ═══════════════════════════════════════════════
//  TILE MODE
// ═══════════════════════════════════════════════

function TileView({ item, qty, onClick, colors, isAvailable, inMenu, menuMode, renderAction }) {
  const hasQty = qty > 0;

  // Ring only when active (in order or in menu)
  const ringClass = hasQty
    ? "ring-2 ring-emerald-500/60"
    : (menuMode && inMenu)
      ? `ring-2 ${colors.ring}`
      : "";

  return (
    <button
      type="button"
      onClick={isAvailable ? onClick : undefined}
      className={`
        group relative flex flex-col min-h-[80px] w-full rounded-lg
        p-2.5 text-left select-none
        transition-all duration-150
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
        ${isAvailable ? "cursor-pointer active:scale-[0.97]" : "cursor-not-allowed opacity-40"}
        ${colors.bg}
        ${ringClass}
      `}
      aria-disabled={!isAvailable}
    >
      <span className={`text-[13px] font-semibold leading-snug line-clamp-2 pr-6 ${
        hasQty ? "text-emerald-400" : colors.text
      }`}>
        {item.item_name || item.item_code}
      </span>

      {isAvailable ? (
        <span className={`text-[11px] font-medium tabular-nums mt-auto pt-1 ${
          hasQty ? "text-emerald-400/60" : "text-muted-foreground"
        }`}>
          {item.price_list_rate > 0 ? formatCurrency(item.price_list_rate) : ""}
        </span>
      ) : (
        <span className="text-[10px] font-bold uppercase tracking-wider text-destructive mt-auto pt-1">
          86'd
        </span>
      )}

      {/* Badge */}
      {hasQty ? (
        <div className="absolute top-2 right-2">
          <QtyBadge qty={qty} size="md" />
        </div>
      ) : (menuMode && inMenu) ? (
        <div className="absolute top-2 right-2">
          <MenuBadge badgeClass={colors.stripe} />
        </div>
      ) : null}

      {renderAction && (
        <div className="absolute bottom-1.5 right-1.5 z-10" onClick={(e) => e.stopPropagation()}>
          {renderAction(item)}
        </div>
      )}
    </button>
  );
}

// ═══════════════════════════════════════════════
//  IMAGE MODE
// ═══════════════════════════════════════════════

function ImageView({ item, qty, onClick, colors, isAvailable, inMenu, menuMode, renderAction }) {
  const title = item.item_name || item.item_code;
  const abbr = title
    .split(" ")
    .map((w) => w[0] || "")
    .join("")
    .substring(0, 2)
    .toUpperCase();
  const hasQty = qty > 0;

  const ringClass = hasQty
    ? "ring-2 ring-emerald-500/60"
    : (menuMode && inMenu)
      ? `ring-2 ${colors.ring}`
      : "";

  return (
    <button
      type="button"
      onClick={isAvailable ? onClick : undefined}
      className={`
        group relative flex flex-col rounded-lg overflow-hidden text-left
        transition-all duration-150 select-none w-full
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
        ${isAvailable ? "cursor-pointer active:scale-[0.97]" : "cursor-not-allowed opacity-40"}
        ${ringClass}
      `}
      aria-disabled={!isAvailable}
    >
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-muted">
        {item.image ? (
          <img
            src={item.image}
            alt={title}
            loading="lazy"
            decoding="async"
            className="absolute inset-0 w-full h-full object-cover transition-transform duration-150 group-hover:scale-105"
          />
        ) : (
          <div className={`absolute inset-0 flex items-center justify-center ${colors.bg}`}>
            <span className={`text-xl font-bold ${colors.text} opacity-40 select-none`}>
              {abbr}
            </span>
          </div>
        )}

        {item.price_list_rate > 0 && (
          <div className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/65 backdrop-blur-sm">
            <span className="text-[10px] font-semibold text-white/90 tabular-nums">
              {formatCurrency(item.price_list_rate)}
            </span>
          </div>
        )}

        {hasQty ? (
          <QtyBadge qty={qty} size="md" className="absolute top-1.5 right-1.5" />
        ) : (menuMode && inMenu) ? (
          <MenuBadge badgeClass={colors.stripe} className="absolute top-1.5 right-1.5" />
        ) : null}

        {!isAvailable && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/50">
            <span className="text-sm font-bold text-white uppercase tracking-wider">86'd</span>
          </div>
        )}
      </div>

      <div className={`px-2 py-1.5 ${colors.bg}`}>
        <span className={`block text-[11px] font-medium leading-tight line-clamp-2 ${
          hasQty ? "text-emerald-400" : colors.text
        }`}>
          {title}
        </span>
      </div>

      {renderAction && (
        <div className="absolute bottom-1.5 right-1.5 z-10" onClick={(e) => e.stopPropagation()}>
          {renderAction(item)}
        </div>
      )}
    </button>
  );
}

// ═══════════════════════════════════════════════
//  COMPACT / LIST MODE
// ═══════════════════════════════════════════════

function CompactView({ item, qty, onClick, colors, isAvailable, inMenu, menuMode, renderAction }) {
  const hasQty = qty > 0;

  const ringClass = hasQty
    ? "ring-2 ring-emerald-500/60"
    : (menuMode && inMenu)
      ? `ring-2 ${colors.ring}`
      : "";

  return (
    <button
      type="button"
      onClick={isAvailable ? onClick : undefined}
      className={`
        group flex items-center gap-2 w-full px-2.5 py-2 rounded-lg
        text-left transition-all duration-150 select-none
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring
        ${isAvailable ? "cursor-pointer active:scale-[0.98]" : "cursor-not-allowed opacity-40"}
        ${colors.bg}
        ${ringClass}
      `}
      aria-disabled={!isAvailable}
    >
      <div className={`w-2 h-2 rounded-full shrink-0 ${hasQty ? "bg-emerald-500" : colors.dot}`} />

      <span className={`flex-1 text-xs font-medium truncate ${hasQty ? "text-emerald-400" : colors.text}`}>
        {item.item_name || item.item_code}
      </span>

      {!isAvailable && (
        <span className="text-[9px] font-bold uppercase tracking-wider text-destructive shrink-0">
          86'd
        </span>
      )}

      <span className="text-[10px] font-medium text-muted-foreground/60 tabular-nums shrink-0">
        {item.price_list_rate > 0 ? formatCurrency(item.price_list_rate) : ""}
      </span>

      {hasQty ? (
        <QtyBadge qty={qty} size="sm" />
      ) : (menuMode && inMenu) ? (
        <MenuBadge badgeClass={colors.stripe} />
      ) : null}

      {renderAction && (
        <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
          {renderAction(item)}
        </div>
      )}
    </button>
  );
}

// ═══════════════════════════════════════════════
//  EXPORTED COMPONENT
// ═══════════════════════════════════════════════

const VIEW_COMPONENTS = {
  tile: TileView,
  image: ImageView,
  compact: CompactView,
};

const ItemCard = memo(
  function ItemCard({
    item,
    onClick,
    viewMode = "tile",
    inMenu = false,
    menuMode = false,
    renderAction,
    showOrderQty = true,
  }) {
    const orderQty = showOrderQty ? useOrderQty(item.item_code) : 0;
    const colors = getCategoryColor(item.item_group);
    const isAvailable = item.is_available !== false;

    const handleClick = useCallback(() => onClick?.(item), [onClick, item]);

    const ViewComponent = VIEW_COMPONENTS[viewMode] || TileView;

    return (
      <ViewComponent
        item={item}
        qty={orderQty}
        onClick={handleClick}
        colors={colors}
        isAvailable={isAvailable}
        inMenu={inMenu}
        menuMode={menuMode}
        renderAction={renderAction}
      />
    );
  },
  (prev, next) => {
    if (prev.viewMode !== next.viewMode) return false;
    if (prev.onClick !== next.onClick) return false;
    if (prev.inMenu !== next.inMenu) return false;
    if (prev.menuMode !== next.menuMode) return false;
    if (prev.renderAction !== next.renderAction) return false;
    if (prev.showOrderQty !== next.showOrderQty) return false;

    const a = prev.item;
    const b = next.item;
    return (
      a.item_code === b.item_code &&
      a.item_name === b.item_name &&
      a.item_group === b.item_group &&
      a.price_list_rate === b.price_list_rate &&
      a.image === b.image &&
      a.is_available === b.is_available
    );
  }
);

export default ItemCard;