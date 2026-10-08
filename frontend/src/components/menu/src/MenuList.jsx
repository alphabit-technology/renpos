import { Star, StarOff, Trash2, Clock,
  ToggleLeft, ToggleRight 
} from "lucide-react";

export function MenuList({ menu, isActive, onSelect, onSetDefault, onToggleEnabled, onDelete }) {
  const EnabledComp = menu.enabled ? ToggleRight  : ToggleLeft;

  return (
    <div
      onClick={onSelect}
      className={`group flex items-center gap-2 px-2 py-2 mx-1 rounded-lg cursor-pointer
        transition-colors select-none
        ${isActive ? "bg-accent text-accent-foreground" : "text-card-foreground hover:bg-muted/60"}`}
    >
      <button
        onClick={(e) => { e.stopPropagation(); onSetDefault(); }}
        className={`shrink-0 transition-colors ${
          menu.is_active ? "text-amber-400" : "text-muted-foreground/30 hover:text-amber-400/60"
        }`}
        title={menu.is_active ? __("The restaurant's menu") : __("Use as the restaurant's menu")}
      >
        {menu.is_active ? <Star size={18} fill="currentColor" /> : <StarOff size={13} />}
      </button>

      <div className="flex-1 min-w-0">
        <span className={`text-xs font-medium truncate block ${!menu.enabled ? "line-through opacity-50" : ""}`}>
          {menu.menu_name}
          {menu.scheduled ? (
            <Clock size={11} className={`inline ml-1 -mt-0.5 ${menu.in_force ? "text-emerald-400" : "text-muted-foreground"}`}
              aria-label={menu.in_force ? __("In force now (schedule)") : __("Has a schedule")} />
          ) : null}
        </span>
        <span className="text-[10px] text-muted-foreground tabular-nums">
          {menu.total_items || 0} {__("items")}
          {menu.rooms?.length > 0 && (
            <span className="text-amber-300/80" title={__("Rooms with this menu of their own")}> · {menu.rooms.join(", ")}</span>
          )}
        </span>
      </div>

      <div className={`flex items-center gap-0.5 shrink-0 transition-opacity ${
        isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"
      }`}>
        <button
          onClick={(e) => { e.stopPropagation(); onToggleEnabled(); }}
          className="p-1 h-full rounded hover:bg-muted transition-colors text-muted-foreground"
          title={menu.enabled ? __("Disable") : __("Enable")}
        >
          <EnabledComp size={18} className={menu.enabled ? "text-emerald-400" : ""}/>
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="p-1 h-full rounded hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
          title={__("Delete")}
        >
          <Trash2 size={18} />
        </button>
      </div>
    </div>
  );
}
