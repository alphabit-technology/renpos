import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { Pencil, Plus, Landmark, ChevronDown, Check, Truck } from 'lucide-react'
import { DeliveryDialog } from '@c/delivery/DeliveryDialog.jsx'
import { useState, useEffect, useRef } from 'react'
import { useIsMobile } from '@c/order/hooks/useIsMobile'
import { RegisterPanel } from '@c/register/RegisterPanel.jsx'
import{ useRooms } from "@/context/RoomsContext.jsx"
import { useFloors } from '../../context/FloorsContext.jsx'
import {can, generalCustomAccess} from "@/router/permissions"
import { StaffMenu } from "@c/staff/StaffMenu.jsx"

export function RoomsBar() {
  const { editing, setEditing, ready, REN } = useRestaurant();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [deliveryOpen, setDeliveryOpen] = useState(false);
  const {rooms, addRoom, currentRoom, setCurrentRoom} = useRooms();
  const {currentFloor} = useFloors()
  const isMobile = useIsMobile()

  if(!ready || !currentFloor) return ;

  const renderRooms = () => {
    if(!rooms || rooms.length == 0) return (
      <div className="flex-1 flex items-stretch overflow-x-auto">
        <div
          className={`relative flex-1 min-w-[120px] flex items-center justify-center px-4 py-3 text-center font-medium transition-colors border-r border-muted`}
        >
          <span className="truncate">No Rooms</span>
        </div>
      </div>
    )

    return (
      <div className="flex-1 flex items-stretch overflow-x-auto">
        {rooms.map((room) => (
          <button
            key={room.name}
            onClick={() => setCurrentRoom(room)}
            className={`relative flex-1 ${isMobile ? 'min-w-[84px] px-3' : 'min-w-[120px] px-4'} flex items-center justify-center py-3 text-center font-medium transition-colors border-r border-muted ${
              currentRoom?.name === room.name
                ? 'bg-foreground/20'
                : 'hover:bg-gray-700/40'
            }`}
          >
            <span className="truncate">{room.description}</span>
            
            {room.orders_count > 0 && (
              <span className="absolute top-1 right-1 bg-yellow-500 text-black text-[10px] font-bold w-5 h-5 flex items-center justify-center rounded-full">
                {room.orders_count}
              </span>
            )}
          </button>
        ))}
      </div>
    )
  }

  return (
    <div className="flex items-stretch shrink-0 h-12 border-b border-border">
      {isMobile && <FloorPicker />}
      {!isMobile && generalCustomAccess() && REN?.access?.edit_floor !== 0 &&
        <button
          onClick={() => setEditing(!editing)}
          className={`w-12 flex items-center justify-center transition-colors ${
            editing 
              ? 'bg-primary/20' 
              : 'text-color hover:text-secondary hover:bg-primary/20'
          }`}
        >
          <Pencil size={18} />
        </button>
      }
      {renderRooms()}
      {!editing && REN?.delivery?.phone_orders && (
        <button
          onClick={() => setDeliveryOpen(true)}
          title={__("New delivery order")}
          className={`${isMobile ? 'w-12 justify-center' : 'px-3 gap-2'} flex items-center border-l border-border text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors`}
        >
          <Truck size={18} />
          {!isMobile && <span className="text-sm font-medium">{__("Delivery")}</span>}
        </button>
      )}
      {deliveryOpen && <DeliveryDialog open onClose={() => setDeliveryOpen(false)} />}
      {!editing && REN?.pos_profile?.name && (REN?.access?.manage_register || REN?.access?.take_payments) && (
        <button
          onClick={() => setRegisterOpen(true)}
          title={__("Cash register")}
          className="w-12 flex items-center justify-center border-l border-border text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
        >
          <Landmark size={18} />
        </button>
      )}
      {!editing && <StaffMenu access={REN?.access} posProfile={REN?.pos_profile?.name} restaurant={REN?.restaurant?.restaurant_name || REN?.restaurant?.name} />}
      {registerOpen && (
        <RegisterPanel posProfile={REN.pos_profile.name} onClose={() => setRegisterOpen(false)} />
      )}
      {editing && can("room.create") && (
        <button 
          className="w-12 flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
          onClick={addRoom}
        >
          <Plus size={20} />
        </button>
      )}
    </div>
  )
}

/** Phones: the floor is chosen here instead of the side rail. */
function FloorPicker() {
  const { floors, currentFloor, setCurrentFloor } = useFloors()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [open])

  if (!floors?.length) return null
  const multiple = floors.length > 1

  return (
    <div ref={ref} className="relative shrink-0 border-r border-border">
      <button
        onClick={() => multiple && setOpen(!open)}
        className="h-full max-w-[120px] flex items-center gap-1 px-3 text-sm font-semibold"
      >
        <span className="truncate">{currentFloor?.description}</span>
        {multiple && <ChevronDown size={15} className="shrink-0 text-muted-foreground" />}
      </button>
      {open && (
        <div className="absolute left-1 top-full mt-1 z-50 min-w-44 rounded-lg border border-border bg-popover text-popover-foreground shadow-xl py-1">
          {floors.map((f) => (
            <button
              key={f.name}
              onClick={() => { setCurrentFloor(f); setOpen(false) }}
              className="w-full flex items-center justify-between gap-3 px-3 py-2.5 text-sm hover:bg-accent text-left"
            >
              <span className="truncate">{f.description}</span>
              {currentFloor?.name === f.name && <Check size={15} />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
