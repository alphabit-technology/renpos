import { memo } from "react";
import {ChefHat, FileText} from "lucide-react";
import { OrderItemRow } from "./OrderItemRow";

export const OrderItems = memo(function OrderItemsList({
  itemsList, currentItemId, hasOrder, onItemSelect,
}) {
  if (itemsList.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-zinc-600">
        {hasOrder ? (
          <>
            <ChefHat size={32} className="mb-2 opacity-30" />
            <span className="text-sm">No items added</span>
          </>
        ) : (
          <>
            <FileText size={32} className="mb-2 opacity-30" />
            <span className="text-sm">Select or create an order</span>
          </>
        )}
      </div>
    );
  }

  return (
    <>
      {itemsList.map((item) => (
        <OrderItemRow
          key={item.identifier}
          item={item}
          selected={currentItemId === item.identifier}
          onClick={onItemSelect}
        />
      ))}
    </>
  );
});