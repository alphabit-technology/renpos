import { memo, useState, useRef, useEffect, useCallback } from "react";
import { MoreVertical, Pencil, XCircle, Trash2, Plus, X } from "lucide-react";

/**
 * OrderHeader — Chrome-style order tabs + management menu.
 *
 * ┌────────────────────────────────────────────────┐
 * │  [OR-00011 ×] [OR-00012 ×] [OR-00013 ×]  [+] │  tabs
 * ├────────────────────────────────────────────────┤
 * │  OR-2026-00011  · 9 items   Draft          ⋮  │  info bar
 * └────────────────────────────────────────────────┘
 *
 * Props:
 *   @param {Array}    orders           - [{name, item_count, status, pending_count}]
 *   @param {string}   currentOrderName - selected order name
 *   @param {function} onSelectOrder    - (orderName) => void
 *   @param {function} onAddOrder       - () => void
 *   @param {number}   itemCount        - items in current order
 *   @param {string}   [status]         - current order status
 *   @param {function} onEdit
 *   @param {function} onCancel
 *   @param {function} onDelete
 */
export const OrderHeader = memo(function OrderHeader({
  orders = [],
  currentOrderName,
  onSelectOrder,
  onAddOrder,
  itemCount = 0,
  status,
  onEdit,
  onCancel,
  onDelete,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);
  const tabsRef = useRef(null);

  // Close menu on outside click
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

  const fire = useCallback((action) => {
    setMenuOpen(false);
    action?.();
  }, []);

  // Short display name: "00011" from "OR-2026-00011"
  const shortName = (name) => {
    if (!name) return "";
    const parts = name.split("-");
    return parts[parts.length - 1];
  };

  return (
    <div className="shrink-0 flex flex-col border-b border-border">
      {/* ── Order Tabs (Chrome-style) ── */}
      <div className="flex items-end gap-0 bg-muted/30 px-1 pt-1 overflow-x-auto scrollbar-none" ref={tabsRef}>
        {orders.map((order) => {
          const active = order.name === currentOrderName;
          return (
            <button
              key={order.name}
              onClick={() => onSelectOrder(order.name)}
              className={`group relative flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium
                         rounded-t-lg transition-all min-w-0 max-w-[160px] shrink-0
                         ${active
                           ? "bg-card text-foreground border-t border-x border-border -mb-px z-10"
                           : "bg-transparent text-muted-foreground hover:text-foreground hover:bg-muted/50"
                         }`}
            >
              {/* Tab label */}
              <span className="truncate">
                {shortName(order.name)}
              </span>

              {/* Pending badge */}
              {order.pending_count > 0 && (
                <span className="shrink-0 min-w-[16px] h-[16px] rounded-full bg-red-500
                               text-white text-[9px] font-bold flex items-center
                               justify-center px-0.5">
                  {order.pending_count}
                </span>
              )}

              {/* Close button (visible on hover / always on active) */}
              {orders.length > 1 && (
                <span
                  role="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectOrder(order.name);
                    // Small delay so the order is selected before delete menu opens
                    setTimeout(() => onDelete?.(), 50);
                  }}
                  className={`shrink-0 w-4 h-4 rounded-sm flex items-center justify-center
                             transition-colors hover:bg-destructive/20 hover:text-destructive
                             ${active ? "opacity-60 hover:opacity-100" : "opacity-0 group-hover:opacity-60"}`}
                >
                  <X size={10} />
                </span>
              )}
            </button>
          );
        })}

        {/* Add order button */}
        <button
          onClick={onAddOrder}
          className="shrink-0 w-7 h-7 flex items-center justify-center rounded-t-lg
                     text-muted-foreground hover:text-foreground hover:bg-muted/50
                     transition-colors mb-0.5 ml-0.5"
          title={__("New Order")}
        >
          <Plus size={14} />
        </button>
      </div>

      {/* ── Info Bar ── */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-card">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-foreground truncate">
            {currentOrderName}
          </span>
          <span className="text-[10px] text-muted-foreground whitespace-nowrap">
            · {itemCount} {itemCount === 1 ? __("item") : __("items")}
          </span>
          {status && (
            <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full
                           bg-accent text-accent-foreground whitespace-nowrap">
              {status}
            </span>
          )}
        </div>

        {/* ⋮ menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="w-6 h-6 flex items-center justify-center rounded-md
                       text-muted-foreground hover:text-foreground hover:bg-muted
                       transition-colors"
          >
            <MoreVertical size={14} />
          </button>

          {menuOpen && (
            <div
              className="absolute right-0 top-full mt-1 w-44 z-50
                         bg-popover border border-border rounded-lg shadow-xl py-1"
            >
              <MenuItem
                icon={Pencil}
                label={__("Edit Details")}
                onClick={() => fire(onEdit)}
              />
              <MenuItem
                icon={XCircle}
                label={__("Cancel Order")}
                onClick={() => fire(onCancel)}
              />
              <div className="h-px bg-border mx-2 my-1" />
              <MenuItem
                icon={Trash2}
                label={__("Delete Order")}
                destructive
                onClick={() => fire(onDelete)}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

function MenuItem({ icon: Icon, label, onClick, destructive = false }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors ${
        destructive
          ? "text-destructive hover:bg-destructive/10"
          : "text-popover-foreground hover:bg-accent"
      }`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

export default OrderHeader;