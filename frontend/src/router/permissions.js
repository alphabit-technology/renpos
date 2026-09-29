/**
 * Restaurant permission helper
 * Uses server-resolved permissions from RestaurantSettings.settings_data()
 */

let _rm = null;

export function initPermissions(rm) {
  _rm = rm;
}

// ─── Map PERMISSIONS doctype → RM.permissions key ────────────

const PERM_KEY_MAP = {
  'Ren Floor':      'ren_floor',
  'Ren Room':       'ren_room',
  'Ren Table':      'ren_table',
  'Ren Station':    'ren_station',
  'Table Order':    'order',
  'Sales Invoice':  'invoice',
};

// ─── Role checks ─────────────────────────────────────────────

export function hasRole(role) {
  if (Array.isArray(role)) {
    return role.some(r => frappe.user_roles.includes(r));
  }
  return frappe.user_roles.includes(role);
}

export function isAdmin() {
  return hasRole(['System Manager', 'Administrator']);
}

// ─── Core check ──────────────────────────────────────────────

export function checkPermission(rule) {
  if (!rule) return true;

  const { doctype, perm, roles, custom, all } = rule;
  const checks = [];

  if (doctype && perm) {
    // Permissions come from the server keyed by doctype (init_restaurant).
    return _rm?.permissions?.[doctype]?.[perm]
  }

  if (roles) {
    checks.push(hasRole(roles));
  }

  if (typeof custom === 'function') {
    checks.push(custom());
  }

  if (checks.length === 0) return true;

  return all ? checks.every(Boolean) : checks.some(Boolean);
}

// ─── Permission map ──────────────────────────────────────────

export const PERMISSIONS = {
  'floor':           { doctype: 'Ren Floor', perm: 'read' },
  'floor.write':     { doctype: 'Ren Floor', perm: 'write' },
  'floor.create':    { doctype: 'Ren Floor', perm: 'create' },

  'room':            { doctype: 'Ren Room', perm: 'read' },
  'room.write':      { doctype: 'Ren Room', perm: 'write' },
  'room.create':     { doctype: 'Ren Room', perm: 'create' },
  'room.delete':     { doctype: 'Ren Room', perm: 'delete' },

  'table':           { doctype: 'Ren Table', perm: 'read' },
  'table.write':     { doctype: 'Ren Table', perm: 'write' },
  'table.create':    { doctype: 'Ren Table', perm: 'create' },
  'table.delete':    { doctype: 'Ren Table', perm: 'delete' },

  'station':         { doctype: 'Ren Station', perm: 'read' },
  'station.write':   { doctype: 'Ren Station', perm: 'write' },
  'station.create':  { doctype: 'Ren Station', perm: 'create' },
  'station.delete':  { doctype: 'Ren Station', perm: 'delete' },

  'order':           { doctype: 'Table Order', perm: 'read' },
  'order.create':    { doctype: 'Table Order', perm: 'create' },
  'order.write':     { doctype: 'Table Order', perm: 'write' },

  'menu':           { doctype: 'Restaurant Menu', perm: 'read' },
  'menu.create':    { doctype: 'Restaurant Menu', perm: 'create' },
  'menu.write':     { doctype: 'Restaurant Menu', perm: 'write' }
};

export function can(name) {
  const rule = PERMISSIONS[name];
  if (!rule) {
    console.warn(`Unknown permission: "${name}"`);
    return false;
  }
  return checkPermission(rule);
}

export const generalCustomAccess = () => {
  const docs = ["room", "table", "station"];
  const permissions = ["create", "write", "delete"];
  for (const doc of docs) {
    for (const perm of permissions) {
      const key = `${doc}.${perm}`;
      if (PERMISSIONS[key] && can(key)) {
        return true;
      }
    }
  }
  return false;
};

export const canOpenOrderManage = (table) => {
  if (frappe.session.user === "Administrator" || canPay()) return true;
  if(!_rm) return false;

  if (table.current_user !== frappe.session.user && table.orders_count > 0) {
    if (_rm.restrictions?.restricted_to_owner_table) {
      return checkPermissions("order", "manage");
    }
  }

  return true;
}

export const canPay = () => {
  return checkPermissions("invoice", "create");
}

export const checkPermissions = (model = null, action, record = null) => {
  if (frappe.session.user === "Administrator") return true;
  if(!_rm) return false;

  let r = false;

  if (model != null) {
    let modelInPermissions = _rm.permissions[model];
    if (typeof modelInPermissions != "undefined" && typeof modelInPermissions[action] !== "undefined") {
      r = _rm.permissions[model][action];
    }

    const exception = () => {
      r = false;
      (_rm.exceptions || []).map(e => {
        r = e[model + "_" + action] === 1;
      });
    }

    if (record == null) {
      if (!r) {
        exception();
      }
    } else {
      if (record.data.owner !== frappe.session.user) {
        if (model === "order" && _rm.restrictions?.restricted_to_owner_order) {
          exception();
        }
        if (model === "table" && _rm.restrictions?.restricted_to_owner_table) {
          exception();
        }
      }
    }

    if (model === 'pos' && r) {
      r = _rm.pos_profile?.["allow_" + action] === 1;
    }
  }

  return r;
}