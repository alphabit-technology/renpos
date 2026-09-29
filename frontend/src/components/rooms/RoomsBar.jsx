import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { Pencil, Plus } from 'lucide-react'
import{ useRooms } from "@/context/RoomsContext.jsx"
import { useFloors } from '../../context/FloorsContext.jsx'
import {can, generalCustomAccess} from "@/router/permissions"

export function RoomsBar() {
  const { editing, setEditing, ready } = useRestaurant();
  const {rooms, addRoom, currentRoom, setCurrentRoom} = useRooms();
  const {currentFloor} = useFloors()

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
            className={`relative flex-1 min-w-[120px] flex items-center justify-center px-4 py-3 text-center font-medium transition-colors border-r border-muted ${
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
      {generalCustomAccess() &&
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
      {editing && can("room.create") && (
        <button 
          className="w-12 flex items-center justify-center text-rm-rooms-text/60 hover:text-rm-rooms-text hover:bg-rm-rooms-active transition-colors"
          onClick={addRoom}
        >
          <Plus size={20} />
        </button>
      )}
    </div>
  )
}