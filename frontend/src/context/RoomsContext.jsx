import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { useRestaurant } from './RestaurantContext'
import { useFloors } from './FloorsContext'
import { usePersistedState } from '@/hooks/usePersistedState'
import { useFrappeRealtime } from '@/hooks/useFrappeRealtime';
import { getUrlParam, setUrlParams } from '@/utils/urlState';

const RoomsContext = createContext(null)

export function RoomsProvider({ children }) {
  const { callMethod, REN, settingsUpdate } = useRestaurant()
  const { currentFloor, setTables, rooms, roomsFloor, loadObjects } = useFloors()
  
  const storageKey = currentFloor ? `ren_current_room_${currentFloor.name}` : null
  const [currentRoom, setCurrentRoom] = usePersistedState(storageKey, null);

  // Menu in force for the room (room menu > restaurant menu > company default,
  // enabled ones only), resolved by the server; reloaded when menus change.
  const [activeMenuInfo, setActiveMenuInfo] = useState(null)
  const [menuVersion, setMenuVersion] = useState(0)
  const activeMenu = activeMenuInfo?.name || null

  useEffect(() => {
    let cancelled = false
    frappe.call({
      method: 'renpos.api.menus.get_active_menu',
      args: { room: currentRoom?.name || null },
    }).then((r) => { if (!cancelled) setActiveMenuInfo(r.message || null) }, () => {})
    return () => { cancelled = true }
  }, [currentRoom?.name, REN, menuVersion])

  useFrappeRealtime('menu_changed', () => setMenuVersion((v) => v + 1), [])

  // scheduled menus (breakfast, happy hour) change by the clock
  useEffect(() => {
    const t = setInterval(() => setMenuVersion((v) => v + 1), 60000)
    return () => clearInterval(t)
  }, [])

  const urlRoom = useRef(getUrlParam('room'))
  useEffect(() => {
    // only with the rooms of this floor in (not before they load, nor another floor's)
    if (!currentFloor || roomsFloor !== currentFloor.name) return
    // no rooms left (deleted, or no access any more): nothing selected, no tables
    if (rooms.length === 0) {
      if (currentRoom) setCurrentRoom(null)
      setTables([])
      return
    }

    // the room in the URL (as it was on load: the rooms of another floor may
    // come first and rewrite the URL), else the last one used on this floor, else the first
    const fromUrl = urlRoom.current
    const found = fromUrl && rooms.find(r => r.name === fromUrl)
    if (found) urlRoom.current = null
    const wanted = found
      || (currentRoom && rooms.find(r => r.name === currentRoom.name))
      || rooms[0]
    if (wanted.name !== currentRoom?.name) setCurrentRoom(wanted)
  }, [rooms, roomsFloor])

  useEffect(() => {
    if (currentRoom?.name) setUrlParams({ room: currentRoom.name })
  }, [currentRoom?.name])

  const wantedRoom = useRef(null)
  const loadTables = async () => {
    const name = currentRoom.name
    wantedRoom.current = name
    const data = await callMethod("Ren Room", name, "get_tables")
    if (wantedRoom.current === name) setTables(data?.tables || [])
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
  }, [currentRoom?.name, REN?.permissions]);

  const addRoom = async () => {
    await callMethod("Ren Floor", currentFloor.name, "add_room")
    await loadObjects()
  }
  
  useEffect(() => {
    if (currentRoom) loadTables()
    else wantedRoom.current = null
  }, [currentRoom?.name, settingsUpdate]);

  return (
    <RoomsContext.Provider value={{ 
      rooms, 
      currentRoom, 
      setCurrentRoom, addRoom, 
      activeMenu,
      activeMenuInfo
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