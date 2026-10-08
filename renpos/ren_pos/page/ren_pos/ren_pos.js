// The React bundle is loaded only on this page (see hooks.py).
const RESTAURANT_ASSETS = "/assets/renpos/dist";

frappe.pages['ren-pos'].on_page_load = function (wrapper) {
  frappe.ui.make_app_page({
    parent: wrapper,
    title: '',
    single_column: true
  });

  const root = $(wrapper).find('.layout-main-section');
  root.append(`
    <div class="ren-pos h-full">
      <div id='restaurant-root' class="h-full"></div>
    </div>
  `);

  // frappe.require adds its own cache-busting version; don't add "?v=" here
  // (its extension detection breaks with query strings).
  // restaurant.js is an IIFE build that also injects its CSS.
  frappe.require(`${RESTAURANT_ASSETS}/js/restaurant.js`, function () {
    if (window.initRestaurantApp) {
      window.initRestaurantApp(document.getElementById('restaurant-root'), wrapper);
    } else {
      frappe.msgprint(__("The restaurant app could not be loaded. Run the frontend build (npm run build)."));
    }
  });
}
