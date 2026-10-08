import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Loader2, Truck, Check, MapPin, UserPlus, Clock } from "lucide-react";
import Modal from "@c/ui/Modal";
import { formatCurrency } from "@c/order/orderItems/calculator";

/**
 * DeliveryDialog — a delivery order taken by phone (api/delivery.py).
 *
 *   1. the phone number finds the customer and their addresses (or a new one)
 *   2. the address and its ZIP code
 *   3. the ZIP code picks the branch (the recommended one first); any other
 *      branch that delivers can be chosen by hand
 *   4. Create: the order is opened at the branch's delivery table (switching
 *      to that branch when it isn't the one in use)
 */

const API = "renpos.api.delivery";
const call = (method, args = {}, post = false) =>
  new Promise((resolve, reject) => frappe.call({
    method: `${API}.${method}`, args, type: post ? "POST" : "GET",
    callback: (r) => resolve(r.message), error: reject,
  }));

const zipOf = (v) => {
  const d = String(v || "").replace(/\D/g, "");
  return d.length >= 5 ? d.slice(0, 5) : "";
};

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">{label}</span>
      {children}
    </label>
  );
}

const input = "w-full h-11 px-3 rounded-lg border border-border bg-background text-foreground text-[15px] outline-none focus:border-primary";

export function DeliveryDialog({ open, onClose }) {
  const [phone, setPhone] = useState("");
  const [searching, setSearching] = useState(false);
  const [found, setFound] = useState(null); // null: not searched yet
  const [customer, setCustomer] = useState(null); // {customer, customer_name, addresses}
  const [newName, setNewName] = useState("");
  const [addressId, setAddressId] = useState(null); // an existing address, or null: typed
  const [line, setLine] = useState("");
  const [city, setCity] = useState("");
  const [zip, setZip] = useState("");
  const [saveAddress, setSaveAddress] = useState(true);
  const [quote, setQuote] = useState(null);
  const [quoting, setQuoting] = useState(false);
  const [branch, setBranch] = useState(null);
  const [notes, setNotes] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);
  const phoneRef = useRef(null);
  // the modal takes the focus when it opens: give it to the phone right after
  useEffect(() => {
    const t = setTimeout(() => phoneRef.current?.focus(), 60);
    return () => clearTimeout(t);
  }, []);

  const address = customer?.addresses?.find((a) => a.address === addressId) || null;
  const zipcode = zipOf(address ? address.zip : zip);

  // the ZIP code picks the branch
  useEffect(() => {
    if (!zipcode) { setQuote(null); setBranch(null); return undefined; }
    let alive = true;
    setQuoting(true);
    call("quote", { zipcode }).then((q) => {
      if (!alive) return;
      setQuote(q);
      setBranch(q.recommended || null);
    }).catch(() => alive && setQuote(null)).finally(() => alive && setQuoting(false));
    return () => { alive = false; };
  }, [zipcode]);

  const search = async (e) => {
    e?.preventDefault();
    if (phone.replace(/\D/g, "").length < 7) return;
    setSearching(true);
    try {
      const rows = await call("lookup", { phone });
      setFound(rows);
      pick(rows[0] || null);
    } finally {
      setSearching(false);
    }
  };

  const pick = (c) => {
    setCustomer(c);
    const first = c?.addresses?.[0];
    setAddressId(first ? first.address : null);
  };

  const chosen = useMemo(() => quote?.branches?.find((b) => b.restaurant === branch) || null, [quote, branch]);
  const typedOk = !address && line.trim();
  const canCreate = !creating && zipcode && branch && (address || typedOk) && (customer || newName.trim() || phone.trim());

  const create = async () => {
    if (!canCreate) return;
    setCreating(true);
    setError(null);
    try {
      const r = await call("new_order", {
        zipcode, restaurant: branch, phone: phone.trim(), notes: notes.trim() || undefined,
        customer: customer?.customer, customer_name: customer ? undefined : newName.trim() || undefined,
        address: address?.address, address_line: address ? undefined : line.trim(),
        city: address ? undefined : city.trim(), save_address: !address && saveAddress && (customer || newName.trim()) ? 1 : 0,
      }, true);
      if (r.switch) {
        await new Promise((resolve, reject) => frappe.call({
          method: "renpos.api.restaurant.switch_restaurant", args: { restaurant: r.restaurant },
          type: "POST", callback: resolve, error: reject,
        }));
      }
      const qs = new URLSearchParams({ floor: r.floor, room: r.room, table: r.table, order: r.order });
      window.location.href = `${window.location.pathname}?${qs}`;
    } catch {
      setError(null); // frappe already showed the message
      setCreating(false);
    }
  };

  const footer = (
    <>
      {chosen && (
        <span className="mr-auto text-sm text-muted-foreground">
          {chosen.restaurant_name}
          {quote?.mine && !quote.mine[chosen.restaurant] && <span className="text-amber-400"> · {__("you don't work there")}</span>}
        </span>
      )}
      <button onClick={onClose} className="h-10 px-4 rounded-lg border border-border hover:bg-muted">{__("Cancel")}</button>
      <button onClick={create} disabled={!canCreate}
        className="h-10 px-5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold flex items-center gap-2 disabled:opacity-40">
        {creating ? <Loader2 size={16} className="animate-spin" /> : <Truck size={16} />}
        {__("Create delivery order")}
      </button>
    </>
  );

  return (
    <Modal open={open} onClose={onClose} size="md" title={__("New delivery order")} footer={footer}>
      <div className="p-4 space-y-5">
        {/* 1. customer */}
        <section className="space-y-2">
          <form onSubmit={search} className="flex gap-2 items-end">
            <div className="flex-1">
              <Field label={__("Phone")}>
                <input value={phone} onChange={(e) => setPhone(e.target.value)} type="tel" ref={phoneRef}
                  placeholder="(617) 555-0100" className={input} />
              </Field>
            </div>
            <button type="submit" disabled={searching || phone.replace(/\D/g, "").length < 7}
              className="h-11 px-4 rounded-lg bg-secondary hover:bg-secondary/80 flex items-center gap-2 disabled:opacity-40">
              {searching ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />} {__("Find")}
            </button>
          </form>
          {found && (
            <div className="flex flex-wrap gap-2">
              {found.map((c) => (
                <button key={c.customer} onClick={() => pick(c)}
                  className={`h-9 px-3 rounded-full border text-sm flex items-center gap-1.5 ${
                    customer?.customer === c.customer ? "border-primary bg-primary/15" : "border-border hover:bg-muted"}`}>
                  {customer?.customer === c.customer && <Check size={14} />} {c.customer_name}
                </button>
              ))}
              <button onClick={() => pick(null)}
                className={`h-9 px-3 rounded-full border text-sm flex items-center gap-1.5 ${
                  !customer ? "border-primary bg-primary/15" : "border-border hover:bg-muted"}`}>
                <UserPlus size={14} /> {found.length ? __("Someone else") : __("New customer")}
              </button>
            </div>
          )}
          {found && !customer && (
            <Field label={__("Name")}>
              <input value={newName} onChange={(e) => setNewName(e.target.value)} className={input} />
            </Field>
          )}
        </section>

        {/* 2. address */}
        <section className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{__("Deliver to")}</div>
          {customer?.addresses?.length > 0 && (
            <div className="space-y-1.5">
              {customer.addresses.map((a) => (
                <button key={a.address} onClick={() => setAddressId(a.address)}
                  className={`w-full text-left px-3 py-2 rounded-lg border flex items-center gap-2 text-sm ${
                    addressId === a.address ? "border-primary bg-primary/10" : "border-border hover:bg-muted"}`}>
                  <MapPin size={15} className="shrink-0" /> <span className="flex-1">{a.line}</span>
                  {addressId === a.address && <Check size={15} />}
                </button>
              ))}
              <button onClick={() => setAddressId(null)}
                className={`w-full text-left px-3 py-2 rounded-lg border text-sm ${
                  !addressId ? "border-primary bg-primary/10" : "border-border hover:bg-muted"}`}>
                {__("Another address")}
              </button>
            </div>
          )}
          {!address && (
            <div className="grid grid-cols-6 gap-2">
              <div className="col-span-6">
                <input value={line} onChange={(e) => setLine(e.target.value)} placeholder={__("Street, number, apartment")} className={input} />
              </div>
              <div className="col-span-4">
                <input value={city} onChange={(e) => setCity(e.target.value)} placeholder={__("City")} className={input} />
              </div>
              <div className="col-span-2">
                <input value={zip} onChange={(e) => setZip(e.target.value)} inputMode="numeric" maxLength={10}
                  placeholder={__("ZIP")} className={input} />
              </div>
              {(customer || newName.trim()) && (
                <label className="col-span-6 flex items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" checked={saveAddress} onChange={(e) => setSaveAddress(e.target.checked)} />
                  {__("Save this address for the customer")}
                </label>
              )}
            </div>
          )}
        </section>

        {/* 3. branch */}
        <section className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-2">
            {__("Branch")} {quoting && <Loader2 size={13} className="animate-spin" />}
          </div>
          {!zipcode && <p className="text-sm text-muted-foreground m-0">{__("Enter the ZIP code to find the branch.")}</p>}
          {zipcode && quote && !quote.recommended && (
            <p className="text-sm text-amber-400 m-0">{__("No branch delivers to {0}. Choose one by hand.", [zipcode])}</p>
          )}
          {quote?.branches?.length > 0 && (
            <div className="grid sm:grid-cols-2 gap-2">
              {quote.branches.map((b) => (
                <button key={b.restaurant} onClick={() => setBranch(b.restaurant)}
                  className={`text-left px-3 py-2.5 rounded-lg border ${
                    branch === b.restaurant ? "border-primary bg-primary/10" : "border-border hover:bg-muted"} ${
                    b.in_zone ? "" : "opacity-70"}`}>
                  <div className="font-semibold text-sm flex items-center gap-1.5">
                    {branch === b.restaurant && <Check size={14} />} {b.restaurant_name}
                    {b.restaurant === quote.recommended && (
                      <span className="ml-auto text-[10px] uppercase font-bold text-emerald-400">{__("Recommended")}</span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5 flex flex-wrap gap-x-2">
                    {b.in_zone ? (
                      <>
                        <span>{b.zone}</span>
                        <span>{b.fee ? __("Fee {0}", [formatCurrency(b.fee)]) : __("No fee")}</span>
                        {b.minimum > 0 && <span>{__("Min. {0}", [formatCurrency(b.minimum)])}</span>}
                        <span className="inline-flex items-center gap-0.5"><Clock size={11} /> {b.eta_minutes} min</span>
                      </>
                    ) : <span>{__("Outside its zones: no fee")}</span>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </section>

        <Field label={__("Notes for the kitchen and the driver")}>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} maxLength={300}
            className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground text-[15px] outline-none focus:border-primary resize-none" />
        </Field>
        {error && <p className="text-sm text-red-400 m-0">{error}</p>}
      </div>
    </Modal>
  );
}

export default DeliveryDialog;
