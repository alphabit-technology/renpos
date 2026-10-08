import { memo, useCallback, useState, useRef, useEffect } from "react";
import { MoreVertical, Trash2, Copy, FileText, ArrowRightLeft, Smartphone, Truck } from "lucide-react";

/**
 * OrderTab — Single order button with ⋮ actions.
 *
 * Supports two variants:
 *   - "sidebar" (default): vertical sidebar style (h-14, w-full, rounded-xl)
 *   - "tab": horizontal Chrome-style tab for modal header (self-stretch, rounded-t-lg)
 *
 * Props:
 *   @param {object}   order    - { name, short_name, items_count, pending_count }
 *   @param {boolean}  selected
 *   @param {function} onClick  - (orderName) => void
 *   @param {function} onAction - (action, order) => void
 *   @param {"sidebar"|"tab"} [variant="sidebar"]
 *   @param {number}   [index]  - tab index (used for inactive tab label in "tab" variant)
 */
export const OrderTab = memo(function OrderTab({
  order,
  selected,
  onClick,
  onAction,
  variant = "sidebar",
  index,
}) {
  const handleClick = useCallback(
    () => onClick(order.name),
    [onClick, order.name]
  );

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [menuOpen]);

  const handleAction = useCallback((action, e) => {
    e.stopPropagation();
    setMenuOpen(false);
    onAction?.(action, order);
  }, [onAction, order]);

  const displayName = order.short_name || order.name?.slice(-5);
  // placed by the guest from their phone (online pickup / QR at the table)
  const origin = order.ren_delivery
    ? (order.ren_origin === "Online" ? __("Online delivery") : __("Phone delivery"))
    : order.ren_origin === "Online" ? __("Online pickup") : order.ren_origin === "Table QR" ? __("Ordered from the table") : "";
  const guestTitle = origin ? [origin, order.ren_guest_name].filter(Boolean).join(" · ") : "";
  const MarkIcon = order.ren_delivery ? Truck : Smartphone;
  const guestMark = origin
    ? <MarkIcon size={13} className="shrink-0 text-sky-400" aria-label={guestTitle} />
    : null;
  const itemCount = order.items_count || 0;
  const pendingCount = order.pending_count || 0;

  // ── Tab variant (horizontal, for modal header) ──
  if (variant === "tab") {
    return (
      <div className="relative shrink-0 flex self-stretch" ref={menuRef}>
        <button
          onClick={handleClick}
          style={{ fontSize: 14 }}
          className={`group relative flex items-center gap-1.5 shrink-0
                     min-w-0 max-w-[180px] px-3 rounded-t-lg
                     transition-all border-b-2 border
                     ${selected
                       ? "bg-card text-foreground !border-b-primary border-x border-x-border"
                       : "bg-card w-[50px] text-muted-foreground border-b-transparent hover:text-foreground hover:bg-muted/50"
                     }`}
        >
          {/* Tab label */}
          {guestMark}
          <span className={`truncate ${selected ? "font-bold" : "font-medium"}`} title={guestTitle || undefined}>
            {selected ? (order.ren_guest_name || displayName) : (index != null ? index + 1 : displayName)}
          </span>

          {/* Pending badge */}
          {pendingCount > 0 && (
            <span className="shrink-0 min-w-[18px] h-[18px] rounded-full bg-red-500
                           text-white text-[10px] font-bold flex items-center
                           justify-center px-1 leading-none">
              {pendingCount}
            </span>
          )}

          {/* ⋮ button */}
          {onAction && (
            <span
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((v) => !v);
              }}
              className={`shrink-0 w-5 h-5 rounded flex items-center justify-center
                         transition-all cursor-pointer
                         hover:bg-accent
                         ${menuOpen ? "opacity-100" : ""}
                         ${selected
                           ? "opacity-50 hover:opacity-100 text-muted-foreground hover:text-foreground"
                           : "opacity-0 group-hover:opacity-60 text-muted-foreground"
                         }`}
            >
              <MoreVertical size={11} />
            </span>
          )}
        </button>

        {/* Dropdown — below the tab */}
        {menuOpen && (
          <div
            className="absolute left-0 top-full mt-0.5 z-50
                       w-40 rounded-lg bg-popover border border-border shadow-xl
                       py-1"
          >
            <DropdownItem icon={FileText} label={__("Details")} onClick={(e) => handleAction("details", e)} />
            <DropdownItem icon={ArrowRightLeft} label={__("Transfer")} onClick={(e) => handleAction("transfer", e)} />
            <DropdownItem icon={Copy} label={__("Duplicate")} onClick={(e) => handleAction("duplicate", e)} />
            <div className="h-px bg-border mx-2 my-1" />
            <DropdownItem icon={Trash2} label={__("Delete")} destructive onClick={(e) => handleAction("delete", e)} />
          </div>
        )}
      </div>
    );
  }

  // ── Sidebar variant (default, vertical) ──
  return (
    <div className="relative w-full group" ref={menuRef}>
      <button
        onClick={handleClick}
        className={`px-2 relative flex flex-row w-full h-full rounded-xl flex items-center justify-center transition-all ${
          selected
            ? "bg-amber-500/20 text-amber-400 ring-1 ring-amber-500/30"
            : "px-3 bg-secondary/70 text-muted-foreground hover:bg-secondary hover:text-card-foreground"
        }`}
      >
        {guestMark}
        <span className="text-sm font-bold leading-none truncate px-1" title={guestTitle || undefined}>
          {selected ? (order.ren_guest_name || displayName) : index + 1}
        </span>

        {itemCount > 0 && (
          <span
            title={pendingCount > 0
              ? __("{0} items · {1} not sent", [itemCount, pendingCount])
              : __("{0} items", [itemCount])}
            className={`absolute -top-1 -right-1 min-w-[18px] h-[18px] rounded-full text-[10px] font-bold flex items-center justify-center px-1 shadow-md ${
              pendingCount > 0
                ? "bg-orange-500 text-white shadow-orange-500/30"
                : selected
                  ? "bg-amber-500 text-black shadow-amber-500/30"
                  : "bg-zinc-600 text-white"
            }`}
          >
            {itemCount}
          </span>
        )}

        {onAction && (
          <span
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpen((v) => !v);
            }}
            className={`absolute top-0.5 right-0.5
              w-5 h-5 flex items-center justify-center rounded-md cursor-pointer
              transition-opacity
              ${menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100"}
              ${selected
                ? "text-amber-400/60 hover:text-amber-400 hover:bg-amber-500/10"
                : "text-muted-foreground/40 hover:text-muted-foreground hover:bg-white/5"}
            `}
          >
            <MoreVertical size={11} />
          </span>
        )}
      </button>

      {/* Dropdown — to the right of the sidebar */}
      {menuOpen && (
        <div
          className="absolute left-full top-0 ml-1.5 z-50
                     w-40 rounded-lg bg-popover border border-border shadow-xl
                     py-1"
        >
          <DropdownItem icon={FileText} label={__("Details")} onClick={(e) => handleAction("details", e)} />
          <DropdownItem icon={ArrowRightLeft} label={__("Transfer")} onClick={(e) => handleAction("transfer", e)} />
          <DropdownItem icon={Copy} label={__("Duplicate")} onClick={(e) => handleAction("duplicate", e)} />
          <div className="h-px bg-border mx-2 my-1" />
          <DropdownItem icon={Trash2} label={__("Delete")} destructive onClick={(e) => handleAction("delete", e)} />
        </div>
      )}
    </div>
  );
}, (prev, next) => {
  return (
    prev.selected === next.selected &&
    prev.variant === next.variant &&
    prev.index === next.index &&
    prev.onClick === next.onClick &&
    prev.onAction === next.onAction &&
    prev.order.name === next.order.name &&
    prev.order.items_count === next.order.items_count &&
    prev.order.pending_count === next.order.pending_count &&
    prev.order.short_name === next.order.short_name
  );
});

function DropdownItem({ icon: Icon, label, onClick, destructive = false }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs transition-colors ${
        destructive
          ? "text-destructive hover:bg-destructive/10"
          : "text-popover-foreground hover:bg-accent"
      }`}
    >
      <Icon size={12} />
      {label}
    </button>
  );
}

export default OrderTab;