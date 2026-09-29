import { FloorObject } from './FloorObject'
import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useState, useCallback } from 'react';
import {DeskForm} from "@/components/utils/desk-form-class.jsx"
import {OrderManager} from "@c/order/OrderManager.jsx"
import { usePermission } from '@/router'
import { can } from '@/router'
import { ActionButton } from '@c/ui/ActionButton.jsx'
import { debounce } from 'es-toolkit'

import { Settings, Trash2, Square, Circle, User, Users, Utensils } from 'lucide-react'


export function Table({ table, onSelect, onDelete }) {
  const [orderOpen, setOrderOpen] = useState(false)
  const { canEdit, canDelete } = usePermission('table');
  const isRound = table.shape === 'Round'
  const { editing, currentTable, callMethod } = useRestaurant()

  const handleSelect = (e) => {
    editing && onSelect?.(e)
    !editing && setOrderOpen(true);
  }

  const handleTableEdit = () => {
    MetaForm.edit('REN Table', 'TABLE-001', {
      fields: ['table_name', 'room', 'capacity', 'status'],
      onSave: (doc) => refreshTables()
    });
   /*  DeskForm.open({
      doctype: "Ren Table",
      doc_name: table.name,
      form_name: "restaurant-table",
      title: __(`Update Table.${table.name}`),
      callback: (self) => self.hide(),
      field_properties: {
        type: { read_only: true },
        room: { read_only: true, hidden: true },
      },
    }); */
  }

  const updateAttr = useCallback(
    debounce((attr, value) => {
      callMethod(doctype, data.name, "set_attr", {
        args: { attr, value },
        freeze: false
      })
    }, 0),
    [data.name, doctype]
  )

  const handleTableDelete = () => {
    callMethod("Ren Table", table.name, "delete")
  }

  return (
    <>
    <OrderManager open={orderOpen} onClose={() => setOrderOpen(false)} />
    <FloorObject
      data={table}
      doctype="Ren Table"
      defaultColor="#22c55e"
      onSelect={handleSelect}
      onDelete={onDelete}
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
        {canEdit && (
          <ActionButton
            variant="primary"
            icon={Settings}
            onClick={handleTableEdit}
            className="rounded-none"
          />
        )}
          <ActionButton
            variant="primary"
            icon={Trash2}
            confirm
            onClick={handleTableDelete}
            className="rounded-none"
          />
          <ActionButton
            variant="primary"
            icon={isRound ? Square : Circle}
            onClick={(e) => { e.stopPropagation(); toggleShape() }}
            className="rounded-none"
          />
        </>
      )}
    />
    </>
  )
}