import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { useRestaurant } from './RestaurantContext'
import { usePersistedState } from '@/hooks/usePersistedState'
const FloorsContext = createContext(null)
import { useFrappeRealtime } from '@/hooks/useFrappeRealtime';
import { getUrlParam, setUrlParams } from '@/utils/urlState';

export function FloorsProvider({ children }) {
  const [currentFloor, setCurrentFloor] = usePersistedState('ren_current_floor', null)
  const { callMethod, REN, settingsUpdate } = useRestaurant()
  const [floors, setFloors] = useState([])
  const [tables, setTables] = useState([])
  const [rooms, setRooms] = useState([])
  const [stations, setStations] = useState([])
  // the floor `rooms` belong to (null until they are loaded)
  const [roomsFloor, setRoomsFloor] = useState(null)

  // the floor whose rooms we want: a slower answer for a floor left behind
  // (the saved one, before the URL's) must not overwrite the current one
  const wantedFloor = useRef(null)
  const loadObjects = async () => {
    const name = currentFloor.name
    wantedFloor.current = name
    const data = await callMethod("Ren Floor", name, "get_children")
    if (wantedFloor.current !== name) return
    setRooms(data?.rooms || [])
    setStations(data?.stations || [])
    setRoomsFloor(name)
  }

  // the floor's rooms and stations: when the floor changes, and when the setup
  // or the person's access changes (settingsUpdate)
  useEffect(() => {
    if (currentFloor) {
      loadObjects()
    } else {
      setRooms([])
      setStations([])
      setTables([])
      setRoomsFloor(null)
    }
  }, [currentFloor?.name, settingsUpdate])

  useEffect(() => {
    if (REN?.floors) setFloors(REN.floors)
  }, [REN?.floors])

  // Pick the floor once the restaurant data is in: the one in the URL, else
  // the last one used on this device (saved), else the first. Uses REN.floors
  // directly: the `floors` state is still empty on the first render, and
  // treating that as "no floors" used to wipe the saved floor on reload.
  useEffect(() => {
    const list = REN?.floors
    if (!list) return
    if (list.length === 0) {
      setCurrentFloor(null)
      return
    }
    const fromUrl = getUrlParam('floor')
    const wanted = (fromUrl && list.find(f => f.name === fromUrl))
      || (currentFloor && list.find(f => f.name === currentFloor.name))
      || list[0]
    if (wanted.name !== currentFloor?.name) setCurrentFloor(wanted)
  }, [REN?.floors])

  useEffect(() => {
    if (currentFloor?.name) setUrlParams({ floor: currentFloor.name })
  }, [currentFloor?.name])

  useFrappeRealtime(currentFloor?.name, (data) => {
    if(!data.type) return;
    const fn = data.type == "Ren Room" ? setRooms : setStations;

    fn(prev => {
      if (data._deleted) {
        return prev.filter(t => t.name !== data.name);
      }
      const exists = prev.some(t => t.name === data.name);
      if (exists) {
        return prev.map(t => t.name === data.name ? { ...t, ...data } : t);
      }

      loadObjects();
      return prev//[...prev, data];
    });
  }, [currentFloor?.name]);

  if (!REN?.floors) return null;

  return (
    <FloorsContext.Provider value={{ 
      floors, 
      currentFloor, setCurrentFloor, 
      rooms, setRooms, roomsFloor,
      tables, setTables,
      stations, setStations,
      loadObjects
    }}>
      {children}
    </FloorsContext.Provider>
  )
}

export const useFloors = () => {
  const ctx = useContext(FloorsContext)
  if (!ctx) throw new Error('useFloors debe usarse dentro de FloorsProvider')
  return ctx
}