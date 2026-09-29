import {memo} from "react"
import { OrderTab } from "./OrderTab";
import {Plus} from "lucide-react"

export const OrderSidebar = memo(function OrderSidebar({
  orders, currentOrderName, onSelectOrder, onAddOrder, layout = "vertical",
}) {
  if (layout === "horizontal") {
    // Mobile: horizontal scrollable order list
    return (
      <div className="flex items-center gap-2 p-3 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
        <button
          onClick={onAddOrder}
          className="w-10 h-10 shrink-0 rounded-lg border border-dashed border-white/20 flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:border-white/30 transition-all"
        >
          <Plus size={18} />
        </button>
        {orders.map((order) => (
          <OrderTab
            key={order.name}
            order={order}
            selected={currentOrderName === order.name}
            onClick={onSelectOrder}
          />
        ))}
      </div>
    );
  }

  // Desktop: vertical sidebar
  return (
    <aside className="w-20 shrink-0 flex flex-col items-center gap-2 py-3 border-r border-white/10">
      <button
        onClick={onAddOrder}
        className="w-10 h-10 rounded-lg border border-dashed border-white/20 flex items-center justify-center text-zinc-500 hover:text-zinc-300 hover:border-white/30 transition-all"
      >
        <Plus size={18} />
      </button>
      <div className="flex-1 overflow-y-auto w-full flex flex-col items-center gap-1.5 py-1 px-0">
        {orders.map((order) => (
          <OrderTab
            key={order.name}
            order={order}
            selected={currentOrderName === order.name}
            onClick={onSelectOrder}
            onAction={(action, order) => {
               console.log(["On Action"])
              // tu lógica aquí
            }}
          />
        ))}
      </div>
    </aside>
  );
});