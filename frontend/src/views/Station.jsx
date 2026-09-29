import { FloorObject } from '@c/objects/FloorObject'
import { Utensils } from 'lucide-react'

export function Station({ station, onSelect, onDelete }) {
  return (
    <FloorObject
      data={station}
      doctype="Ren Station"
      defaultColor="#9f4c5c"
      onSelect={onSelect}
      onDelete={onDelete}
      allowShape={false}
      renderBadges={(data, editing) => (
        <>
          {!editing && data.orders_count > 0 && (
            <div className="absolute top-0.5 left-1/2 -translate-x-1/2 bg-zinc-800/80 text-white text-md flex items-center gap-1 h-[24px] px-2 rounded-md shadow-md z-20">
              <Utensils size={13} />
              <span>{data.orders_count}</span>
            </div>
          )}
        </>
      )}
    />
  )
}