import { useCallback, useEffect, useState } from "react";
import { X, Loader2, Lock, Unlock, CheckCircle2, AlertTriangle, RotateCw } from "lucide-react";
import OrderAPI from "@c/order/api";

/**
 * RegisterPanel — the cashier's own cash register (shift).
 *
 *   closed    → enter the opening float per mode → open
 *   open      → live shift report (X): sales, taxes, voids, expected per mode
 *               → count the drawer → close (Z): POS Closing Entry with differences
 *   outdated  → shift from a previous day: must be closed first
 *   taken     → someone else's shift is open on this POS Profile (ERPNext v16:
 *               one open register per profile): they close it, or a manager
 *               counts and closes it here
 *   elsewhere → the cashier's own shift is open on another POS Profile
 *
 * Props: posProfile, onClose, onChanged(status)
 */

function money(v) {
  if (typeof window.format_currency === "function") return window.format_currency(v);
  return `$ ${(Math.round((parseFloat(v) || 0) * 100) / 100).toFixed(2)}`;
}

function fmtTime(v) {
  if (!v) return "";
  const d = new Date(String(v).replace(" ", "T"));
  return isNaN(d) ? String(v) : d.toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

function AmountInput({ label, value, onChange, hint, autoFocus }) {
  return (
    <label className="flex items-center gap-3 py-2">
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-medium truncate">{label}</span>
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </span>
      <input
        type="number" inputMode="decimal" min="0" step="0.01"
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="0.00"
        className="w-32 h-11 rounded-xl bg-background border border-border px-3 text-right text-base tabular-nums outline-none focus:border-ring"
      />
    </label>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="rounded-xl bg-muted/30 border border-border px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`text-lg font-bold tabular-nums ${tone || ""}`}>{value}</div>
    </div>
  );
}

export function RegisterPanel({ posProfile, onClose, onChanged }) {
  const [state, setState] = useState(null);       // get_register response
  const [view, setView] = useState("status");     // status | count | done
  const [amounts, setAmounts] = useState({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);     // close_register response

  const load = useCallback(async () => {
    try {
      setState(await OrderAPI.getRegister(posProfile));
    } catch {
      setState({ status: "error" });
    }
  }, [posProfile]);

  useEffect(() => { load(); }, [load]);

  const modes = state?.modes || [];
  const report = state?.report;

  const doOpen = async () => {
    setBusy(true);
    try {
      const balances = modes.map((m) => ({ mode_of_payment: m.mode_of_payment, opening_amount: parseFloat(amounts[m.mode_of_payment]) || 0 }));
      const st = await OrderAPI.openRegister(posProfile, balances);
      setState(st);
      setAmounts({});
      onChanged?.(st.status);
    } catch { /* server message already shown */ }
    setBusy(false);
  };

  const doClose = async () => {
    setBusy(true);
    try {
      const counted = (report?.payments || []).map((p) => ({
        mode_of_payment: p.mode_of_payment, closing_amount: parseFloat(amounts[p.mode_of_payment]) || 0,
      }));
      const other = state?.status === "taken" ? state.opening?.name : null;
      const res = await OrderAPI.closeRegister(posProfile, counted, 0, other);
      setResult(res);
      setView("done");
      onChanged?.("closed");
      if (other) {
        // their shift is closed: this cashier can open the register now
        setResult({ ...res, reopen: true });
      }
    } catch { /* server message already shown */ }
    setBusy(false);
  };

  const header = (icon, title, subtitle) => (
    <div className="shrink-0 flex items-start gap-3 px-5 pt-4 pb-3 border-b border-border">
      {icon}
      <div className="flex-1 min-w-0">
        <div className="text-lg font-semibold leading-tight">{title}</div>
        {subtitle && <div className="text-xs text-muted-foreground mt-0.5">{subtitle}</div>}
      </div>
      <button onClick={onClose} className="w-9 h-9 -mr-2 flex items-center justify-center rounded-xl text-muted-foreground hover:bg-muted" aria-label={__("Close")}>
        <X size={20} />
      </button>
    </div>
  );

  const footer = (children) => (
    <div className="shrink-0 px-5 pt-3 border-t border-border flex gap-2" style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}>
      {children}
    </div>
  );

  const primary = "flex-1 min-h-[48px] rounded-2xl font-semibold text-white disabled:opacity-40 flex items-center justify-center gap-2";

  let body;
  if (!state) {
    body = <div className="flex-1 flex items-center justify-center py-16 text-muted-foreground"><Loader2 className="animate-spin" /></div>;
  } else if (state.status === "no_permission" || state.status === "error") {
    body = (
      <>
        {header(<Lock className="text-amber-400 mt-1" size={22} />, __("Cash register"))}
        <div className="px-5 py-8 text-sm text-muted-foreground">
          {state.status === "error"
            ? __("The register could not be loaded.")
            : __("Your user can't take payments. Cashiers need the Accounts User and Sales Manager roles (or equivalent permissions).")}
        </div>
      </>
    );
  } else if ((state.status === "taken" || state.status === "elsewhere") && view === "status") {
    const o = state.opening || {};
    const taken = state.status === "taken";
    body = (
      <>
        {header(<AlertTriangle className="text-amber-400 mt-1" size={22} />,
          taken ? __("Register in use") : __("Your register is open elsewhere"),
          __("Since {0}", [fmtTime(o.period_start_date)]))}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-3 text-sm">
          {taken ? (
            <p className="m-0">
              {__("{0} has the register of {1} open. Only one register per POS Profile can be open at a time.", [o.user_name || o.user, o.pos_profile])}{" "}
              {state.can_close
                ? __("You can count and close their shift here, then open yours.")
                : __("Ask them or a manager to close it, or use another POS Profile.")}
            </p>
          ) : (
            <p className="m-0">{__("Your register of {0} is still open. Close it there before opening this one.", [o.pos_profile])}</p>
          )}
          {taken && state.can_close && report && (
            <div className="grid grid-cols-2 gap-2">
              <Stat label={__("Sales")} value={money(report.grand_total)} />
              <Stat label={__("Checks")} value={report.invoices ?? 0} />
            </div>
          )}
        </div>
        {footer(
          <>
            <button onClick={() => { setState(null); load(); }} className="min-h-[48px] w-12 rounded-2xl bg-muted flex items-center justify-center" aria-label={__("Refresh")}>
              <RotateCw size={18} />
            </button>
            {taken && state.can_close ? (
              <button onClick={() => { setAmounts({}); setView("count"); }} className={`${primary} bg-destructive`}>
                <Lock size={18} /> {__("Close {0}'s shift", [o.user_name || o.user])}
              </button>
            ) : (
              <button onClick={onClose} className={`${primary} bg-blue-600`}>{__("OK")}</button>
            )}
          </>
        )}
      </>
    );
  } else if (state.status === "closed") {
    body = (
      <>
        {header(<Lock className="text-amber-400 mt-1" size={22} />, __("Open your register"), __("Count the cash you start the shift with."))}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-2 divide-y divide-border">
          {modes.map((m, i) => (
            <AmountInput
              key={m.mode_of_payment}
              label={m.mode_of_payment}
              hint={m.type === "Cash" ? __("Opening float") : null}
              autoFocus={i === 0}
              value={amounts[m.mode_of_payment] ?? ""}
              onChange={(v) => setAmounts((a) => ({ ...a, [m.mode_of_payment]: v }))}
            />
          ))}
        </div>
        {footer(
          <button disabled={busy} onClick={doOpen} className={`${primary} bg-blue-600 active:bg-blue-700`}>
            {busy ? <Loader2 size={18} className="animate-spin" /> : <Unlock size={18} />} {__("Open register")}
          </button>
        )}
      </>
    );
  } else if (view === "done" && result) {
    const totalDiff = (result.reconciliation || []).reduce((s, r) => s + r.difference, 0);
    body = (
      <>
        {header(<CheckCircle2 className="text-emerald-400 mt-1" size={22} />, __("Register closed"), result.closing_entry)}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-3 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <Stat label={__("Sales")} value={money(result.report?.grand_total)} />
            <Stat label={__("Difference")} value={money(totalDiff)}
                  tone={Math.abs(totalDiff) < 0.005 ? "text-emerald-400" : "text-destructive"} />
          </div>
          <ReconTable rows={result.reconciliation} />
        </div>
        {footer(result.reopen ? (
          <button onClick={() => { setResult(null); setView("status"); setAmounts({}); setState(null); load(); }}
            className={`${primary} bg-blue-600`}>
            <Unlock size={18} /> {__("Open your register")}
          </button>
        ) : (
          <button onClick={onClose} className={`${primary} bg-blue-600`}>{__("Done")}</button>
        ))}
      </>
    );
  } else if (view === "count") {
    body = (
      <>
        {header(<Lock className="text-amber-400 mt-1" size={22} />, __("Count the drawer"), __("Enter what you actually have for each payment method."))}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-2 divide-y divide-border">
          {(report?.payments || []).map((p, i) => {
            const v = amounts[p.mode_of_payment];
            const diff = v === undefined || v === "" ? null : (parseFloat(v) || 0) - p.expected;
            return (
              <AmountInput
                key={p.mode_of_payment}
                label={p.mode_of_payment}
                autoFocus={i === 0}
                hint={
                  <>
                    {__("Expected")} {money(p.expected)}
                    {diff !== null && Math.abs(diff) >= 0.005 && (
                      <span className={diff > 0 ? "text-emerald-400" : "text-destructive"}> · {diff > 0 ? "+" : ""}{money(diff)}</span>
                    )}
                  </>
                }
                value={v ?? ""}
                onChange={(val) => setAmounts((a) => ({ ...a, [p.mode_of_payment]: val }))}
              />
            );
          })}
        </div>
        {footer(
          <>
            <button onClick={() => setView("status")} className="min-h-[48px] px-5 rounded-2xl bg-muted font-semibold">{__("Back")}</button>
            <button
              disabled={busy || (report?.payments || []).some((p) => amounts[p.mode_of_payment] === undefined || amounts[p.mode_of_payment] === "")}
              onClick={doClose}
              className={`${primary} bg-destructive`}
            >
              {busy ? <Loader2 size={18} className="animate-spin" /> : <Lock size={18} />} {__("Close register")}
            </button>
          </>
        )}
      </>
    );
  } else {
    const outdated = state.status === "outdated";
    body = (
      <>
        {header(
          outdated ? <AlertTriangle className="text-amber-400 mt-1" size={22} /> : <Unlock className="text-emerald-400 mt-1" size={22} />,
          outdated ? __("Shift from a previous day") : __("Register open"),
          __("Since {0}", [fmtTime(state.opening?.period_start_date)])
        )}
        <div className="flex-1 min-h-0 overflow-y-auto px-5 py-3 space-y-3">
          {outdated && (
            <p className="text-sm text-amber-400">{__("Close this shift to take payments again.")}</p>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Stat label={__("Sales")} value={money(report?.grand_total)} />
            <Stat label={__("Checks")} value={report?.invoices ?? 0} />
            <Stat label={__("Taxes")} value={money(report?.taxes)} />
            <Stat label={__("Voids")} value={`${report?.voids?.count || 0} · ${money(report?.voids?.amount || 0)}`} />
          </div>
          <ReconTable rows={(report?.payments || []).map((p) => ({ ...p, counted: null }))} />
        </div>
        {footer(
          <>
            <button onClick={() => { setState(null); load(); }} className="min-h-[48px] w-12 rounded-2xl bg-muted flex items-center justify-center" aria-label={__("Refresh")}>
              <RotateCw size={18} />
            </button>
            {state.receipt_printer && (
              <button
                onClick={() => OrderAPI.openDrawer(posProfile).then(() => frappe.show_alert({ message: __("Drawer opened"), indicator: "green" }), () => {})}
                className="min-h-[48px] px-4 rounded-2xl bg-muted font-semibold text-sm"
              >
                {__("Open drawer")}
              </button>
            )}
            <button onClick={() => { setAmounts({}); setView("count"); }} className={`${primary} bg-destructive`}>
              <Lock size={18} /> {__("Close register")}
            </button>
          </>
        )}
      </>
    );
  }

  return (
    <div className="fixed inset-0 z-[1050] flex items-end sm:items-center justify-center bg-black/60 animate-fade-in" onClick={onClose}>
      <div
        className="w-full sm:max-w-lg max-h-[92vh] flex flex-col bg-card text-card-foreground border border-border rounded-t-3xl sm:rounded-2xl shadow-2xl animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        {body}
      </div>
    </div>
  );
}

function ReconTable({ rows }) {
  const showCount = rows?.some((r) => r.counted !== null && r.counted !== undefined);
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-[11px] uppercase tracking-wide text-muted-foreground">
          <th className="text-left font-medium py-1">{__("Method")}</th>
          <th className="text-right font-medium py-1">{__("Opening")}</th>
          <th className="text-right font-medium py-1">{__("Expected")}</th>
          {showCount && <th className="text-right font-medium py-1">{__("Counted")}</th>}
          {showCount && <th className="text-right font-medium py-1">{__("Diff.")}</th>}
        </tr>
      </thead>
      <tbody>
        {(rows || []).map((r) => (
          <tr key={r.mode_of_payment} className="border-t border-border">
            <td className="py-2 font-medium">{r.mode_of_payment}</td>
            <td className="py-2 text-right tabular-nums text-muted-foreground">{money(r.opening)}</td>
            <td className="py-2 text-right tabular-nums">{money(r.expected)}</td>
            {showCount && <td className="py-2 text-right tabular-nums">{money(r.counted)}</td>}
            {showCount && (
              <td className={`py-2 text-right tabular-nums ${Math.abs(r.difference) < 0.005 ? "text-emerald-400" : "text-destructive"}`}>
                {money(r.difference)}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default RegisterPanel;
