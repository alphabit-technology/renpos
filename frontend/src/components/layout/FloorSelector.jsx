import { useState, useRef, useEffect } from 'react'
import { ChevronRight, Plus } from 'lucide-react'
import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { useFloors } from "@/context/FloorsContext.jsx"

export function FloorSelector() {
  const { floors, currentFloor, setCurrentFloor, loadFloors } = useFloors()
  const [open, setOpen] = useState(false)
  const selectRef = useRef(null)
  const containerRef = useRef(null)

  useEffect(() => {
    if (open && selectRef.current) {
      selectRef.current.focus()
      try { selectRef.current.showPicker() } catch (e) {}
    }
  }, [open])

  const handleBlur = (e) => {
    if (containerRef.current?.contains(e.relatedTarget)) return
    setOpen(false)
  }

  const handleChange = (e) => {
    const floor = floors.find(f => f.name === e.target.value)
    if (floor) setCurrentFloor(floor)
    setOpen(false)
  }

  const addFloor = () => {
    setOpen(false)
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
              company: frappe.defaults.get_user_default('company')
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

  /* useEffect(() => {
    loadFloors()
  }, []) */

  if (!open) {
    return (
      <div className="flex items-center gap-1">
        <button
          onClick={() => floors.length > 0 ? setOpen(true) : addFloor()}
          className="p-1.5 rounded-md hover:bg-foreground/10 transition-colors"
          title={currentFloor?.description || 'Select floor'}
        >
          <ChevronRight size={18} />
        </button>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="flex items-center gap-1">
      <select
        ref={selectRef}
        value={currentFloor?.name || ''}
        onChange={handleChange}
        onBlur={handleBlur}
        className="h-8 px-2 rounded-md bg-background border border-foreground/20 text-sm outline-none"
      >
        {floors.map(floor => (
          <option key={floor.name} value={floor.name}>
            {floor.description}
          </option>
        ))}
      </select>
      <button
        onClick={addFloor}
        className="p-1.5 rounded-md hover:bg-foreground/10 transition-colors"
        title="Add floor"
      >
        <Plus size={16} />
      </button>
    </div>
  )
}