import { FloorObject } from './FloorObject'
import { Settings, Trash2, Square, Circle, User, Users, Utensils } from 'lucide-react'

import { ActionButton } from '@c/ui/ActionButton.jsx'
import { useRestaurant } from '@/context/RestaurantContext.jsx'
import { useState } from 'react'
import { KitchenView } from '@c/kitchen/KitchenView.jsx'

export function Station({ station, onSelect, onDelete }) {
  const { callMethod, editing } = useRestaurant()
  const [kitchenOpen, setKitchenOpen] = useState(false)

  // Editing the floor: select/move the station. Otherwise: open its kitchen screen.
  const handleSelect = (e) => {
    if (editing) onSelect?.(e)
    else setKitchenOpen(true)
  }
  const handleStationEdit = () => {
    /* DeskForm.open({
      doctype: "Ren Station",
      doc_name: station.name,
      form_name: "restaurant-production-center",
      title: __(`Update Station`),
      callback: (self) => self.hide(),
      field_properties: {
        type: { read_only: true },
        room: { read_only: true, hidden: true },
      },
    }); */
    /* console.log(["Table Edit"])
    MetaForm.edit('Ren Table', table.name, {
      fields: ['table_name', 'room', 'capacity', 'status'],
      allFields:true,
      onSave: (doc) => refreshTables()
    }); */
    MetaForm.open('Ren Station', station.name, {
      fieldProperties: {
        floor: { read_only: 1, hidden: 1 }
      },
    })

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

  const handleStationDelete = () => {
    callMethod("Ren Station", station.name, "delete")
  }

  return (
    <>
    {kitchenOpen && <KitchenView open station={station} onClose={() => setKitchenOpen(false)} />}
    <FloorObject
      data={station}
      doctype="Ren Station"
      defaultColor="#9f4c5c"
      onSelect={handleSelect}
      onDelete={onDelete}
      allowShape={false}
      renderBadges={(data, editing) => (
        <>
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
          <ActionButton
            variant="primary"
            icon={Settings}
            onClick={handleStationEdit}
            className="rounded-none"
          />
        
          <ActionButton
            variant="primary"
            icon={Trash2}
            confirm
            onClick={handleStationDelete}
            className="rounded-none"
          />
        </>
      )}
    />
    </>
  )
}
