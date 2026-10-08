import { Truck, Phone, AlertTriangle } from "lucide-react";
import { formatCurrency } from "@c/order/orderItems/calculator";

/**
 * DeliveryBanner — on a delivery order (api/delivery.py): where it goes, the
 * zone, the fee, the time promised, the phone, and how much is missing to
 * reach the zone's minimum order.
 */
export function DeliveryBanner({ order, itemsTotal = 0, compact = false }) {
  if (!order?.ren_delivery) return null;
  const by = order.ren_deliver_by
    ? new Date(String(order.ren_deliver_by).replace(" ", "T")).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : "";
  const missing = Math.max((Number(order.ren_delivery_minimum) || 0) - (Number(itemsTotal) || 0), 0);
  const fee = Number(order.ren_delivery_fee) || 0;

  return (
    <div className={`shrink-0 border-b border-border bg-sky-500/10 ${compact ? "px-3 py-2" : "px-3.5 py-2.5"}`}>
      <div className="flex items-start gap-2">
        <Truck size={16} className="shrink-0 mt-0.5 text-sky-400" />
        <div className="min-w-0 flex-1 text-sm leading-snug">
          <div className="font-semibold truncate" title={order.ren_delivery_address}>
            {order.ren_delivery_address}{order.ren_delivery_zip && !String(order.ren_delivery_address).includes(order.ren_delivery_zip) ? ` · ${order.ren_delivery_zip}` : ""}
          </div>
          <div className="text-xs text-muted-foreground flex flex-wrap gap-x-2">
            {by && <span>{__("Deliver by {0}", [by])}</span>}
            {order.ren_delivery_zone && <span>{order.ren_delivery_zone}</span>}
            <span>{fee ? __("Fee {0}", [formatCurrency(fee)]) : __("No fee")}</span>
            {order.ren_driver_name && (
              <span className="text-violet-300">
                {order.ren_delivered_at ? __("Delivered by {0}", [order.ren_driver_name]) : __("On the way with {0}", [order.ren_driver_name])}
              </span>
            )}
            {order.ren_guest_phone && (
              <a href={`tel:${order.ren_guest_phone}`} className="inline-flex items-center gap-1 text-sky-400">
                <Phone size={11} /> {order.ren_guest_phone}
              </a>
            )}
          </div>
        </div>
      </div>
      {missing > 0 && (
        <div className="mt-1.5 flex items-center gap-1.5 text-xs text-amber-400">
          <AlertTriangle size={13} />
          {__("{0} more to reach the {1} minimum", [formatCurrency(missing), formatCurrency(order.ren_delivery_minimum)])}
        </div>
      )}
    </div>
  );
}

export default DeliveryBanner;
