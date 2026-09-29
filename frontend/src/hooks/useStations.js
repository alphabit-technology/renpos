import { useState, useEffect } from 'react';
import { useFrappeRealtime } from './useFrappeRealtime';
import { useRestaurant } from '@/context/RestaurantContext.jsx';
import { useRooms } from '@/context/RoomsContext.jsx';

export function useStations() {
  const [ stations, setTables ] = useState([]);
  const { callMethod } = useRestaurant();
  const { currentRoom } = useRooms();

  const loadStations = async () => {
    const data = await callMethod("Ren Room", currentRoom.name, "get_tables")
    setTables(data?.tables || [])
  }
  useEffect(() => {
    currentRoom && loadTables()
  }, [currentRoom]);

  useFrappeRealtime(currentRoom?.name, (data) => {
    /* if (data.action === 'Add') {
      setTables(prev => [...prev, data.table]);
    } else if (data.action === 'Update') {
      setTables(prev => prev.map(t => 
        t.name === data.table.name ? data.table : t
      ));
    } else if (data.action === 'Delete') {
      setTables(prev => prev.filter(t => t.name !== data.table.name));
    } */
  }, [currentRoom?.name]);

  const addTable = async (type = 'Table') => {
    if (!currentRoom) return;

    await callMethod("Ren Room", currentRoom.name, "add_object");
  };

  return { tables, addTable };
}