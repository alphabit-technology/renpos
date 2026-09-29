import { memo, useRef } from "react";
import { Plus } from "lucide-react";
import { OrderTab } from "./OrderTab";

/**
 * OrderTabs — Horizontal tab bar using OrderTab variant="tab".
 *
 * Designed for modal header:
 *   - fontSize: 0 resets inherited title size
 *   - ml-auto pushes tabs to the right
 *   - Each tab uses OrderTab with full ⋮ menu
 *
 * Props:
 *   @param {Array}    orders           - [{name, short_name, items_count, pending_count}]
 *   @param {string}   currentOrderName
 *   @param {function} onSelectOrder
 *   @param {function} onAddOrder
 *   @param {function} onAction         - (action, order) => void
 */
export const OrderTabs = memo(function OrderTabs({
  orders = [],
  currentOrderName,
  onSelectOrder,
  onAddOrder,
  onAction,
}) {
  const tabsRef = useRef(null);

  return (
    <div
      ref={tabsRef}
      className="flex items-stretch gap-0.5 self-stretch min-w-0 ml-auto overflow-x-auto scrollbar-none"
      style={{ fontSize: 0 }}
    >
      {orders.map((order, index) => (
        <OrderTab
          key={order.name}
          order={order}
          selected={order.name === currentOrderName}
          onClick={onSelectOrder}
          onAction={onAction}
          variant="sidebar"
          index={index}
        />
      ))}

      <button
        onClick={onAddOrder}
        style={{ fontSize: 14 }}
        className="shrink-0 w-12 flex items-center justify-center self-stretch
                   text-muted-foreground hover:text-foreground hover:bg-muted/50
                   rounded-t-lg transition-colors"
        title={__("New Order")}
      >
        <Plus size={15} />
      </button>
    </div>
  );
});

export default OrderTabs;