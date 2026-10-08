import { useEffect, useState } from "react";
import { Store, Layers, DoorOpen, Square, ChefHat, Loader2 } from "lucide-react";
import Modal from "@c/ui/Modal";

/**
 * "My access": where this person is working (the restaurant and how it was
 * picked), their role and where it comes from, what they work there (Ren
 * Staff), and the POS Profiles they charge with. Every restaurant they work
 * at is listed with its own role and access.
 */

const CHOSEN = {
  chosen: "the one you picked in \"Work at\"",
  default: "your default restaurant",
  first: "the first restaurant you work at (none is marked as your default)",
  none: "you don't work at any restaurant yet",
};

const ROLE_SOURCE = {
  manager: "Restaurant Manager: full access",
  staff: "set for you in this restaurant (Ren Staff)",
  settings_default: "the default role in Ren Settings (none set for you here)",
  built_in: "built-in defaults (no role set anywhere)",
};

const ICON = { "Ren Floor": Layers, "Ren Room": DoorOpen, "Ren Table": Square, "Ren Station": ChefHat };
const KIND = { "Ren Floor": "Floor", "Ren Room": "Room", "Ren Table": "Table", "Ren Station": "Station" };

function Row({ label, children }) {
  return (
    <div className="flex gap-3 py-2 border-b border-border last:border-0">
      <span className="w-28 shrink-0 text-xs uppercase tracking-wide text-muted-foreground pt-0.5">{__(label)}</span>
      <div className="flex-1 min-w-0 text-sm">{children}</div>
    </div>
  );
}

export function MyAccess({ open, onClose }) {
  const [ctx, setCtx] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    frappe.call({ method: "renpos.api.access.my_context" })
      .then((r) => setCtx(r.message), () => setError(__("Couldn't load your access")));
  }, [open]);

  const loading = open && !ctx && !error;

  return (
    <Modal open={open} onClose={onClose} title={__("My access")} size="md">
      {loading && <div className="p-8 flex justify-center"><Loader2 className="animate-spin" /></div>}
      {error && <p className="p-6 text-sm text-red-400">{error}</p>}
      {ctx && (
        <div className="p-4 flex flex-col gap-4">
          <div className="rounded-lg border border-border px-3">
            <Row label="Restaurant">
              <span className="flex items-center gap-1.5 font-semibold">
                <Store size={14} /> {ctx.restaurant?.restaurant_name || ctx.restaurant?.name || __("Not set")}
              </span>
              {ctx.restaurant?.company && <span className="text-xs text-muted-foreground">{ctx.restaurant.company}</span>}
            </Row>
            <Row label="Why here">
              <p className="text-xs text-muted-foreground m-0">{__("In use because it's {0}.", [__(CHOSEN[ctx.chosen_by])])}</p>
            </Row>
            <Row label="Charges with">
              {ctx.billing_profiles.length ? (
                <span className="font-semibold">{ctx.billing_profiles.join(", ")}</span>
              ) : (
                <span className="text-muted-foreground">{__("No POS Profile: you take orders, a cashier charges them")}</span>
              )}
            </Row>
            <Row label="Role">
              <span className="font-semibold">{ctx.role.manager ? __("Manager") : (ctx.role.name || __("Default"))}</span>
              <p className="text-xs text-muted-foreground">{__(ROLE_SOURCE[ctx.role.source])}</p>
            </Row>
            <Row label="Can see">
              {ctx.whole_plan ? (
                <span>{__("The whole floor plan of the restaurant")}</span>
              ) : (
                <span className="tabular-nums">
                  {__("{0} floors · {1} rooms · {2} tables · {3} production centers",
                    [ctx.visible.floors, ctx.visible.rooms, ctx.visible.tables, ctx.visible.stations])}
                </span>
              )}
            </Row>
          </div>

          <div className="flex flex-col gap-2">
            <h4 className="text-xs uppercase tracking-wide text-muted-foreground">{__("Where you work")}</h4>
            {!ctx.staff.length && <p className="text-sm text-muted-foreground">{__("A manager adds you in Ren Staff.")}</p>}
            {ctx.staff.map((p) => (
              <div key={p.restaurant} className={`rounded-lg border p-3 ${p.active ? "border-primary/60 bg-primary/5" : "border-border"} ${p.enabled ? "" : "opacity-60"}`}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold">{p.restaurant_name}</span>
                  {p.active && <span className="text-[10px] font-bold uppercase rounded px-1.5 py-0.5 bg-primary text-primary-foreground">{__("In use")}</span>}
                  {!!p.default && <span className="text-[10px] font-bold uppercase rounded px-1.5 py-0.5 bg-foreground/10">{__("Default")}</span>}
                  {!p.enabled && <span className="text-[10px] font-bold uppercase rounded px-1.5 py-0.5 bg-red-500/20 text-red-400">{__("Disabled")}</span>}
                  <span className="ml-auto text-xs text-muted-foreground">{__("Role")}: {p.role || __("default")}</span>
                </div>
                {p.grants.length ? (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {p.grants.map((g) => {
                      const Icon = ICON[g.type] || Square;
                      return (
                        <span key={`${g.type}:${g.name}`} title={__(KIND[g.type] || g.type)}
                          className="flex items-center gap-1 text-xs rounded-md border border-border px-1.5 py-0.5">
                          <Icon size={12} className="text-muted-foreground" /> {g.label}
                        </span>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground mt-2">{__("No floors, rooms, tables or stations")}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  );
}
