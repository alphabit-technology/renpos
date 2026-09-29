import { memo } from "react";
import { UtensilsCrossed, ShoppingCart, LayoutList } from "lucide-react";

const MOBILE_TABS = [
  { key: "orders", label: "Orders", icon: LayoutList },
  { key: "items", label: "Items", icon: UtensilsCrossed },
  { key: "cart", label: "Cart", icon: ShoppingCart },
];

export const MobileBottomTabs = memo(function MobileBottomTabs({
  activeTab, onTabChange, cartCount,
}) {
  return (
    <nav className="shrink-0 flex border-t border-white/[0.08] bg-[var(--card-bg,#111122)]">
      {MOBILE_TABS.map(({ key, label, icon: Icon }) => {
        const isActive = activeTab === key;
        const showBadge = key === "cart" && cartCount > 0;

        return (
          <button
            key={key}
            onClick={() => onTabChange(key)}
            className={`flex-1 flex flex-col items-center justify-center gap-0.5 py-2.5 text-[10px] font-medium transition-colors relative ${
              isActive
                ? "text-white bg-white/[0.06]"
                : "text-zinc-600 hover:text-zinc-400"
            }`}
          >
            <Icon size={18} />
            <span>{__(label)}</span>
            {showBadge && (
              <span className="absolute top-1.5 right-[calc(50%-18px)] min-w-[16px] h-4 rounded-full bg-emerald-500 text-white text-[9px] font-bold flex items-center justify-center px-1">
                {cartCount}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
});