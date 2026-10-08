import { memo, useState, useEffect } from "react";
import { Ban } from "lucide-react";
import { ItemTree } from "@c/items";
import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useRooms} from "@/context/RoomsContext"
import { SoldOutDialog } from "./SoldOutDialog";

export const ItemCatalog = memo(function ItemCatalog({ onItemClick }) {
  const { REN } = useRestaurant();
  const { activeMenu } = useRooms();
  const [soldOutOpen, setSoldOutOpen] = useState(false);
  const [soldOutCount, setSoldOutCount] = useState(0);

  // how many items are 86'd right now (badge), live
  useEffect(() => {
    let cancelled = false;
    const load = () => frappe.call({ method: "renpos.api.menus.get_sold_out" }).then(
      (r) => { if (!cancelled) setSoldOutCount((r.message || []).length); }, () => {});
    load();
    frappe.realtime.on("menu_availability", load);
    return () => { cancelled = true; frappe.realtime.off("menu_availability", load); };
  }, []);

  return (
    <main className="flex-1 flex flex-col min-w-0 min-h-0 relative">
      <button
        onClick={() => setSoldOutOpen(true)}
        title={__("Sold out (86)")}
        className={`absolute bottom-3 right-3 z-10 flex items-center gap-1.5 h-9 px-3 rounded-full shadow-lg text-xs font-semibold
          ${soldOutCount ? "bg-rose-600 text-white" : "bg-card border border-border text-muted-foreground hover:text-foreground"}`}
      >
        <Ban size={14} /> 86{soldOutCount ? ` · ${soldOutCount}` : ""}
      </button>
      <ItemTree
        enabled={true}
        className="flex-1"
        onItemClick={onItemClick}
        menuName={activeMenu || "__not_assigned_menu__"}
        priceList={REN?.pos_profile?.selling_price_list}
        restaurant={REN?.restaurant?.name}
        menuMode={false}
        showOrderQty={true}
        sideGroups
      />
      {soldOutOpen && <SoldOutDialog open menuName={activeMenu} onClose={() => setSoldOutOpen(false)} />}
    </main>
  );
});
