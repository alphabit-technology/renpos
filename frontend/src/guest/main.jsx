// Guest ordering page (/order): its own small bundle, dist/js/guest.js (vite build --mode guest).
import React from "react";
import ReactDOM from "react-dom/client";
import GuestApp from "./GuestApp";
import "./guest.css";

// the shared components translate with Frappe's __(); the guest page has no desk
if (typeof window.__ !== "function") {
  window.__ = (text, args) => (args ? String(text).replace(/\{(\d+)\}/g, (m, i) => (args[i] ?? m)) : text);
}

window.initGuestOrder = (container, boot) => {
  const root = ReactDOM.createRoot(container);
  root.render(
    <React.StrictMode>
      <GuestApp boot={boot || {}} />
    </React.StrictMode>
  );
  return root;
};
