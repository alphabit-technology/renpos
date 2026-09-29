export const mockRooms = [
  { name: 'room-1', description: 'R 2', orders_count: 0 },
  { name: 'room-2', description: 'R 1', orders_count: 1 },
]

export const mockTables = {
  'room-1': [
    { 
      name: 'table-1', 
      description: 'T-142', 
      type: 'Table', 
      shape: 'Square', 
      data_style: '{"x":180,"y":150,"width":140,"height":120}', 
      color: '#3d6b3d', 
      orders_count: 0, 
      no_of_seats: 4,
      customer: 'John Doe'
    },
    { 
      name: 'table-2', 
      description: 'T-83', 
      type: 'Table', 
      shape: 'Square', 
      data_style: '{"x":50,"y":280,"width":130,"height":110}', 
      color: '#22c55e', 
      orders_count: 1, 
      no_of_seats: 4,
      customer: 'Jane Smith'
    },
    { 
      name: 'table-3', 
      description: 'T-140', 
      type: 'Table', 
      shape: 'Round', 
      data_style: '{"x":280,"y":350,"width":150,"height":150}', 
      color: '#22c55e', 
      orders_count: 0, 
      no_of_seats: 4,
      customer: null
    },
    { 
      name: 'pc-1', 
      description: 'P-185', 
      type: 'Production Center', 
      data_style: '{"x":500,"y":200,"width":140,"height":100}', 
      color: '#9f4c5c', 
      orders_count: 0 
    },
    { 
      name: 'pc-2', 
      description: 'P-421', 
      type: 'Production Center', 
      data_style: '{"x":350,"y":550,"width":130,"height":120}', 
      color: '#4a6670', 
      orders_count: 0 
    },
  ],
  'room-2': [
    { 
      name: 'table-4', 
      description: 'T-1', 
      type: 'Table', 
      shape: 'Square', 
      data_style: '{"x":100,"y":200,"width":120,"height":100}', 
      color: '#22c55e', 
      orders_count: 1, 
      no_of_seats: 4 
    },
  ],
}