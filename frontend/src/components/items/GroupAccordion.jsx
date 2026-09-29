import { useState, memo } from "react";
import { ChevronDown } from "lucide-react";
import ItemGrid from "./ItemGrid";
import { getCategoryColor } from "./itemConstants";

/**
 * GroupAccordion — Collapsible item group with category color indicator.
 */

const GroupAccordion = memo(function GroupAccordion({
  group,
  items,
  onItemClick,
  viewMode,
  menuItems,
  menuMode = false,
  renderAction,
  showOrderQty = true,
}) {
  const [open, setOpen] = useState(items.length > 0);
  const colors = getCategoryColor(group.name);

  return (
    <div className="rounded-lg overflow-hidden ring-1 ring-border">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2.5 bg-card hover:bg-accent/50 transition-colors"
      >
        <div className={`w-2 h-2 rounded-full shrink-0 ${colors.dot}`} />
        <span className="text-sm font-medium text-card-foreground">{group.name}</span>
        <span className={`text-[10px] font-semibold tabular-nums px-1.5 py-0.5 rounded-md ${colors.bg} ${colors.text}`}>
          {items.length}
        </span>
        <ChevronDown
          size={15}
          className={`ml-auto text-muted-foreground transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && items.length > 0 && (
        <div className="p-2 border-t border-border">
          <ItemGrid
            items={items}
            onItemClick={onItemClick}
            viewMode={viewMode}
            menuItems={menuItems}
            menuMode={menuMode}
            renderAction={renderAction}
            showOrderQty={showOrderQty}
          />
        </div>
      )}
    </div>
  );
});

export default GroupAccordion;