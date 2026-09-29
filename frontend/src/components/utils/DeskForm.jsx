import { useState, useEffect, useCallback, useRef } from 'react'
import { FrappeField } from './FrappeField.jsx'
import { X, Loader2 } from 'lucide-react'

const BASE_URL = "restaurant_management.restaurant_management.doctype.desk_form.desk_form."

function callMethod(method, args) {
  return new Promise((resolve, reject) => {
    frappe.call({
      method: `${BASE_URL}${method}`,
      args,
      freeze: false,
      callback: (r) => resolve(r.message),
      error: reject,
    })
  })
}

function buildLayout(fields) {
  const sections = []
  let currentSection = null
  let currentColumn = null

  const ensureSection = () => {
    if (!currentSection) {
      currentSection = { label: '', columns: [], collapsible: false }
      sections.push(currentSection)
    }
  }

  const ensureColumn = () => {
    ensureSection()
    if (!currentColumn) {
      currentColumn = { fields: [] }
      currentSection.columns.push(currentColumn)
    }
  }

  fields.forEach((df) => {
    if (df.fieldtype === 'Section Break') {
      currentSection = {
        label: df.label || '',
        fieldname: df.fieldname,
        columns: [],
        collapsible: df.collapsible || false,
        hidden: df.hidden || false,
      }
      sections.push(currentSection)
      currentColumn = null
    } else if (df.fieldtype === 'Column Break') {
      ensureSection()
      currentColumn = null
    } else {
      ensureColumn()
      currentColumn.fields.push(df)
    }
  })

  return sections
}

function FormSection({ section, values, setValue, readOnlyFields }) {
  const [collapsed, setCollapsed] = useState(false)
  const colCount = section.columns.length || 1

  if (section.hidden) return null

  const hasVisibleFields = section.columns.some(col =>
    col.fields.some(f => !f.hidden)
  )
  if (!hasVisibleFields) return null

  return (
    <div className="mb-4">
      {section.label && (
        <div
          className={`text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3 pb-2 border-b border-border ${section.collapsible ? 'cursor-pointer' : ''}`}
          onClick={() => section.collapsible && setCollapsed(!collapsed)}
        >
          {section.collapsible && (
            <span className="mr-1">{collapsed ? '▸' : '▾'}</span>
          )}
          {section.label}
        </div>
      )}
      {!collapsed && (
        <div
          className="grid gap-x-4 gap-y-1"
          style={{ gridTemplateColumns: `repeat(${colCount}, 1fr)` }}
        >
          {section.columns.map((col, colIdx) => (
            <div key={colIdx} className="space-y-1">
              {col.fields.map((field) => {
                if (field.hidden) return null
                const isReadOnly = field.read_only || readOnlyFields?.[field.fieldname]
                return (
                  <FrappeField
                    key={field.fieldname}
                    df={field}
                    readOnly={isReadOnly}
                    value={values[field.fieldname]}
                    onChange={(val) => setValue(field.fieldname, val)}
                  />
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function DeskForm({
  formName,
  docName,
  doctype: initialDoctype,
  title,
  fieldProperties = {},
  onSave,
  onClose,
  onReload,
  primaryActionLabel,
  location,
}) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deskForm, setDeskForm] = useState(null)
  const [layout, setLayout] = useState([])
  const [values, setValues] = useState({})
  const [doctype, setDoctype] = useState(initialDoctype || null)
  const dataRef = useRef(null) // guarda la respuesta completa como el original

  // Replica el flujo de FrappeForm.initialize()
  useEffect(() => {
    if (!formName) return

    const name = formName.replaceAll(' ', '-').toLowerCase()

    setLoading(true)

    const init = async () => {
      // Paso 1: get_form_data (equivalente a get_all)
      const data = await callMethod('get_form_data', { form_name: name, doc_name: docName })
      dataRef.current = data

      const form = data.desk_form
      const dt = form.doc_type

      setDeskForm(form)
      setDoctype(dt)

      // Paso 2: Si no vino doc pero tenemos doc_name, fetch separado
      // Equivale a: if (!this.doc && this.doc_name) this.doc = await this.get_doc()
      let doc = data.doc
      if (!doc && docName) {
        doc = await callMethod('get_doc', { doctype: dt, doc_name: docName })
      }

      // Deep copy como hace el original
      doc = JSON.parse(JSON.stringify(doc || {}))

      // Asegurar que doctype esté en el doc
      doc.doctype = dt

      setValues(doc)

      // Paso 3: Procesar fields con field_properties
      const processedFields = (form.desk_form_fields || []).map((df) => {
        const copy = { ...df }

        // Limpiar referencias de parent como hace el original
        delete copy.parent
        delete copy.parentfield
        delete copy.parenttype

        // Aplicar field_properties (como el original hace en make())
        const props = fieldProperties[df.fieldname]
        if (props) {
          Object.assign(copy, props)
          if (props.read_only) {
            copy.doctype = null
            copy.docname = null
          }
        }

        // Manejar Table fields como el original
        if (copy.fieldtype === 'Table') {
          copy.get_data = () => doc[copy.fieldname] || []
          if (data.hasOwnProperty(copy.fieldname)) {
            copy.fields = data[copy.fieldname]
          }
          copy.options = null
        } else {
          if (copy.read_only) {
            copy.doctype = null
            copy.docname = null
          }
        }

        return copy
      })

      setLayout(buildLayout(processedFields))
      setLoading(false)

      // Callback post-carga
      setTimeout(() => onReload?.(), 100)
    }

    init().catch((err) => {
      console.error('DeskForm init error:', err)
      setLoading(false)
    })
  }, [formName, docName])

  const setValue = useCallback((fieldname, value) => {
    setValues((prev) => ({ ...prev, [fieldname]: value }))
  }, [])

  // Reload desde servidor (equivalente a background_reload)
  const reload = useCallback(async (fromServer = true) => {
    if (!doctype || !docName) return
    const doc = await callMethod('get_doc', { doctype, doc_name: docName })
    const parsed = JSON.parse(JSON.stringify(doc))
    parsed.doctype = doctype
    setValues(parsed)
    onReload?.()
  }, [doctype, docName, onReload])

  const handleSave = useCallback(() => {
    if (saving) return
    setSaving(true)

    const doc = { ...values, doctype }
    const name = formName.replaceAll(' ', '-').toLowerCase()

    frappe.call({
      type: 'POST',
      method: `${BASE_URL}accept`,
      args: {
        desk_form: name,
        data: doc,
        doc_name: docName,
      },
      freeze: true,
      callback: (data) => {
        if (!data.exc) {
          onSave?.(data.message, values)
        } else {
          frappe.msgprint(__('There were errors. Please report this.'))
        }
        setSaving(false)
      },
      error: () => {
        frappe.msgprint(__('There were errors. Please report this.'))
        setSaving(false)
      },
    })
  }, [values, doctype, formName, docName, saving, onSave])

  const readOnlyFields = Object.entries(fieldProperties).reduce((acc, [k, v]) => {
    if (v.read_only) acc[k] = true
    return acc
  }, {})

  const content = loading ? (
    <div className="flex items-center justify-center py-12">
      <Loader2 className="animate-spin text-muted-foreground" size={24} />
    </div>
  ) : (
    <div className="px-5 py-4 desk-form-body">
      {layout.map((section, idx) => (
        <FormSection
          key={section.fieldname || idx}
          section={section}
          values={values}
          setValue={setValue}
          readOnlyFields={readOnlyFields}
        />
      ))}
    </div>
  )

  const saveLabel = primaryActionLabel || __('Save')
  const inModal = !location

  if (!inModal) {
    return (
      <div className="desk-form">
        {content}
        <div className="flex justify-end gap-2 px-5 py-3">
          <button onClick={handleSave} disabled={saving || loading}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {saving ? __('Saving...') : saveLabel}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-[1500] flex items-center justify-center bg-black/50">
      <div
        className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[85vh] flex flex-col"
        onMouseDown={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        onTouchStart={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <h3 className="text-base font-semibold text-foreground">
            {title || deskForm?.title || formName}
          </h3>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1">{content}</div>

        <div className="flex justify-end gap-2 px-5 py-3 border-t border-border shrink-0">
          <button onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg text-muted-foreground hover:bg-accent transition-colors">
            {__('Cancel')}
          </button>
          <button onClick={handleSave} disabled={saving || loading}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {saving ? __('Saving...') : saveLabel}
          </button>
        </div>
      </div>
    </div>
  )
}