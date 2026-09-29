import { memo } from "react";
import { Search, Leaf, Flame } from "lucide-react";
import { VIEW_MODES } from "./itemConstants";

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
  return (
    <div className="flex items-center gap-2 shrink-0 flex-wrap">
      <div className="flex shrink-0 gap-1">
        <button
          className={`px-3 py-2 border text-xs flex items-center gap-1.5 rounded-l-lg transition-all border-emerald-500/60 ${
            itemType === "Veg"
              ? "bg-emerald-500/20 text-emerald-400 border-emerald-500"
              : "text-emerald-500/60 bg-transparent hover:bg-emerald-500/10 hover:text-emerald-400"
          }`}
          onClick={() => onItemTypeChange(itemType === "Veg" ? null : "Veg")}
        >
          <Leaf size={13} /> {__("Veg")}
        </button>
        <button
          className={`px-3 py-2 border text-xs flex items-center gap-1.5 rounded-r-lg transition-all border-amber-500/60 ${
            itemType === "Non-Veg"
              ? "bg-amber-500/20 text-amber-400 border-amber-500"
              : "text-amber-500/60 bg-transparent hover:bg-amber-500/10 hover:text-amber-400"
          }`}
          onClick={() =>
            onItemTypeChange(itemType === "Non-Veg" ? null : "Non-Veg")
          }
        >
          <Flame size={13} /> {__("Non-Veg")}
        </button>
      </div>

      <div className="relative flex-1 min-w-[140px]">
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