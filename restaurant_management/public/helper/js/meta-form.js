/**
 * MetaForm — Uses Frappe's native rendering engine
 * 
 * Instead of DeskForm (custom DocType + custom endpoint + custom field handling),
 * this uses frappe.get_meta() + frappe.ui.Dialog which already handles:
 *   ✓ Dynamic Link resolution (via automatic Link conversion in grids)
 *   ✓ fetch_from
 *   ✓ Link field queries & filters
 *   ✓ Child tables
 *   ✓ depends_on / mandatory_depends_on
 *   ✓ All field types natively
 *   ✓ Permission checks
 * 
 * Usage:
 *   // POS context — uses form_views.js config for field selection
 *   MetaForm.view('REN Table', 'pos', 'TABLE-001', {
 *     onSave: (doc) => refreshTables()
 *   });
 * 
 *   // POS context — create new (no docname)
 *   MetaForm.view('REN Floor', 'pos', null, {
 *     defaults: { restaurant: 'Main' }
 *   });
 *
 *   // Create or edit — auto-detects if doc exists
 *   MetaForm.save('POS Profile User', userName, {
 *     defaults: { parent: posProfile, parenttype: 'POS Profile' },
 *     onSave: (doc) => reloadPermissions()
 *   });
 *
 *   // Edit existing doc
 *   MetaForm.edit('REN Table', 'TABLE-001', {
 *     fields: ['table_name', 'room', 'capacity', 'status'],
 *     title: 'Edit Table',
 *     onSave: (doc) => console.log('saved', doc)
 *   });
 * 
 *   // Create new doc
 *   MetaForm.create('REN Floor', {
 *     fields: ['floor_name', 'restaurant'],
 *     title: 'New Floor',
 *     defaults: { restaurant: 'Main Restaurant' },
 *     onSave: (doc) => console.log('created', doc)
 *   });
 * 
 *   // Full form (all fields from meta) — admin backend
 *   MetaForm.open('Restaurant Permission Manage', 'PERM-001');
 * 
 *   // With field overrides
 *   MetaForm.edit('REN Table', 'TABLE-001', {
 *     fields: ['table_name', 'room', 'capacity'],
 *     fieldProperties: {
 *       room: { read_only: 1 },
 *       capacity: { description: 'Max seats' }
 *     }
 *   });
 */

frappe.provide("frappe.ui");

class MetaForm {

  /**
   * Open a dialog to edit an existing document
   */
  static async edit(doctype, docname, opts = {}) {
    const instance = new MetaForm({ ...opts, doctype, docname });
    return instance.show();
  }

  /**
   * Open a dialog to create a new document
   */
  static async create(doctype, opts = {}) {
    const instance = new MetaForm({ ...opts, doctype, docname: null });
    return instance.show();
  }

  /**
   * Create or edit — auto-detects based on existence
   * If docname provided and exists → edit. Otherwise → create.
   */
  static async save(doctype, docname = null, opts = {}) {
    const instance = new MetaForm({ ...opts, doctype, docname, upsert: true });
    return instance.show();
  }

  /**
   * Open with all fields from meta
   */
  static async open(doctype, docname = null, opts = {}) {
    const instance = new MetaForm({ ...opts, doctype, docname });
    return instance.show();
  }

  /**
   * Open using a named view config
   * Merges view config (fields, fieldProperties, size) with opts
   */
  static async view(doctype, context = 'pos', docname = null, opts = {}) {
    const viewConfig = MetaForm.getView(doctype, context) || {};
    return MetaForm.save(doctype, docname, {
      ...viewConfig,
      ...opts,
    });
  }

  /**
   * Register form views config
   */
  static registerViews(views) {
    MetaForm._views = views;
  }

  /**
   * Get view config for a DocType + context
   */
  static getView(doctype, context = 'pos') {
    const views = MetaForm._views?.[doctype];
    if (!views) return null;
    return views[context] || views['default'] || null;
  }

  static _views = {};

  // ─── Instance ────────────────────────────────────────────────

  constructor(opts) {
    this.doctype = opts.doctype;
    this.key  = opts.key || opts.docname,
    this.docname = opts.docname;
    this.title = opts.title;
    this.fields = opts.fields;
    this.defaults = opts.defaults || {};
    this.fieldProperties = opts.fieldProperties || {};
    this.size = opts.size || '';
    this.onSave = opts.onSave;
    this.onDelete = opts.onDelete;
    this.afterLoad = opts.afterLoad;
    this.primaryLabel = opts.primaryLabel || __('Save');
    this.readOnly = opts.readOnly || false;
    this.upsert = opts.upsert || false;
    this.dialog = null;
    this.doc = null;
    this.isNew = false;
  }

  static _cache = new Map();

  static #getCacheKey(doctype, fieldKey, docname) {

      return `${doctype}::${fieldKey}::${docname || '__new__'}`;
  }

  async show() {
    const fieldKey = (this.fields || []).join("");
    const cacheKey = MetaForm.#getCacheKey(this.doctype, fieldKey, this.docname);
    const cached = MetaForm._cache.get(cacheKey);

    if (cached?.dialog && cached.dialog.$wrapper?.length) {
        // Reutilizar dialog existente
        this.dialog = cached.dialog;
        this.doc = cached.doc;
        this.isNew = cached.isNew;

        // Refrescar datos si es edición
        if (this.docname && !this.isNew) {
            await this.#loadDoc();
        }

        this.#setValues();
        this.dialog.show();
        this.#populateChildTables();
        this.afterLoad?.(this);
        return this;
    }

    // Crear nuevo
    await this.#loadMeta();
    await this.#loadDoc();

    const dialogFields = this.#buildFields();

    this.dialog = new frappe.ui.Dialog({
        title: this.title || (this.isNew ? __('New {0}', [this.doctype]) : __('Edit {0}', [this.doctype])),
        fields: dialogFields,
        size: this.size,
        primary_action_label: this.readOnly ? null : this.primaryLabel,
        primary_action: this.readOnly ? null : (values) => this.#save(values),
    });

    // Guardar en cache
    MetaForm._cache.set(cacheKey, {
        dialog: this.dialog,
        doc: this.doc,
        isNew: this.isNew,
    });

    // Limpiar cache si se destruye manualmente
    this.dialog.onhide = () => {
        // No destruir, solo ocultar (ya es el default)
    };

    this.#setValues();
    this.dialog.show();
    this.#populateChildTables();
    this.afterLoad?.(this);

    return this;
  }

  // ─── Private ─────────────────────────────────────────────────

  async #loadMeta() {
    await new Promise((resolve, reject) => {
      frappe.model.with_doctype(this.doctype, resolve, reject);
    });

    const meta = frappe.get_meta(this.doctype);
    const tableFields = meta.fields.filter(df => df.fieldtype === 'Table' && df.options);

    for (const df of tableFields) {
      if (!this.fields || this.fields.includes(df.fieldname)) {
        await new Promise((resolve, reject) => {
          frappe.model.with_doctype(df.options, resolve, reject);
        });
      }
    }
  }

  async #loadDoc() {
    if (this.docname) {
      if (this.upsert) {
        try {
          const exists = await frappe.db.exists(this.doctype, this.docname);
          if (exists) {
            this.doc = await frappe.db.get_doc(this.doctype, this.docname);
            this.isNew = false;
          } else {
            this.doc = frappe.model.get_new_doc(this.doctype);
            this.doc.name = this.docname;
            this.isNew = true;
          }
        } catch {
          this.doc = frappe.model.get_new_doc(this.doctype);
          this.doc.name = this.docname;
          this.isNew = true;
        }
      } else {
        this.doc = await frappe.db.get_doc(this.doctype, this.docname);
        this.isNew = false;
      }
    } else {
      this.doc = frappe.model.get_new_doc(this.doctype);
      this.isNew = true;
    }

    for (const [key, value] of Object.entries(this.defaults)) {
      if (this.isNew || this.doc[key] === undefined || this.doc[key] === null) {
        this.doc[key] = value;
      }
    }
  }

  #buildFields() {
    const meta = frappe.get_meta(this.doctype);
    const NO_VALUE = new Set([
      'Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button', 'Fold',
    ]);
    const LAYOUT_TYPES = new Set(['Section Break', 'Column Break', 'Tab Break']);
    const SKIP = new Set(['amended_from', 'amendment_date']);

    let metaFields = meta.fields;

    if (this.fields) {
      const requested = new Set(this.fields);
      metaFields = this.#filterFieldsWithLayout(metaFields, requested);
    } else {
      metaFields = metaFields.filter(df =>
        LAYOUT_TYPES.has(df.fieldtype) ||
        (!df.hidden && !df.is_virtual && !SKIP.has(df.fieldname))
      );
    }

    return metaFields.map(df => {
      const field = { ...df };

      const overrides = this.fieldProperties[df.fieldname];
      if (overrides) {
        Object.assign(field, overrides);
      }

      if (this.readOnly && !NO_VALUE.has(field.fieldtype)) {
        field.read_only = 1;
      }

      // ─── Table fields: build child grid with Dynamic Link conversion ───
      if (field.fieldtype === 'Table' && field.options) {
        this.#buildTableField(field);
      }

      return field;
    });
  }

  #buildTableField(field) {
    const childMeta = frappe.get_meta(field.options);
    if (!childMeta) return;

    const dynamicLinkMap = {};
    const dynamicLinkSources = new Set();

    for (const cf of childMeta.fields) {
      if (cf.fieldtype === 'Dynamic Link' && cf.options) {
        dynamicLinkMap[cf.fieldname] = cf.options;
        dynamicLinkSources.add(cf.options);
      }
    }

    // Map: linkFieldname → [{ target, source }]  for fetch_from resolution
    const fetchMap = {};
    for (const cf of childMeta.fields) {
      if (!cf.fetch_from) continue;
      const [linkField, sourceField] = cf.fetch_from.split('.');
      if (!linkField || !sourceField) continue;
      fetchMap[linkField] ??= [];
      fetchMap[linkField].push({ target: cf.fieldname, source: sourceField });
    }

    field.fields = childMeta.fields
      .filter(f =>
        f.in_list_view ||
        f.reqd ||
        f.fetch_from ||
        f.fieldtype === 'Dynamic Link' ||
        dynamicLinkSources.has(f.fieldname)
      )
      .map(f => {
        const cf = { ...f, in_list_view: 1 };

        if (f.fetch_from) cf.read_only = 1;

        const childOverrides = this.fieldProperties[`${field.fieldname}.${f.fieldname}`];
        if (childOverrides) {
          Object.assign(cf, childOverrides);
        }

        if (cf.fieldtype === 'Dynamic Link') {
          cf.fieldtype = 'Link';
          cf.options = "";
          cf._was_dynamic_link = true;
          cf._source_fieldname = dynamicLinkMap[f.fieldname];
        }

        return cf;
      });

    const dialogRef = () => this.dialog;
    const tableFieldname = field.fieldname;

    for (const cf of field.fields) {
      const fname = cf.fieldname;

      // ━━━ Source fields for Dynamic Links ━━━
      // When user selects e.g. "Customer" in party_type,
      // find all Dynamic Link targets on the same row and update their df.options
      if (dynamicLinkSources.has(fname)) {
        const dependentFields = [];
        for (const [dlName, srcName] of Object.entries(dynamicLinkMap)) {
          if (srcName === fname) dependentFields.push(dlName);
        }

        cf.onchange = function () {
          const value = this.get_value();
          const gridRow = this.grid_row;
          if (!gridRow || !gridRow.doc) return;

          gridRow.doc[fname] = value;

          // Update each dependent Dynamic Link (now a plain Link) field's options
          for (const dlFieldname of dependentFields) {
            // Find the control on this grid row
            const targetCtrl = gridRow.on_grid_fields.find(
              f => f.df.fieldname === dlFieldname
            );
            if (targetCtrl) {
              targetCtrl.df.options = value || "";
              targetCtrl.refresh();
            }

            // Clear stale value — doctype changed, old reference is invalid
            if (gridRow.doc[dlFieldname]) {
              gridRow.doc[dlFieldname] = '';
            }
          }

          gridRow.refresh();
        };
      }

      // ━━━ Fields with fetch_from targets ━━━
      if (fetchMap[fname]) {
        const targets = fetchMap[fname];
        const prevOnchange = cf.onchange;

        cf.onchange = function () {
          if (prevOnchange) prevOnchange.call(this);

          const value = this.get_value();
          const gridRow = this.grid_row;
          const rowDoc = gridRow?.doc;
          if (rowDoc) rowDoc[fname] = value;

          if (!value) {
            for (const t of targets) {
              if (rowDoc) rowDoc[t.target] = '';
            }
            gridRow?.refresh();
            return;
          }

          // Determine the doctype to fetch from
          let doctype;
          if (dynamicLinkMap[fname]) {
            // This field itself was a Dynamic Link — get doctype from source
            doctype = rowDoc?.[dynamicLinkMap[fname]] || '';
          } else {
            doctype = cf.options;
          }
          if (!doctype) return;

          frappe.call({
            method: 'frappe.client.get_value',
            args: {
              doctype: doctype,
              filters: { name: value },
              fieldname: targets.map(t => t.source),
            },
            no_spinner: true,
            callback: function (r) {
              if (!r.message) return;
              for (const t of targets) {
                if (rowDoc) rowDoc[t.target] = r.message[t.source] || '';
              }
              gridRow?.refresh();
            },
          });
        };
      }

      // ━━━ Default: flush all field changes to row doc ━━━
      if (!cf.onchange) {
        cf.onchange = function () {
          const gridRow = this.grid_row;
          if (gridRow?.doc) {
            gridRow.doc[fname] = this.get_value();
          }
        };
      }
    }

    const doc = this.doc;
    field.get_data = () => doc?.[tableFieldname] ?? [];
    field.data = [];

    if (this.readOnly) {
      field.cannot_add_rows = true;
      field.cannot_delete_rows = true;
    }
  }

  /**
   * Include requested fields + layout fields around them for proper structure
   */
  #filterFieldsWithLayout(allFields, requested) {
    const result = [];
    let lastSection = null;
    let lastColumn = null;
    let sectionHasFields = false;
    let columnHasFields = false;

    for (const df of allFields) {
      if (df.fieldtype === 'Section Break' || df.fieldtype === 'Tab Break') {
        lastSection = df;
        lastColumn = null;
        sectionHasFields = false;
        columnHasFields = false;
        continue;
      }

      if (df.fieldtype === 'Column Break') {
        lastColumn = df;
        columnHasFields = false;
        continue;
      }

      if (requested.has(df.fieldname)) {
        if (lastSection && !sectionHasFields) {
          result.push({ ...lastSection });
          sectionHasFields = true;
        }
        if (lastColumn && !columnHasFields) {
          result.push({ ...lastColumn });
          columnHasFields = true;
        }
        result.push(df);
      }
    }

    return result;
  }

  #setValues() {
    if (!this.doc || !this.dialog) return;

    const values = {};
    for (const field of this.dialog.fields) {
      if (field.fieldtype === 'Table') continue;
      if (field.fieldname && this.doc[field.fieldname] !== undefined) {
        values[field.fieldname] = this.doc[field.fieldname];
      }
    }

    this.dialog.set_values(values);
  }

  /**
   * Populate child tables after dialog is rendered.
   * 
   * After adding rows, we also need to sync Dynamic Link options
   * for existing data — e.g. if loading a doc where party_type="Customer",
   * the party field's df.options must be set to "Customer" on each row.
   */
  #populateChildTables() {
    for (const field of this.dialog.fields) {
      if (field.fieldtype !== 'Table') continue;

      const grid = this.dialog.fields_dict[field.fieldname]?.grid;
      if (!grid) continue;

      const childDoctype = field.options;

      const origAddRow = grid.add_new_row.bind(grid);
      grid.add_new_row = function () {
        const result = origAddRow.apply(this, arguments);
        const lastRow = grid.grid_rows?.[grid.grid_rows.length - 1];
        if (lastRow?.doc) {
          lastRow.doc.doctype = childDoctype;
        }
        return result;
      };

      const data = this.doc[field.fieldname];
      if (!data || !data.length) continue;

      // Clear and rebuild
      grid.df.data = [];
      grid.refresh();

      for (let i = 0; i < data.length; i++) {
        grid.add_new_row();
        const gridRow = grid.grid_rows[grid.grid_rows.length - 1];
        if (!gridRow) continue;

        const rowData = data[i];
        for (const key in rowData) {
          if (rowData[key] !== undefined && key !== 'name'
            && key !== 'parent' && key !== 'parenttype' && key !== 'parentfield') {
            gridRow.doc[key] = rowData[key];
          }
        }
      }

      grid.refresh();

      // ━━━ Sync Dynamic Link options for loaded data ━━━
      // For each row, find converted Dynamic Link fields and set their
      // df.options based on the source field's current value in that row.
      this.#syncDynamicLinkOptionsForGrid(field, grid);
    }
  }

  /**
   * After populating grid rows with data, update df.options on each
   * converted Dynamic Link field to match the source field's value.
   * 
   * Without this, a loaded row with party_type="Customer" would show
   * the party Link field pointing at "DocType" (the default) instead
   * of "Customer", so the link dropdown would show wrong results.
   */
  #syncDynamicLinkOptionsForGrid(field, grid) {
    // Find which fields were converted from Dynamic Link
    const convertedFields = (field.fields || []).filter(f => f._was_dynamic_link);
    if (!convertedFields.length) return;

    for (const gridRow of (grid.grid_rows || [])) {
      if (!gridRow.doc) continue;

      for (const cf of convertedFields) {
        const sourceFieldname = cf._source_fieldname;
        const resolvedDoctype = gridRow.doc[sourceFieldname];

        if (resolvedDoctype) {
          // Find the actual control on this rendered row
          const ctrl = gridRow.on_grid_fields?.find(
            f => f.df.fieldname === cf.fieldname
          );
          if (ctrl) {
            ctrl.df.options = resolvedDoctype;
            ctrl.refresh();
          }
        }
      }
    }
  }

  async #save(values) {
    try {
      Object.assign(this.doc, values);

      for (const field of this.dialog.fields) {
        if (field.fieldtype === 'Table') {
          const grid = this.dialog.fields_dict[field.fieldname]?.grid;
          if (grid) {
            this.doc[field.fieldname] = grid.get_data();
          }
        }
      }

      let savedDoc;

      if (this.isNew) {
        this.doc.doctype = this.doctype;
        savedDoc = await frappe.call({
          method: 'frappe.client.insert',
          args: { doc: this.doc },
          freeze: true,
        });
      } else {
        savedDoc = await frappe.call({
          method: 'frappe.client.save',
          args: { doc: this.doc },
          freeze: true,
        });
      }

      const doc = savedDoc.message;
      frappe.show_alert({
        message: __("{0} saved", [doc.name]),
        indicator: "green",
      });

      this.dialog.hide();
      this.onSave?.(doc);

    } catch (err) {
      console.error('MetaForm save error:', err);
    }
  }

  hide() {
    this.dialog?.hide();
  }

  get_value(fieldname) {
    return this.dialog?.get_value(fieldname);
  }

  set_value(fieldname, value) {
    return this.dialog?.set_value(fieldname, value);
  }

  get_field(fieldname) {
    return this.dialog?.fields_dict?.[fieldname];
  }

  set_df_property(fieldname, prop, value) {
    this.dialog?.set_df_property(fieldname, prop, value);
  }
}

frappe.ui.MetaForm = MetaForm;