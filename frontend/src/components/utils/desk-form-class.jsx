
import {useRef, useEffect, useState} from "react"
import { FrappeForm } from "./frappe-form-class.js";
import { X } from "lucide-react";

class DeskFormClass extends FrappeForm {
  is_hide = true;
  has_footer = true;
  has_primary_action = true;
  base_url = "restaurant_management.restaurant_management.doctype.desk_form.desk_form.";

  constructor(options) {
    super(options);

    this.in_modal = !this.location;
    if (this.form_name) this.initialize();
  }

  remove() {
    this.$$wrapper.remove();
  }

  get $$wrapper() {
    if (this.in_modal) {
      // this._wrapper es frappe.ui.Dialog, .$wrapper es jQuery → extraer el DOM
      return this._wrapper.$wrapper[0];
    }
    // location mode: _wrapper es un DOM element
    return this._wrapper;
  }

  get parent() {
    return this.body;
  }

  get body() {
    if (this.in_modal) {
      return this._wrapper.$wrapper[0].querySelector('.modal-body');
    }
    return this._wrapper;
  }

  get footer() {
    if (this.in_modal) {
      return this._wrapper.$wrapper[0].querySelector('.modal-footer');
    }
    return this._wrapper;
  }

  get footer_buttons_wrapper() {
    return this.footer.querySelector('.standard-actions');
  }

  get primary_btn() {
    return this.footer.querySelector('.btn-primary');
  }

  get_primary_btn() {
    return this.primary_btn;
  }

  field(field_name) {
    return this.in_modal ? this._wrapper.fields_dict[field_name].$wrapper[0] : null;
  }

  get_value(fieldname) {
    if (Array.isArray(fieldname)) {
      return fieldname.map(field => this.get_value(field));
    }
    return super.get_value(fieldname);
  }

  async initialize() {
    if (this.location) {
      // location puede ser jQuery o DOM element
      const parent = this.location instanceof HTMLElement ? this.location : this.location[0];
      const div = document.createElement('div');
      div.className = 'desk-form';
      parent.appendChild(div);
      this._wrapper = div;
    } else {
      this._wrapper = new frappe.ui.Dialog({
        title: this.title,
        on_hide: () => {
          close_grid_and_dialog();
        }
      });
    }

    await super.initialize();

    function close_grid_and_dialog() {
      const openRow = document.querySelector(".grid-row-open");
      if (openRow) {
        const gridRow = $(openRow).data("grid_row"); // .data() sigue siendo Frappe/jQuery interno
        gridRow.toggle_view(false);
        return false;
      }

      if (cur_dialog && !cur_dialog.no_cancel_flag) {
        return false;
      }
    }

    if (this.in_modal && this._wrapper?.wrapper) {
      this._wrapper.wrapper.classList.add('modal-lg');
    }

    this.showEl(this.body);
    this.show();
  }

  execute_primary_action() {
    this.primary_btn?.focus();

    if (this.primary_action) {
      this.last_data ??= JSON.stringify(this.doc);
      if (this.last_data != JSON.stringify(this.doc)) {
        this.last_data = JSON.stringify(this.doc);
        this.primary_action();
      }
    } else {
      this.save();
    }
  }

  async make() {
    await super.make();

    this.customize();

    if (this.has_primary_action && this.in_modal) {
      const button = this.primary_btn;
      if (button) {
        button.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          this.execute_primary_action();
        });

        button.textContent = this.primary_action_label || __('Save');
        button.classList.remove('hide');
      }

      this.footer.classList.remove('hide');
      this.footer.style.display = 'flex';
    } else {
      this.hideEl(this.footer);
    }

    this.make_custom_buttons_wrapper();
  }

  customize() {
    this.body.classList.add('desk-form-body');
  }

  load() {
    this.before_load && this.before_load();
    super.initialize();
    this.initialize_fetches();
  }

  set_value(fieldname, value, on_reload = false) {
    const field = this.get_field(fieldname);
    if (field && typeof field.set_value === "function") {
      field.set_value(value);
    }
  }

  async reload(doc = null, from_server = false) {
    this.reloading = true;
    this.before_load && this.before_load();
    this.doc = doc || await this.get_doc(from_server);
    this.doc = JSON.parse(JSON.stringify(this.doc));

    this.refresh();
    this.customize();
    this.reloading = false;

    setTimeout(() => {
      if (typeof this.on_reload === "function") {
        this.on_reload();
      }
      this.reloading = false;
    }, 100);

    return this;
  }

  background_reload() {
    this.get_doc(true).then(doc => {
      this.doc = JSON.parse(JSON.stringify(doc));
      this.refresh();
    });
  }

  show() {
    this.is_hide = false;
    // _wrapper puede ser frappe.ui.Dialog (tiene .show()) o DOM element
    if (typeof this._wrapper.show === 'function') {
      this._wrapper.show();
    } else {
      this.showEl(this._wrapper);
    }
    return this;
  }

  hide() {
    this.is_hide = true;
    if (typeof this._wrapper.hide === 'function') {
      this._wrapper.hide();
    } else {
      this.hideEl(this._wrapper);
    }
    return this;
  }

  hide_field(fieldname) {
    if (Array.isArray(fieldname)) {
      fieldname.forEach(field => this.hide_field(field));
    } else {
      this.set_field_display(fieldname, true);
    }
  }

  super_container_field(fieldname) {
    const wrapper = this.get_field(fieldname)?.$wrapper?.[0];
    return wrapper?.parentElement?.parentElement;
  }

  show_field(fieldname) {
    if (Array.isArray(fieldname)) {
      fieldname.forEach(field => this.show_field(field));
    } else {
      this.set_field_display(fieldname, false);
    }
  }

  set_field_display(fieldname, hide) {
    const field = this.get_field(fieldname);
    if (field) {
      // $wrapper es jQuery, acceder al DOM element
      const el = field.$wrapper?.[0] || field.$wrapper;
      if (el) {
        el.style.display = hide ? 'none' : '';
      }
    }
  }

  toggle() {
    this.is_hide ? this.show() : this.hide();
    return this;
  }

  make_custom_buttons_wrapper() {
    const html = `
      <div class="widget-group custom-widget">
        <div class="widget-group-body grid-col-2"></div>
      </div>`;
    this.body.insertAdjacentHTML('beforeend', html);
  }

  // ---- Helpers vanilla ----

  showEl(el) {
    if (el) el.style.display = '';
  }

  hideEl(el) {
    if (el) el.style.display = 'none';
  }
}

/* this.edit_form = new DeskForm({
  doctype: "Restaurant Object",
  doc_name: this.data.name,
  form_name: this.data.type === "Table" ? "restaurant-table" : "restaurant-production-center",
  callback: (self) => {
    self.hide();
  },
  title: __(`Update ${this.data.type}`),
  field_properties: {
    type: { read_only: true },
    room: { read_only: true, hidden: true },
  }
}); */

export function DeskForm(props){
  const ref = useRef();
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  const onClose = () => {}

  useEffect(() => {
    new DeskFormClass({
      location: ref.current,
      doctype: props.doctype,
      doc_name: props.docName,
      form_name: props.formName,
      callback: (self) => {
        self.hide();
      },
      title: __(`Update ${props.docName}`),
      field_properties: {
        type: { read_only: true },
        room: { read_only: true, hidden: true },
      }
    });
  }, [])

  const handleSave = () => {}

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
            {props.formName}
          </h3>
          <button onClick={props.onClose}
            className="p-1.5 rounded-lg hover:bg-accent text-muted-foreground hover:text-foreground transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1" ref={ref}/>

        <div className="flex justify-end gap-2 px-5 py-3 border-t border-border shrink-0">
          <button onClick={props.onClose}
            className="px-4 py-2 text-sm rounded-lg text-muted-foreground hover:bg-accent transition-colors">
            {__('Cancel')}
          </button>
          <button onClick={handleSave} disabled={saving || loading}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
            {saving ? __('Saving...') : "Save"}
          </button>
        </div>
      </div>
    </div>
  )
}