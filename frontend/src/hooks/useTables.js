import { useState, useEffect } from 'react';
import { useFrappeRealtime } from './useFrappeRealtime';
import { useRestaurant } from '@/context/RestaurantContext.jsx';
import { useRooms } from '@/context/RoomsContext.jsx';

export function useTables() {
  const [tables, setTables] = useState();
  const { callMethod } = useRestaurant();
  const { currentRoom } = useRooms();

  const loadTables = async () => {
    const data = await callMethod("Ren Room", currentRoom.name, "get_tables")
    setTables(data?.tables || [])
  }
  
  useEffect(() => {
    currentRoom && loadTables()
  }, [currentRoom?.name]);

  useFrappeRealtime(currentRoom?.name, (r) => {
    if (r.action === 'Add') {
      setTables(prev => [...prev, r.table]);
    } else if (r.action === 'Update') {
      setTables(prev => prev.map(t => 
        t.name === r.data.name ? r.data : t
      ));
    } else if (r.action === 'Delete') {
      setTables(prev => prev.filter(t => t.name !== r.data.name));
    }
  }, [currentRoom?.name]);

  const addTable = async (type = 'Table') => {
    if (!currentRoom) return;

    await callMethod("Ren Room", currentRoom.name, "add_object");
  };

  const updateDataTable = async (table) => {
    setTables(prev => prev.map(t => 
      t.name === table.name ? { ...t, ...table } : t
    ));
  };

  return { tables, addTable, updateDataTable };
}