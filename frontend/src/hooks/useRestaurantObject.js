// useRestaurantObject.js
import { useState, useEffect, useCallback } from 'react'
import { debounce } from 'es-toolkit'
import { useRestaurant } from '../../context/RestaurantContext.jsx'
import { useFrappeRealtime } from '../../hooks/useFrappeRealtime'

export function useRestaurantObject(initialData, { onDelete } = {}) {
  const { editing, currentTable, callMethod, currentRoom } = useRestaurant()
  const [data, setData] = useState(initialData)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const [size, setSize] = useState({ width: 100, height: 100 })
  const [isDragging, setIsDragging] = useState(false)

  useEffect(() => setData(initialData), [initialData])

  const isSelected = editing && currentTable?.name === data.name

  useFrappeRealtime(data.name, (payload) => {
    if (payload.action === 'Notifications') return
    if (data.room?.name !== currentRoom?.name) return

    switch (payload.action) {
      case 'Update':
        setData(prev => ({ ...prev, ...payload.data }))
        break
      case 'Delete':
        onDelete?.(data.name)
        break
    }
  }, [data.name, currentRoom?.name])

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
      callMethod('Ren Table', data.name, 'set_attr', {
        args: {attr, value},
        freeze: false
      })
    }, 0),
    [data.name]
  )

  const handleDragStop = (e, d) => {
    setIsDragging(false)
    const newPos = { x: d.x, y: d.y }
    setPosition(newPos)
    updateAttr('data_style', JSON.stringify({ ...newPos, ...size }))
  }

  const handleResizeStop = (e, dir, ref, delta, newPos) => {
    const newSize = { width: ref.offsetWidth, height: ref.offsetHeight }
    setSize(newSize)
    setPosition(newPos)
    updateAttr('data_style', JSON.stringify({ ...newPos, ...newSize }))
  }

  return {
    data, setData,
    position, size,
    isDragging, setIsDragging,
    isSelected, editing,
    updateAttr,
    handleDragStop,
    handleResizeStop,
  }
}