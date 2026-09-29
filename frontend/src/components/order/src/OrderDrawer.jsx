import { useState, useCallback, useEffect, useRef } from "react";
import { X, Users, User, StickyNote, UtensilsCrossed, Truck } from "lucide-react";

/**
 * OrderDrawer — Right-side drawer for editing Table Order details.
 *
 * Fields: customer, dinners, notes, is_delivery
 * Saves each field immediately on blur/change via frappe.client.set_value.
 *
 * Props:
 *   @param {boolean} open
 *   @param {function} onClose
 *   @param {object} order - Table Order doc (at minimum: name, customer, customer_name, dinners, notes, is_delivery)
 *   @param {function} onUpdate - called after a field is saved, receives (fieldname, value)
 */
export function OrderDrawer({ open, onClose, order, onUpdate }) {
  if (!open || !order) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      {/* Drawer panel */}
      <div className="relative w-80 max-w-[85vw] h-full bg-card border-l border-border
                      shadow-2xl flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div>
            <h3 className="text-sm font-semibold text-card-foreground">
              {__("Order Details")}
            </h3>
            <span className="text-[10px] text-muted-foreground">
              {order.name}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground"
          >
            <X size={16} />
          </button>
        </div>

        {/* Fields */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
          {/* Customer */}
          <CustomerField
            orderName={order.name}
            value={order.customer || ""}
            displayName={order.customer_name || ""}
            onUpdate={onUpdate}
          />

          {/* Dinners */}
          <DinnersField
            orderName={order.name}
            value={order.dinners || 0}
            onUpdate={onUpdate}
          />

          {/* Service Type */}
          <ServiceTypeField
            orderName={order.name}
            isDelivery={order.is_delivery || 0}
            onUpdate={onUpdate}
          />

          {/* Notes */}
          <NotesField
            orderName={order.name}
            value={order.notes || ""}
            onUpdate={onUpdate}
          />
        </div>

        {/* Footer info */}
        <div className="px-4 py-3 border-t border-border">
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>{order.room_description || order.room}</span>
            <span>{order.table_description || order.table}</span>
          </div>
          {order.status && (
            <div className="mt-1">
              <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-accent text-accent-foreground">
                {order.status}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Field Components ───────────────────────────

function saveField(orderName, fieldname, value) {
  return new Promise((resolve, reject) => {
    frappe.call({
      method: "frappe.client.set_value",
      args: {
        doctype: "Table Order",
        name: orderName,
        fieldname,
        value,
      },
      callback: (r) => resolve(r?.message),
      error: reject,
    });
  });
}

function CustomerField({ orderName, value, displayName, onUpdate }) {
  const inputRef = useRef(null);

  const openCustomerPicker = useCallback(() => {
    // Use Frappe's built-in Link selector
    new frappe.ui.form.LinkSelector({
      doctype: "Customer",
      fieldname: "customer",
      target: { doctype: "Table Order" },
      callback: (value) => {
        if (value) {
          saveField(orderName, "customer", value).then(() => {
            onUpdate?.("customer", value);
          });
        }
      },
    });
  }, [orderName, onUpdate]);

  const handleClear = useCallback(() => {
    saveField(orderName, "customer", "").then(() => {
      onUpdate?.("customer", "");
    });
  }, [orderName, onUpdate]);

  return (
    <FieldWrapper icon={User} label={__("Customer")}>
      <div className="flex items-center gap-2">
        <button
          onClick={openCustomerPicker}
          className="flex-1 text-left px-2.5 py-2 text-xs rounded-lg bg-muted/50 border border-border
                     text-card-foreground hover:bg-muted transition-colors truncate"
        >
          {displayName || value || (
            <span className="text-muted-foreground">{__("Select customer...")}</span>
          )}
        </button>
        {value && (
          <button
            onClick={handleClear}
            className="p-1 rounded hover:bg-muted text-muted-foreground transition-colors"
          >
            <X size={12} />
          </button>
        )}
      </div>
    </FieldWrapper>
  );
}

function DinnersField({ orderName, value, onUpdate }) {
  const [local, setLocal] = useState(value);

  useEffect(() => { setLocal(value); }, [value]);

  const handleBlur = useCallback(() => {
    const num = parseInt(local, 10) || 0;
    if (num !== value) {
      saveField(orderName, "dinners", num).then(() => {
        onUpdate?.("dinners", num);
      });
    }
  }, [local, value, orderName, onUpdate]);

  return (
    <FieldWrapper icon={Users} label={__("Guests")}>
      <div className="flex items-center gap-2">
        <button
          onClick={() => {
            const n = Math.max(0, (parseInt(local, 10) || 0) - 1);
            setLocal(n);
            saveField(orderName, "dinners", n).then(() => onUpdate?.("dinners", n));
          }}
          className="w-8 h-8 rounded-lg bg-muted/50 border border-border flex items-center justify-center
                     text-card-foreground hover:bg-muted transition-colors text-sm font-bold"
        >
          −
        </button>
        <input
          type="number"
          min="0"
          value={local}
          onChange={(e) => setLocal(e.target.value)}
          onBlur={handleBlur}
          className="w-14 text-center px-2 py-1.5 text-xs font-medium rounded-lg bg-muted/50 border border-border
                     text-card-foreground focus:outline-none focus:ring-1 focus:ring-ring/40
                     [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none
                     [&::-webkit-inner-spin-button]:appearance-none"
        />
        <button
          onClick={() => {
            const n = (parseInt(local, 10) || 0) + 1;
            setLocal(n);
            saveField(orderName, "dinners", n).then(() => onUpdate?.("dinners", n));
          }}
          className="w-8 h-8 rounded-lg bg-muted/50 border border-border flex items-center justify-center
                     text-card-foreground hover:bg-muted transition-colors text-sm font-bold"
        >
          +
        </button>
      </div>
    </FieldWrapper>
  );
}

function ServiceTypeField({ orderName, isDelivery, onUpdate }) {
  const handleChange = useCallback((delivery) => {
    saveField(orderName, "is_delivery", delivery ? 1 : 0).then(() => {
      onUpdate?.("is_delivery", delivery ? 1 : 0);
    });
  }, [orderName, onUpdate]);

  return (
    <FieldWrapper icon={UtensilsCrossed} label={__("Service Type")}>
      <div className="flex gap-2">
        <ToggleChip
          active={!isDelivery}
          onClick={() => handleChange(false)}
          icon={UtensilsCrossed}
          label={__("Dine-in")}
        />
        <ToggleChip
          active={!!isDelivery}
          onClick={() => handleChange(true)}
          icon={Truck}
          label={__("Delivery")}
        />
      </div>
    </FieldWrapper>
  );
}

function NotesField({ orderName, value, onUpdate }) {
  const [local, setLocal] = useState(value);

  useEffect(() => { setLocal(value); }, [value]);

  const handleBlur = useCallback(() => {
    if (local !== value) {
      saveField(orderName, "notes", local).then(() => {
        onUpdate?.("notes", local);
      });
    }
  }, [local, value, orderName, onUpdate]);

  return (
    <FieldWrapper icon={StickyNote} label={__("Notes")}>
      <textarea
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={handleBlur}
        rows={3}
        placeholder={__("Add notes...")}
        className="w-full px-2.5 py-2 text-xs rounded-lg bg-muted/50 border border-border resize-none
                   text-card-foreground placeholder:text-muted-foreground
                   focus:outline-none focus:ring-1 focus:ring-ring/40"
      />
    </FieldWrapper>
  );
}

// ─── Shared UI ──────────────────────────────────

function FieldWrapper({ icon: Icon, label, children }) {
  return (
    <div>
      <label className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground mb-1.5">
        <Icon size={12} />
        {label}
      </label>
      {children}
    </div>
  );
}

function ToggleChip({ active, onClick, icon: Icon, label }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg transition-all ${
        active
          ? "bg-accent text-accent-foreground ring-1 ring-ring/30"
          : "bg-muted/30 text-muted-foreground hover:bg-muted/50"
      }`}
    >
      <Icon size={12} />
      {label}
    </button>
  );
}

export default OrderDrawer;