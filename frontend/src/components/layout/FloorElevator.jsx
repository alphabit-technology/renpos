import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useFloors } from '@/context/FloorsContext.jsx'
import { useRestaurant } from '@/context/RestaurantContext'
import { PlusIcon, ChevronLeft, ChevronRight } from 'lucide-react'
import {can} from "@/router/permissions"

export function FloorElevator() {
  const { floors, currentFloor, setCurrentFloor, loadFloors } = useFloors()
  const [expanded, setExpanded] = useState(false)
  const {restaurant} = useRestaurant()

  const addFloor = () => {
    const d = new frappe.ui.Dialog({
      title: 'New Floor',
      fields: [
        { fieldname: 'description', fieldtype: 'Data', label: 'Floor Name', reqd: 1 }
      ],
      primary_action_label: 'Create',
      primary_action(values) {
        frappe.call({
          method: 'frappe.client.insert',
          args: {
            doc: {
              doctype: 'Ren Floor',
              description: values.description,
              restaurant: restaurant.name
            }
          },
          callback: () => {
            d.hide()
            loadFloors()
          }
        })
      }
    })
    d.show()
  }

  if (!floors || floors.length === 0) {
    return (can("floor.create") ? (
      <div className="flex flex-col items-center justify-center w-12 bg-card border-r border-border">
        <button
          onClick={addFloor}
          className="p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
          title="Add floor"
        >
          <Plus size={16} />
        </button>
      </div>
    ) : <></>)
  }

  return (
    <div
      className={`
        flex flex-col h-full bg-card border-r border-border
        transition-[width] duration-200 ease-out overflow-hidden shrink-0 relative
        ${expanded ? 'w-40' : 'w-12'}
      `}
    >
      {/* Track line */}
      <div className="absolute left-[23px] top-2 bottom-17 w-0.5 bg-border rounded-full z-0" />

      {/* Floor buttons */}
      <div className="flex-1 flex flex-col justify-center gap-1 py-3 relative z-[1]">
        {floors.map((floor, i) => {
          const active = currentFloor?.name === floor.name
          const floorNumber = floors.length - i

          return (
            <button
              key={floor.name}
              onClick={() => setCurrentFloor(floor)}
              className={`
                group flex items-center gap-2.5 min-h-[44px] border-l-[3px] transition-all duration-150
                ${expanded ? 'px-3' : 'px-0 justify-center'}
                ${active
                  ? 'border-l-primary bg-accent'
                  : 'border-l-transparent hover:bg-accent/50'
                }
              `}
            >
              {/* Floor number badge */}
              <div
                className={`
                  w-7 h-7 rounded-md flex items-center justify-center shrink-0
                  text-xs font-bold font-mono transition-all duration-150 border
                  ${active
                    ? 'bg-primary/15 text-red-500 border-primary/30'
                    : 'bg-muted text-muted-foreground border-border group-hover:text-foreground'
                  }
                `}
              >
                {floorNumber}
              </div>

              {/* Expanded: floor name */}
              {expanded && (
                <span
                  className={`
                    text-xs font-semibold truncate max-w-[80px] transition-opacity duration-150
                    ${active ? 'text-foreground' : 'text-muted-foreground group-hover:text-foreground'}
                  `}
                >
                  {floor.description}
                </span>
              )}

              {/* Collapsed: occupied dot */}
              {!expanded && floor.rooms?.some(r => r.tables?.some(t => t.status === 'occupied')) && (
                <div className="absolute top-1.5 right-1 w-1.5 h-1.5 rounded-full bg-destructive shadow-[0_0_6px] shadow-destructive/40" />
              )}
            </button>
          )
        })}
      </div>

      {/* Bottom actions */}
      <div className="flex flex-col border-t border-border shrink-0">
        {can("floor.create") ?
        <button
          onClick={addFloor}
          className={`
            flex items-center gap-2 h-9 transition-colors
            text-muted-foreground hover:text-foreground hover:bg-accent/50
            ${expanded ? 'px-3 justify-start' : 'justify-center'}
          `}
          title="Add floor"
        >
          <Plus size={14} />
          {expanded && <span className="text-[10px] font-medium">Add Floor</span>}
        </button> : <></>
        }
        <button
          onClick={() => setExpanded(!expanded)}
          className="h-8 flex items-center justify-center border-t border-border text-muted-foreground hover:text-foreground transition-colors text-xs"
        >
          {expanded ? <ChevronLeft size={14}/> : <ChevronRight size={14}/>}
        </button>
      </div>
    </div>
  )
}