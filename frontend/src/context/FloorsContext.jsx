import { createContext, useContext, useEffect, useState } from 'react'
import { useRestaurant } from './RestaurantContext'
import { usePersistedState } from '@/hooks/usePersistedState'
const FloorsContext = createContext(null)
import { useFrappeRealtime } from '@/hooks/useFrappeRealtime';

export function FloorsProvider({ children }) {
  const [currentFloor, setCurrentFloor] = usePersistedState('rm_current_floor', null)
  const [loading, setLoading] = useState(true)
  const { callMethod, RM } = useRestaurant()
  const [floors, setFloors] = useState([])
  const [tables, setTables] = useState([])
  const [rooms, setRooms] = useState([])
  const [stations, setStations] = useState([])

  const loadObjects = async () => {
    const data = await callMethod("Ren Floor", currentFloor.name, "get_children")
    setRooms(data?.rooms || [])
    setStations(data?.stations || [])
  }

  useEffect(() => {
    if (currentFloor) {
      loadObjects()
    } else {
      setRooms([])
      setStations([])
    }
  }, [currentFloor])

  useEffect(() => {
    if (RM?.floors) setFloors(RM.floors)
  }, [RM?.floors])

  useEffect(() => {
    if (floors.length === 0){
      setCurrentFloor(null)
      return
    }

    const stillExists = currentFloor && floors.find(f => f.name === currentFloor.name)
    if (!stillExists) {
      setCurrentFloor(floors[0])
    }
  }, [RM?.floors, floors])

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

  if (!RM?.floors) return null;

  return (
    <FloorsContext.Provider value={{ 
      floors, 
      currentFloor, setCurrentFloor, 
      loading, 
      rooms, setRooms,
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