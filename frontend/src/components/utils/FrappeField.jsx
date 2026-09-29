import { useRef, useEffect } from 'react'

export function FrappeField({ df, value, onChange, readOnly, hidden }) {
  const ref = useRef(null)
  const controlRef = useRef(null)
  const internalChange = useRef(false)
  const valueRef = useRef(value) // track current value sin re-render

  // Mantener valueRef sincronizado
  valueRef.current = value

  useEffect(() => {
    if (!ref.current) return

    // Construir df completo como lo hace FrappeForm.make()
    const fieldDf = {
      ...df,
      read_only: readOnly ? 1 : (df.read_only || 0),
    }

    let control
    try {
      control = frappe.ui.form.make_control({
        parent: ref.current,
        df: fieldDf,
        render_input: true,
        only_input: false,
      })
    } catch (e) {
      console.warn(`FrappeField: failed to create "${df.fieldname}" (${df.fieldtype})`, e)
      return
    }

    if (!control) {
      console.warn(`FrappeField: make_control returned undefined for "${df.fieldname}" (${df.fieldtype})`)
      return
    }

    // Algunos controles necesitan make() explícito
    if (typeof control.make === 'function' && !control.has_input) {
      control.make()
    }

    // Forzar estado Write para que no quede disabled
    if (!readOnly) {
      control.disp_status = 'Write'
      if (typeof control.make_input === 'function' && !control.$input) {
        control.make_input()
      }
    }

    // Forzar habilitación del input HTML
    if (control.$input) {
      control.$input.prop('disabled', false)
      control.$input.prop('readonly', readOnly ? true : false)
      control.$input.css('pointer-events', 'auto')
    }

    // Establecer valor — usar el ref para tener el valor más actual
    const currentVal = valueRef.current
    // Para valores que son 0, false, o string vacío, debemos ser explícitos
    if (currentVal !== undefined && currentVal !== null) {
      control.set_value(currentVal)
    } else if (df.default !== undefined && df.default !== null) {
      control.set_value(df.default)
    } else {
      control.set_value('')
    }

    // Listeners para cambios del usuario
    if (!readOnly) {
      const handleChange = () => {
        internalChange.current = true
        const newVal = control.get_value()
        onChange?.(newVal)
      }

      // $input para la mayoría de controles
      if (control.$input) {
        control.$input.on('change', handleChange)
        // 'input' para capturar mientras escribe (no solo al blur)
        control.$input.on('input', handleChange)
      }

      // Fallback para controles sin $input (Color, Select, etc.)
      if (!control.$input && control.$wrapper) {
        control.$wrapper.on('change', handleChange)
      }

      // Algunos controles de Frappe usan onchange en el df
      const originalOnChange = fieldDf.onchange
      fieldDf.onchange = function() {
        originalOnChange?.call(this)
        handleChange()
      }
    }

    controlRef.current = control

    return () => {
      controlRef.current = null
      if (ref.current) $(ref.current).empty()
    }
  }, [df.fieldtype, df.fieldname, df.options, readOnly])

  // Sincronizar solo cambios externos (no los del usuario)
  useEffect(() => {
    if (internalChange.current) {
      internalChange.current = false
      return
    }

    if (!controlRef.current) return

    // Comparar con el valor actual del control para evitar loops
    const controlVal = controlRef.current.get_value?.()
    const newVal = value !== undefined && value !== null ? value : ''

    // Solo actualizar si realmente cambió
    // Comparación loose para manejar 0 == "0", etc.
    if (String(controlVal) !== String(newVal)) {
      controlRef.current.set_value(newVal)
    }
  }, [value])

  if (hidden || df.hidden) return null

  return <div ref={ref} />
}