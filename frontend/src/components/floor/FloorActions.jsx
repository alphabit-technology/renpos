import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { Plus, Pencil, Trash2, Menu, Landmark, CheckIcon, CalendarDays } from 'lucide-react'
import { ActionButton } from '@c/ui/ActionButton.jsx'
import { useRooms } from '@/context/RoomsContext.jsx'
import { can } from "@/router/permissions"

export function AddTableButton({ onAdd }) {
  const { editing } = useRestaurant()
  if (!can("table.create")) return null
  if (!editing) return null
  
  return (
    <ActionButton
      icon={Plus}
      label="Table"
      onClick={() => onAdd?.('Table')}
    />
  )
}

export function AddProductionCenterButton({ onAdd }) {
  const { editing } = useRestaurant()
  if (!can("station.create")) return null
  if (!editing) return null
  
  return (
    <ActionButton
      icon={Plus}
      label="Station"
      onClick={() => onAdd?.('Production Center')}
    />
  )
}

export function EditRoomButton({ onClick }) {
  const { editing } = useRestaurant()
  const {currentRoom} = useRooms();
  if (!can("room.write")) return null
  if (!editing || !currentRoom) return null
  
  return (
    <ActionButton
      icon={Pencil}
      label="Edit"
      onClick={onClick}
    />
  )
}

export function DeleteRoomButton({ onClick }) {
  const {editing } = useRestaurant()
  const {currentRoom} = useRooms();
  if (!can("room.delete")) return null
  if (!editing || !currentRoom) return null
  
  return (
    <ActionButton
      icon={Trash2}
      label="Delete"
      confirmLabel="Confirm"
      confirm
      confirmVariant="destructive"
      onClick={onClick}
    />
  )
}

export function MenuButton({ onClick }) {
  if (can("menu.write") || can("menu.create")) {
    return (
      <ActionButton
        icon={Menu}
        label="Menu"
        onClick={onClick}
      />
    )
  }
  return null
}

export function BookingButton({onClick}){
  return (
    <ActionButton
      icon={CalendarDays}
      label=""
      onClick={onClick}
    />
  )
}

export default ActionButton