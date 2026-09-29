import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { Plus, Pencil, Trash2, Menu, Landmark, Check } from 'lucide-react'

function ActionButton({ 
  icon: Icon, 
  label, 
  onClick, 
  variant = 'default', 
  doubleClick = false,
  className = ''
}) {
  const handleClick = doubleClick ? undefined : onClick
  const handleDoubleClick = doubleClick ? onClick : undefined

  const variants = {
    default: 'rm-btn rm-btn-default',
    danger: 'rm-btn rm-btn-danger',
  }

  return (
    <button
      className={`${variants[variant]} ${className}`}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
    >
      {Icon && <Icon size={16} />}
      {label && <span>{label}</span>}
    </button>
  )
}

export function AddTableButton({ onAdd }) {
  const { editing } = useRestaurant()
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
  if (!editing) return null
  
  return (
    <ActionButton
      icon={Landmark}
      label="P Center"
      onClick={() => onAdd?.('Production Center')}
    />
  )
}

export function CheckInButton({ onCheckIn }) {
  return (
    <ActionButton
      icon={Check}
      label="Check In"
      variant="danger"
      onClick={onCheckIn}
    />
  )
}

export function EditRoomButton({ onEdit }) {
  const { currentRoom, editing } = useRestaurant()
  if (!editing || !currentRoom) return null
  
  return (
    <ActionButton
      icon={Pencil}
      label="Edit"
      onClick={() => onEdit?.(currentRoom)}
    />
  )
}

export function DeleteRoomButton({ onDelete }) {
  const { currentRoom, editing } = useRestaurant()
  if (!editing || !currentRoom) return null
  
  return (
    <ActionButton
      icon={Trash2}
      label="Delete"
      onClick={() => onDelete?.(currentRoom)}
      doubleClick={true}
    />
  )
}

export function MenuButton({ onOpenMenu }) {
  const { editing } = useRestaurant()
  if (!editing) return null

  return (
    <ActionButton
      icon={Menu}
      label="Menu"
      onClick={onOpenMenu}
    />
  )
}

export default ActionButton