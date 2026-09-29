import { createContext, useContext, useEffect, useState } from 'react'
import { useRestaurant } from './RestaurantContext'
import { useFloors } from './FloorsContext'
import { usePersistedState } from '@/hooks/usePersistedState'
import { useFrappeRealtime } from '@/hooks/useFrappeRealtime';

const RoomsContext = createContext(null)

export function RoomsProvider({ children }) {
  const { callMethod, RM, settingsUpdate } = useRestaurant()
  const { currentFloor, setTables, rooms, setRooms, loadObjects } = useFloors()
  
  const storageKey = currentFloor ? `rm_current_room_${currentFloor.name}` : null
  const [currentRoom, setCurrentRoom] = usePersistedState(storageKey, null);

  const restaurant = RM.restaurant || {};
  const [activeMenu, setActiveMenu] = useState(currentRoom?.menu || restaurant.active_menu);

  useEffect(() => {
    setActiveMenu(currentRoom?.menu || RM.restaurant?.active_menu )
  }, [RM, currentRoom])

  useEffect(() => {
    if (rooms.length === 0) return

    const stillExists = currentRoom && rooms.find(r => r.name === currentRoom.name)
    if (!stillExists) {
      setCurrentRoom(rooms[0])
    }
  }, [rooms])

  const loadTables = async () => {
    const data = await callMethod("Ren Room", currentRoom.name, "get_tables")
    setTables(data?.tables || [])
  }

  useFrappeRealtime(currentRoom?.name, (data) => {
    setTables(prev => {
      if (data._deleted) {
        return prev.filter(t => t.name !== data.name);
      }
      const exists = prev.some(t => t.name === data.name);
      if (exists) {
        return prev.map(t => t.name === data.name ? { ...t, ...data } : t);
      }

      loadTables();
      return prev;
    });
  }, [currentRoom?.name, RM?.permissions]);

  const addRoom = async () => {
    await callMethod("Ren Floor", currentFloor.name, "add_room")
    await loadObjects()
  }
  
  useEffect(() => {
    currentRoom && loadTables()
  }, [currentRoom?.name, settingsUpdate]);

  return (
    <RoomsContext.Provider value={{ 
      rooms, 
      currentRoom, 
      setCurrentRoom, addRoom, 
      activeMenu 
    }}>
      {children}
    </RoomsContext.Provider>
  )
}

export const useRooms = () => {
  const ctx = useContext(RoomsContext)
  if (!ctx) throw new Error('useRooms debe usarse dentro de RoomsProvider')
  return ctx
}