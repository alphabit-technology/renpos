import { FloorObject } from './FloorObject'
import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useState } from 'react';
import { getUrlParam, setUrlParams } from '@/utils/urlState';
import {OrderManager} from "@c/order/OrderManager.jsx"
import { ActionButton } from '@c/ui/ActionButton.jsx'

import { Settings, Trash2, Square, Circle, User, Users, Utensils, Clock } from 'lucide-react'
import { can } from '@/router/permissions';


/**
 * variant "plan": the object on the floor plan (drag / resize while editing).
 * variant "card": a card of the table list (phones, or the list view).
 */
export function Table({ table, onSelect, variant = "plan" }) {
  // reopened after a reload when the URL says this table was open (?table=…)
  const [orderOpen, setOrderOpenState] = useState(() => getUrlParam('table') === table.name);
  const setOrderOpen = (open) => {
    setOrderOpenState(open);
    setUrlParams({ table: open ? table.name : null, station: null, ...(open ? {} : { order: null }) });
  };
  const { editing, callMethod, REN } = useRestaurant()

  const handleSelect = async (e) => {
    editing && onSelect?.(e)
    if(!REN) return;

    if(!editing){
      if (REN.pos_profile == null) {
        frappe.throw(__("POS Profile is required to use Point-of-Sale"));
        return;
      }

      // Taking orders doesn't need a cash register: each cashier opens
      // their own register when charging (see PaymentPanel).
      setOrderOpen(true);
    }
  }

  const handleTableEdit = () => {
    MetaForm.edit('Ren Table', table.name, {
      fields: ['name', 'color', 'shape', 'no_of_seats', 'minimum_seating', 'description']
    });
  }

  const handleTableDelete = () => {
    callMethod("Ren Table", table.name, "delete")
  }

  return (
    <>
      <OrderManager
        table={table}
        open={orderOpen}
        onClose={() => setOrderOpen(false)}
        posProfile={REN.pos_profile?.name}
      />
    {variant === "card" ? <TableCard table={table} onOpen={handleSelect} /> :
    <FloorObject
      data={table}
      doctype="Ren Table"
      defaultColor="#22c55e"
      onSelect={handleSelect}
      renderOverlay={(data) => {
        if (data.reservation && !data.orders_count) {
          // held for an upcoming reservation
          return (
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <div className="rounded-md bg-amber-500/85 text-black px-1.5 py-0.5 text-[11px] font-bold leading-tight text-center max-w-[90%]">
                <div className="flex items-center justify-center gap-1"><Clock size={11} />{data.reservation.time}</div>
                <div className="truncate font-semibold">{data.reservation.guest} · {data.reservation.party_size}</div>
              </div>
            </div>
          )
        }
        const hasCustomer = data.customer || data.status === 'Reserved'
        if (!hasCustomer) return null
        return (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="rounded-full bg-red-600/40 flex items-center justify-center opacity-80" style={{ width: '65%', height: '65%' }}>
              <User className="text-gray-900/70 w-1/2 h-1/2" />
            </div>
          </div>
        )
      }}
      renderBadges={(data, editing) => (
        <>
          {data.no_of_seats && (
            <div className="absolute bottom-1 left-1/2 -translate-x-1/2 bg-zinc-800/60 text-white text-sm flex items-center gap-1 h-[24px] px-2 rounded-md shadow-md z-20 opacity-60">
              <Users size={14} />
              {data.no_of_seats}
            </div>
          )}
          {!editing && data.orders_count > 0 && (
            <div className="absolute top-0.5 left-1/2 -translate-x-1/2 bg-zinc-800/80 text-white text-md flex items-center gap-1 h-[24px] px-2 rounded-md shadow-md z-20">
              <Utensils size={13} />
              <span>{data.orders_count}</span>
            </div>
          )}
        </>
      )}
      actions={({ toggleShape, data }) => (
        <>
        {can("table.write") ?
          <ActionButton
            variant="primary"
            icon={Settings}
            onClick={handleTableEdit}
            className="rounded-none"
          /> : <></>}
        
        {can("table.delete") ?
          <ActionButton
            variant="primary"
            icon={Trash2}
            confirm
            onClick={handleTableDelete}
            className="rounded-none"
          /> : <></>}
          {can("table.write") ?
          <ActionButton
            variant="primary"
            icon={data.shape === 'Round' ? Square : Circle}
            onClick={(e) => { e.stopPropagation(); toggleShape() }}
            className="rounded-none"
          /> : <></>}
        </>
      )}
      />}
    </>
  )
}

export function tableState(t) {
  if (t.orders_count > 0) return t.current_user === frappe.session.user ? "mine" : "occupied"
  if (t.reservation) return "reserved"
  return "free"
}

const STATE_STYLE = {
  free:     { label: "Free",     dot: "#22c55e" },
  mine:     { label: "Yours",    dot: "#3b82f6" },
  occupied: { label: "Occupied", dot: "#ef4444" },
  reserved: { label: "Reserved", dot: "#f59e0b" },
}

function TableCard({ table: t, onOpen }) {
  const state = tableState(t)
  const st = STATE_STYLE[state]
  return (
    <button
      onClick={onOpen}
      className="relative flex flex-col justify-between gap-2 min-h-[104px] rounded-xl border border-border bg-card p-3 text-left
        hover:bg-accent/60 active:scale-[0.98] transition select-none overflow-hidden"
    >
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ backgroundColor: t.color || st.dot }} />
      <div className="flex items-start justify-between gap-2 pl-1">
        <span className="text-2xl font-semibold leading-none truncate">{t.description}</span>
        <span className="shrink-0 flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold"
          style={{ backgroundColor: `color-mix(in srgb, ${st.dot} 20%, transparent)` }}>
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: st.dot }} />
          {__(st.label)}
        </span>
      </div>
      <div className="pl-1 flex flex-col gap-1 text-xs text-muted-foreground">
        {state === "reserved" && t.reservation && (
          <span className="flex items-center gap-1 text-amber-400 font-medium truncate">
            <Clock size={12} /> {t.reservation.time} · {t.reservation.guest} · {t.reservation.party_size}
          </span>
        )}
        {t.orders_count > 0 && t.customer && <span className="truncate">{t.customer}</span>}
        <span className="flex items-center gap-3">
          {t.no_of_seats ? <span className="flex items-center gap-1"><Users size={13} />{t.no_of_seats}</span> : null}
          {t.orders_count > 0 && <span className="flex items-center gap-1 text-foreground"><Utensils size={13} />{t.orders_count}</span>}
        </span>
      </div>
    </button>
  )
}