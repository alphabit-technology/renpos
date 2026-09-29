const API_BASE = "restaurant_management.restaurant_management.page.restaurant_manage.restaurant_manage."

export async function callApi(method, args = {}) {
  try {
    const response = await frappe.call({
      method: `${API_BASE}${method}`,
      args
    })
    return response.message
  } catch (error) {
    console.error(`API Error (${method}):`, error)
    throw error
  }
}

export async function callMethod(method, args = {}) {
  try {
    const response = await frappe.call({
      method,
      args
    })
    return response.message
  } catch (error) {
    console.error(`API Error (${method}):`, error)
    throw error
  }
}

// Para operaciones CRUD directas
export const api = {
  getValue: (doctype, name, fieldname) => 
    callMethod('frappe.client.get_value', { doctype, name, fieldname }),
  
  setValue: (doctype, name, fieldname, value) =>
    callMethod('frappe.client.set_value', { doctype, name, fieldname, value }),
  
  getDoc: (doctype, name) =>
    callMethod('frappe.client.get', { doctype, name }),
  
  getList: (doctype, filters = {}, fields = ['*'], limit = 0) =>
    callMethod('frappe.client.get_list', { doctype, filters, fields, limit_page_length: limit }),
}

export default api