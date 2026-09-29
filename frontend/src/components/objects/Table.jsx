import { FloorObject } from './FloorObject'
import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useState } from 'react';
import {OrderManager} from "@c/order/OrderManager.jsx"
import { ActionButton } from '@c/ui/ActionButton.jsx'

import { Settings, Trash2, Square, Circle, User, Users, Utensils } from 'lucide-react'
import { can, canOpenOrderManage } from '@/router/permissions';
import { useRooms } from '@/context/RoomsContext.jsx';


export function Table({ table, onSelect }) {
  const [orderOpen, setOrderOpen] = useState(false);
  const { editing, callMethod, RM } = useRestaurant()

  const handleSelect = async (e) => {
    editing && onSelect?.(e)
    if(!RM) return;

    if(!editing){
      if (RM.pos_profile == null) {
        frappe.throw(__("POS Profile is required to use Point-of-Sale"));
        return;
      }

      /* if(!POS){
        handleSetPOS();
        return;
      } */

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
      {canOpenOrderManage(table) ? <OrderManager
        table={table}
        open={orderOpen}
        onClose={() => setOrderOpen(false)} 
        posProfile={RM.pos_profile?.name}
      /> : 
    <></>}
    <FloorObject
      data={table}
      doctype="Ren Table"
      defaultColor="#22c55e"
      onSelect={handleSelect}
      renderOverlay={(data) => {
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
      />
    </>
  )
}