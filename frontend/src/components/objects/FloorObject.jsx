import { Rnd } from 'react-rnd'
import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { useState, useEffect, useCallback } from 'react'
import { Settings, Trash2, Square, Circle, User, Users, Utensils } from 'lucide-react'
import { debounce } from 'es-toolkit'
import { ActionButton } from '@c/ui/ActionButton.jsx'


import { useFrappeRealtime } from '../../hooks/useFrappeRealtime.js'

export function FloorObject({ 
  actions,
  data: initialData, 
  doctype,
  onSelect, 
  onDelete,
  defaultColor = '#22c55e',
  renderBadges,
  renderOverlay,
  allowShape = true,
}) {
  const { editing, currentTable, callMethod } = useRestaurant()
  const [data, setData] = useState(initialData)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [size, setSize] = useState({ width: 100, height: 100 })
  const [isDragging, setIsDragging] = useState(false)
  const [editObject, setEditObject] = useState(false)

  useEffect(() => {
    setData(initialData)
  }, [initialData])

  const isSelected = editing && currentTable?.name === data.name
  const isRound = data.shape === 'Round'
  const bgColor = data.color || defaultColor

  /* useFrappeRealtime(data.name, (msg) => {
    if (msg.action === "Notifications") return
    switch (msg.action) {
      case 'Update':
        const data = msg.data;
        console.log(["data", data])
        if(data.room){

        }else{

        }
        //setData(prev => ({ ...prev, ...msg.data }))
        break
      case 'Delete':
        onDelete?.(data.name)
        break
    }
  }, [data.name]) */

  useEffect(() => {
    let style = {}
    try {
      style = data.data_style ? JSON.parse(data.data_style) : {}
    } catch (e) {}
    setPosition({ x: style.x || 0, y: style.y || 0 })
    setSize({ width: style.width || 100, height: style.height || 100 })
  }, [data.data_style])

  const updateAttr = useCallback(
    debounce((attr, value) => {
      callMethod(doctype, data.name, "set_attr", {
        args: { attr, value },
        freeze: false
      })
    }, 0),
    [data.name, doctype]
  )

  const handleDragStop = (e, d) => {
    setIsDragging(false)
    const newPosition = { x: d.x, y: d.y }
    setPosition(newPosition)
    updateAttr("data_style", JSON.stringify({ ...newPosition, ...size }))
  }

  const handleResizeStop = (e, direction, ref, delta, newPosition) => {
    const newSize = { width: ref.offsetWidth, height: ref.offsetHeight }
    setSize(newSize)
    setPosition(newPosition)
    updateAttr("data_style", JSON.stringify({ ...newPosition, ...newSize }))
  }

  const handleClick = () => {
    !isDragging && onSelect(data)
  }

  const toggleShape = () => {
    const newShape = data.shape === 'Round' ? 'Square' : 'Round'
    setData(prev => ({ ...prev, shape: newShape }))
    updateAttr("shape", newShape)
  }

  const handleObjectDelete = () => {
    callMethod(doctype, initialData.name, "delete")
  }

  return (
    <>
    <Rnd
      position={position}
      size={size}
      onDragStart={() => setIsDragging(true)}
      onDragStop={handleDragStop}
      onResizeStop={handleResizeStop}
      disableDragging={!editing}
      enableResizing={editing && isSelected}
      minWidth={60}
      minHeight={60}
      onContextMenu={(e) => e.preventDefault()}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="relative w-full h-full">
        <div
          onMouseDown={handleClick}
          className={`
            w-full h-full flex items-center justify-center
            text-white font-semibold cursor-pointer select-none
            transition-shadow duration-200
            ${isRound ? 'rounded-full' : 'rounded-lg'}
            ${isSelected ? 'ring-2 ring-foreground/70 ring-offset-2 ring-offset-foreground/20' : ''}
            ${isDragging ? 'opacity-80' : ''}
          `}
          style={{ backgroundColor: bgColor }}
        >
          {renderOverlay?.(data)}

          <span className="relative z-10 text-3xl font-extralight drop-shadow-lg opacity-70">
            {data.description}
          </span>

          {renderBadges?.(data, editing)}
        </div>

        {editing && isSelected && (
          <div
            className="absolute top-0 h-full z-50"
            style={{ left: 'calc(100% + 8px)' }}
          >
            <div
              className="absolute top-1/2 -translate-y-1/2 flex flex-col gap-0 bg-foreground/10 rounded-lg shadow-lg p-0"
              onMouseDown={(e) => e.stopPropagation()}
              onTouchStart={(e) => e.stopPropagation()}
            >
              {actions?.()}
            </div>
          </div>
        )}
      </div>
    </Rnd>
    </>
  )
}