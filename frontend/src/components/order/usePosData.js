/**
 * usePosData — Pre-load POS configuration and item catalog.
 *
 * Called ONCE when OrderManager opens.
 * Returns everything needed for client-side calculations:
 * items, prices, taxes, currency, permissions.
 */
import { setEditableStatuses } from "./statuses";
import { useState, useEffect, useCallback, useRef } from "react";
import OrderAPI from "./api";

export default function usePosData(posProfile) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const cacheRef = useRef(null);

  const load = useCallback(async () => {
    if (!posProfile) return;

    // Return cached if same profile
    if (cacheRef.current?.posProfile === posProfile) {
      setData(cacheRef.current.data);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await OrderAPI.getPosData(posProfile);

      // Index items by item_code for fast lookup
      const itemsByCode = {};
      for (const item of result.items || []) {
        itemsByCode[item.item_code] = item;
      }

      setEditableStatuses(result.editable_statuses);
      const posData = {
        // Config
        posProfile: result.pos_profile || posProfile,
        currency: result.currency || "USD",
        taxInclusive: result.tax_inclusive || false,
        allowDiscountChange: result.allow_discount_change ?? true,
        allowRateChange: result.allow_rate_change ?? true,
        isManager: !!result.is_manager,
        receiptPrinter: result.receipt_printer || null,

        // Items catalog
        items: result.items || [],
        itemsByCode,
        itemGroups: result.item_groups || [],
        // { group_name: { name, title, min_select, max_select, options } }
        modifierGroups: result.modifier_groups || {},
        modifierModes: result.modifier_modes || [],

        // Pricing
        priceList: result.price_list || "",
        pricingRules: result.pricing_rules || [],

        // Taxes
        taxTemplate: result.taxes || {},

        // Payments
        payments: result.payments || [],

        // Permissions
        permissions: result.permissions || {},
      };

      cacheRef.current = { posProfile, data: posData };
      setData(posData);
    } catch (err) {
      console.error("Failed to load POS data:", err);
      setError(err);
    }

    setLoading(false);
  }, [posProfile]);

  useEffect(() => {
    load();
  }, [load]);

  /**
   * Find item data by code from pre-loaded catalog.
   * Returns full item with price_list_rate, item_tax_rate, etc.
   */
  const getItem = useCallback(
    (itemCode) => data?.itemsByCode?.[itemCode] || null,
    [data]
  );

  /**
   * Force reload (e.g., after price change notification)
   */
  const reload = useCallback(() => {
    cacheRef.current = null;
    load();
  }, [load]);

  return {
    posData: data,
    loading,
    error,
    getItem,
    reload,
  };
}