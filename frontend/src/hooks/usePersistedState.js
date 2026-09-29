import { useState, useEffect } from 'react'

export function usePersistedState(key, initialValue = null) {
  const [value, setValue] = useState(() => {
    if (!key) return initialValue
    try {
      const stored = localStorage.getItem(key)
      return stored ? JSON.parse(stored) : initialValue
    } catch {
      return initialValue
    }
  })

  useEffect(() => {
    if (!key) {
      setValue(initialValue)
      return
    }
    try {
      const stored = localStorage.getItem(key)
      setValue(stored ? JSON.parse(stored) : initialValue)
    } catch {
      setValue(initialValue)
    }
  }, [key])

  const setPersisted = (newValue) => {
    const resolved = typeof newValue === 'function' ? newValue(value) : newValue
    setValue(resolved)

    if (!key) return

    if (resolved === null) {
      localStorage.removeItem(key)
    } else {
      localStorage.setItem(key, JSON.stringify(resolved))
    }
  }

  return [value, setPersisted]
}