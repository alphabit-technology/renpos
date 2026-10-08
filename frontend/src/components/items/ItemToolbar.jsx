import { memo } from "react";
import { Search } from "lucide-react";
import { useMenuTags } from "./menuTags";
import { VIEW_MODES } from "./itemConstants";
import { useIsMobile } from "@c/order/hooks/useIsMobile";

const ViewModeToggle = memo(function ViewModeToggle({ viewMode, onChange }) {
  return (
    <div className="flex rounded-lg overflow-hidden ring-1 ring-border shrink-0">
      {Object.values(VIEW_MODES).map((mode) => (
        <button
          key={mode.key}
          onClick={() => onChange(mode.key)}
          title={mode.label}
          className={`w-9 h-9 flex items-center justify-center transition-colors ${
            viewMode === mode.key
              ? "bg-accent text-foreground"
              : "bg-transparent text-muted-foreground/60 hover:text-muted-foreground hover:bg-accent/50"
          }`}
        >
          <i className={`fa ${mode.icon} text-xs`} />
        </button>
      ))}
    </div>
  );
});

function ItemToolbar({
  itemType,
  onItemTypeChange,
  search,
  onSearchChange,
  searchRef,
  viewMode,
  onViewModeChange,
}) {
  // phones: icon-only filters so toolbar fits in a single row
  const compact = useIsMobile();
  // quick filters: Menu Tags marked "Filter in the POS"
  const filterTags = useMenuTags().filter((t) => t.show_as_filter);
  return (
    <div className={`flex items-center gap-2 shrink-0 ${compact ? "" : "flex-wrap"}`}>
      {filterTags.length > 0 && (
        <div className="flex shrink-0 gap-1 overflow-x-auto scrollbar-none max-w-[45%]">
          {filterTags.map((t) => {
            const on = itemType === t.name;
            return (
              <button
                key={t.name}
                title={t.name}
                onClick={() => onItemTypeChange(on ? null : t.name)}
                style={{ borderColor: t.color || undefined, color: on ? "#fff" : t.color || undefined,
                         background: on ? t.color || "var(--primary)" : "transparent" }}
                className="px-2.5 py-2 border text-xs font-semibold rounded-lg whitespace-nowrap transition-colors"
              >
                {compact ? (t.abbreviation || t.name) : t.name}
              </button>
            );
          })}
        </div>
      )}

      <div className={`relative flex-1 ${compact ? "min-w-0" : "min-w-[140px]"}`}>
        <Search
          size={15}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/60 pointer-events-none"
        />
        <input
          ref={searchRef}
          type="text"
          placeholder={__("Search Items")}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full h-9 pl-8 pr-3 rounded-lg bg-foreground/[0.04] border border-border text-sm text-card-foreground outline-none focus:border-ring focus:bg-foreground/[0.06] placeholder:text-muted-foreground/60 transition-colors"
        />
      </div>

      {onViewModeChange && (
        <ViewModeToggle viewMode={viewMode} onChange={onViewModeChange} />
      )}
    </div>
  );
}

export default ItemToolbar;