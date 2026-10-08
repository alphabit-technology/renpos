import { useState, useEffect, useRef, useCallback } from "react";
import { UserCircle2, Clock, KeyRound, LogOut, MonitorSmartphone, Loader2, ShieldCheck, Store, Check } from "lucide-react";
import { MyAccess } from "./MyAccess.jsx";
import { useIsMobile } from "@c/order/hooks/useIsMobile";

/**
 * StaffMenu — the person at the terminal: their restaurant role, clock
 * in / out, their PIN (approvals and PIN login), switching user on a shared
 * terminal, and (managers) registering this device as a terminal.
 * The button shows the restaurant and POS Profile in use (tablet / desktop);
 * "My access" explains which profile, role and grants apply. People who
 * work several restaurants (branches, a call center) switch between them here.
 */

const STAFF = "renpos.api.staff";
const ACCESS = "renpos.api.access";
const TOKEN_KEY = "ren_terminal_token";

const call = (method, args = {}) => frappe.call({ method, args }).then((r) => r.message);

function terminalToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function StaffMenu({ access, posProfile, restaurant }) {
  const [open, setOpen] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const isMobile = useIsMobile();
  const [shift, setShift] = useState(null);
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);

  const loadShift = useCallback(() => call(`${STAFF}.get_shift`).then(setShift, () => {}), []);
  useEffect(() => { loadShift(); }, [loadShift]);

  const [branches, setBranches] = useState([]);
  useEffect(() => {
    if (open) call("renpos.api.restaurant.my_restaurants").then(setBranches, () => {});
  }, [open]);
  const switchBranch = (b) => {
    if (b.current) return;
    frappe.call({ method: "renpos.api.restaurant.switch_restaurant", args: { restaurant: b.restaurant },
      type: "POST" }).then(() => {
      // the floor, menu and register are the other restaurant's
      window.location.href = window.location.pathname;
    });
  };

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  const clock = async () => {
    setBusy(true);
    try { setShift(await call(`${STAFF}.${shift?.clocked_in ? "clock_out" : "clock_in"}`)); } catch { /* shown */ }
    setBusy(false);
  };

  const setPin = () => {
    const d = new frappe.ui.Dialog({
      title: __("My PIN"),
      fields: [
        { fieldtype: "HTML", options: `<p class="text-muted">${__("4 to 8 digits. Used to approve actions (if your role approves) and to log in on registered terminals.")}</p>` },
        { fieldtype: "Password", fieldname: "pin", label: __("New PIN"), reqd: 1 },
        { fieldtype: "Password", fieldname: "again", label: __("Repeat PIN"), reqd: 1 },
      ],
      primary_action_label: __("Save"),
      primary_action: async ({ pin, again }) => {
        if (pin !== again) { frappe.msgprint(__("The PINs don't match")); return; }
        await call(`${ACCESS}.set_pin`, { pin });
        d.hide();
        frappe.show_alert({ message: __("PIN saved"), indicator: "green" });
      },
    });
    d.show();
  };

  const switchUser = () => {
    const token = terminalToken();
    frappe.confirm(__("Log out and let someone else use this terminal?"), () => {
      frappe.call({ method: "logout" }).then(() => {
        window.location.href = token ? "/pos_login" : "/login";
      });
    });
  };

  const registerTerminal = () => {
    frappe.prompt({ fieldname: "name", fieldtype: "Data", label: __("Terminal name"), reqd: 1,
      default: __("Terminal") }, async ({ name }) => {
      const r = await call(`${STAFF}.register_terminal`, { terminal_name: name, pos_profile: posProfile });
      try { localStorage.setItem(TOKEN_KEY, r.token); } catch { /* private mode */ }
      frappe.show_alert({ message: __("This device is now terminal {0}", [r.terminal_name]), indicator: "green" });
    }, __("Register this terminal"), __("Register"));
  };

  const item = (Icon, label, onClick, extra = null) => (
    <button onClick={() => { setOpen(false); onClick(); }}
      className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent text-left">
      <Icon size={15} /> <span className="flex-1">{label}</span> {extra}
    </button>
  );

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} title={restaurant ? `${__("Staff")} · ${restaurant}` : __("Staff")}
        className={`h-full ${isMobile ? "w-12 justify-center" : "max-w-56 px-3 gap-2"} flex items-center border-l border-border text-muted-foreground hover:text-foreground hover:bg-primary/20 relative`}>
        <span className="relative shrink-0">
          <UserCircle2 size={19} />
          {shift?.clocked_in && <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-500" />}
        </span>
        {!isMobile && restaurant && (
          <span className="flex flex-col items-start min-w-0 leading-tight text-left">
            <span className="text-[11px] truncate max-w-44">{access?.manager ? __("Manager") : (access?.name || __("Staff"))}</span>
            <span className="text-xs font-semibold text-foreground truncate max-w-44">{restaurant}</span>
          </span>
        )}
      </button>
      {accessOpen && <MyAccess open onClose={() => setAccessOpen(false)} />}
      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 w-64 rounded-lg bg-popover border border-border shadow-xl py-1">
          <div className="px-3 py-2 border-b border-border">
            <p className="text-sm font-semibold truncate">{frappe.session.user_fullname || frappe.session.user}</p>
            <p className="text-xs text-muted-foreground">
              {access?.manager ? __("Manager") : (access?.name || __("Default role"))}
              {restaurant && <> · {restaurant}</>}
              {shift?.clocked_in && <> · {__("on since {0}", [String(shift.clock_in).substring(11, 16)])}</>}
            </p>
          </div>
          {branches.length > 1 && (
            <div className="py-1 border-b border-border">
              <p className="px-3 pt-1 pb-0.5 text-[11px] uppercase tracking-wide text-muted-foreground m-0">{__("Work at")}</p>
              {branches.map((b) => (
                <div key={b.restaurant}>
                  {item(Store, b.restaurant_name, () => switchBranch(b), b.current ? <Check size={14} /> : null)}
                </div>
              ))}
            </div>
          )}
          {item(ShieldCheck, __("My access"), () => setAccessOpen(true))}
          {item(Clock, shift?.clocked_in ? __("Clock out") : __("Clock in"), clock,
            busy ? <Loader2 size={13} className="animate-spin" /> : null)}
          {item(KeyRound, access?.has_pin ? __("Change my PIN") : __("Set my PIN"), setPin)}
          {item(LogOut, __("Switch user"), switchUser)}
          {!!access?.manager && item(MonitorSmartphone, __("Register this terminal"), registerTerminal)}
        </div>
      )}
    </div>
  );
}

export default StaffMenu;
