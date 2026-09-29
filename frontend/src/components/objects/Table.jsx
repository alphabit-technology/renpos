import { FloorObject } from './FloorObject'
import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useState, useCallback } from 'react';
import {OrderManager} from "@c/order/OrderManager.jsx"
import {OrderManagerExample} from "@c/order/OrderExample.jsx"
import { ActionButton } from '@c/ui/ActionButton.jsx'
import { debounce } from 'es-toolkit'

import { Settings, Trash2, Square, Circle, User, Users, Utensils } from 'lucide-react'
import { can, canOpenOrderManage } from '@/router/permissions';
import { useRooms } from '@/context/RoomsContext.jsx';


export function Table({ table, onSelect }) {
  const [orderOpen, setOrderOpen] = useState(false);
  const isRound = table.shape === 'Round'
  const { editing, currentTable, callMethod, RM, POS, handleSetPOS, checkOpeningEntry } = useRestaurant()

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

      if(!await checkOpeningEntry()){
        return
      }

      const _open = () => {
        setOrderOpen(true);
      }
        if (RM.navigate_table) {
          RM.navigate_table = null;
          _open();
          return;
        }

        return _open()

        /* if (hasCustomer()) {
          _open();
          return
        } */

        setTimeout(() => {
          const dialog = new frappe.ui.Dialog({
            title: __('Table {0}', [table.description]),
            fields: [
              {
                fieldtype: 'Column Break'
              },
              {
                fieldtype: 'Link', label: __('Customer'),
                fieldname: "customer",
                options: "Customer",
                default: table?.customer,
                //get_query: () => {
                //    return {
                //        filters: {
                //            "customer_group": RM.pos_profile.customer_group
                //        }
                //    }
                //}
              },
              {
                fieldtype: 'HTML', fieldname: "reservation"
              },
              {
                fieldtype: 'Section Break'
              },
              {
                fieldtype: 'Button', fieldname: "open_table", label: __('Open Table'), primary: 1,
                click: () => {
                  if (dialog.get_value("customer") === "") {
                    frappe.msgprint(__("Please select a customer to open the table"));
                    return;
                  }

                  frappe.db.set_value("Ren Table", table.name, "customer", dialog.get_value("customer")).then(() => {
                    dialog.hide();
                    _open();
                  });
                }
              }
            ]
          });

          Object.entries({ width: "100%", height: "50px", fontSize: "20px", fontWeight: "400" }).forEach(([key, value]) => {
            dialog.get_field("open_table").input.style[key] = value;
          });

          dialog.show();

          //Reservation.render(this.data.name, dialog.get_field("reservation").$wrapper);
        }, 0)
    }
  }

  const handleTableEdit = () => {
    MetaForm.edit('Ren Table', table.name, {
      fields: ['name', 'color', 'shape', 'no_of_seats', 'minimum_seating', 'description']
    });
  }

  const updateAttr = useCallback(
    debounce((attr, value) => {
      callMethod("Ren Table", data.name, "set_attr", {
        args: { attr, value },
        freeze: false
      })
    }, 0),
    [table.name]
  )

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
      actions={() => (
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
            icon={isRound ? Square : Circle}
            onClick={(e) => { e.stopPropagation(); toggleShape() }}
            className="rounded-none"
          /> : <></>}
        </>
      )}
      />
    </>
  )
}