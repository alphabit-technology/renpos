import { memo, useCallback } from "react";
import { getCategoryColor } from "./itemConstants";

const ALL_TAB_NAME = "All Item Groups";

const GroupTab = memo(function GroupTab({ group, isActive, onClick, vertical }) {
  const isAll = group.name === ALL_TAB_NAME;
  const label = isAll ? __("All") : group.name;
  const colors = isAll ? null : getCategoryColor(group.name);

  const handleClick = useCallback(
    () => onClick(group.name),
    [onClick, group.name]
  );

  if (vertical) {
    // side column: tall, easy-to-hit rows with a color bar
    return (
      <button
        onClick={handleClick}
        className={`relative shrink-0 w-full min-h-[44px] flex items-center gap-2 pl-3 pr-2 py-2 rounded-lg text-left text-sm font-semibold transition-all ${
          isActive
            ? isAll ? "bg-accent text-foreground" : `${colors.bg} ${colors.text}`
            : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
        }`}
      >
        <span className={`absolute left-0 top-2 bottom-2 w-1 rounded-full ${
          isActive ? (isAll ? "bg-foreground/60" : colors.dot) : "bg-transparent"}`} />
        <span className="leading-tight line-clamp-2">{label}</span>
      </button>
    );
  }

  if (isAll) {
    return (
      <button
        onClick={handleClick}
        className={`shrink-0 flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
          isActive
            ? "bg-accent text-foreground ring-1 ring-border"
            : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
        }`}
      >
        {label}
      </button>
    );
  }

  return (
    <button
      onClick={handleClick}
      className={`shrink-0 flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
        isActive
          ? `${colors.bg} ${colors.text} ring-1 ${colors.ring}`
          : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
      }`}
    >
      <div
        className={`w-1.5 h-1.5 rounded-full shrink-0 ${
          isActive ? colors.dot : "bg-muted-foreground/30"
        }`}
      />
      {label}
    </button>
  );
}, (prev, next) => {
  return (
    prev.isActive === next.isActive &&
    prev.vertical === next.vertical &&
    prev.onClick === next.onClick &&
    prev.group.name === next.group.name
  );
});

function ItemGroupTabs({ tabs, activeTab, onTabChange, vertical = false, className = "" }) {
  if (tabs.length === 0) return null;

  if (vertical) {
    return (
      <nav className={`flex flex-col gap-1 p-2 overflow-y-auto overscroll-contain ${className}`} style={{ scrollbarWidth: "thin" }}>
        {tabs.map((group) => (
          <GroupTab key={group.name} group={group} isActive={activeTab === group.name} onClick={onTabChange} vertical />
        ))}
      </nav>
    );
  }

  return (
    <div
      className={`flex gap-1.5 px-3 py-2 overflow-x-auto shrink-0 ${className}`}
      style={{ scrollbarWidth: "none" }}
    >
      {tabs.map((group) => (
        <GroupTab
          key={group.name}
          group={group}
          isActive={activeTab === group.name}
          onClick={onTabChange}
        />
      ))}
    </div>
  );
}

export default ItemGroupTabs;