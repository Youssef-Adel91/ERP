"use client";

import { useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  ShoppingCart,
  Loader2,
  AlertCircle,
  Search,
  Plus,
  Minus,
  Trash2,
  Wallet,
  LogOut,
  Package,
  CheckCircle2,
  History,
  Undo2,
  X,
} from "lucide-react";

// ── Types (mirrors backend app/modules/pos/api.py) ───────────────────────────

interface PosCatalogEntry {
  item_id: string;
  variant_id: string;
  sku: string;
  name: string;
  price: string;
}

interface CashShift {
  id: string;
  status: "OPEN" | "CLOSED";
  opening_balance: string;
  closing_balance: string | null;
  expected_balance: string | null;
  variance: string | null;
  opened_at: string;
  closed_at: string | null;
}

interface CartLine {
  item_id: string;
  variant_id: string;
  sku: string;
  name: string;
  unit_price: number;
  qty: number;
}

interface PosSaleRow {
  id: string;
  invoice_id: string;
  invoice_number: string;
  cashier_id: string;
  amount: string;
  payment_method: string;
  created_at: string;
  is_refund: boolean;
}

export default function PosPage() {
  const [cart, setCart] = useState<CartLine[]>([]);
  const [search, setSearch] = useState("");
  const [checkoutError, setCheckoutError] = useState("");
  const [lastReceipt, setLastReceipt] = useState<{ invoice_number: string; grand_total: string } | null>(null);

  const queryClient = useQueryClient();

  // One key per checkout attempt (survives a manual retry of the SAME
  // cart after a network error/timeout, so a double-tap or a client retry
  // can't ring up the sale twice server-side — see backend
  // app/modules/pos/api.py::checkout Idempotency-Key handling). Cleared on
  // success (new cart) so the next sale gets a fresh key.
  const checkoutIdempotencyKeyRef = useRef<string | null>(null);

  const { data: shift, isLoading: shiftLoading } = useQuery({
    queryKey: ["pos-current-shift"],
    queryFn: async () => {
      const res = await apiClient.get<CashShift | null>("/pos/shifts/current");
      return res.data;
    },
  });

  const { data: catalog, isLoading: catalogLoading, isError: catalogError } = useQuery({
    queryKey: ["pos-catalog"],
    queryFn: async () => {
      const res = await apiClient.get<PosCatalogEntry[]>("/pos/catalog");
      return res.data;
    },
    enabled: !!shift,
  });

  const filteredCatalog = useMemo(() => {
    if (!catalog) return [];
    const q = search.trim().toLowerCase();
    if (!q) return catalog;
    return catalog.filter(
      (c) => c.name.toLowerCase().includes(q) || c.sku.toLowerCase().includes(q)
    );
  }, [catalog, search]);

  const cartTotal = useMemo(
    () => cart.reduce((sum, line) => sum + line.unit_price * line.qty, 0),
    [cart]
  );

  const addToCart = (entry: PosCatalogEntry) => {
    setLastReceipt(null);
    setCart((prev) => {
      const existing = prev.find((l) => l.variant_id === entry.variant_id);
      if (existing) {
        return prev.map((l) =>
          l.variant_id === entry.variant_id ? { ...l, qty: l.qty + 1 } : l
        );
      }
      return [
        ...prev,
        {
          item_id: entry.item_id,
          variant_id: entry.variant_id,
          sku: entry.sku,
          name: entry.name,
          unit_price: Number(entry.price),
          qty: 1,
        },
      ];
    });
  };

  const updateQty = (variant_id: string, delta: number) => {
    setCart((prev) =>
      prev
        .map((l) => (l.variant_id === variant_id ? { ...l, qty: l.qty + delta } : l))
        .filter((l) => l.qty > 0)
    );
  };

  const removeLine = (variant_id: string) => {
    setCart((prev) => prev.filter((l) => l.variant_id !== variant_id));
  };

  const checkoutMutation = useMutation({
    mutationFn: async () => {
      if (!shift) throw new Error("no shift");
      checkoutIdempotencyKeyRef.current ??= crypto.randomUUID();
      const res = await apiClient.post(
        "/pos/checkout",
        {
          shift_id: shift.id,
          lines: cart.map((l) => ({
            item_id: l.item_id,
            variant_id: l.variant_id,
            qty: l.qty,
            unit_price: l.unit_price,
          })),
        },
        { headers: { "Idempotency-Key": checkoutIdempotencyKeyRef.current } }
      );
      return res.data as { invoice_number: string; grand_total: string };
    },
    onSuccess: (data) => {
      checkoutIdempotencyKeyRef.current = null;
      setCheckoutError("");
      setLastReceipt(data);
      setCart([]);
      queryClient.invalidateQueries({ queryKey: ["pos-current-shift"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setCheckoutError(pickDetail(err, "تعذر إتمام عملية البيع."));
    },
  });

  if (shiftLoading) {
    return (
      <div className="flex items-center justify-center h-[70vh] text-on-surface-variant gap-2">
        <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
      </div>
    );
  }

  if (!shift) {
    return <OpenShiftPanel onOpened={() => queryClient.invalidateQueries({ queryKey: ["pos-current-shift"] })} />;
  }

  return (
    <div className="h-[calc(100vh-7rem)] flex flex-col gap-3">
      <ShiftBar shift={shift} onClosed={() => queryClient.invalidateQueries({ queryKey: ["pos-current-shift"] })} />

      <div className="grid grid-cols-[1fr_380px] gap-3 flex-1 min-h-0">
        {/* Items grid — right side in RTL */}
        <div className="glass-card rounded-xl p-4 flex flex-col min-h-0">
          <div className="relative mb-3">
            <Search className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ابحث بالاسم أو الكود..."
              className="input-field pr-9"
            />
          </div>

          {catalogLoading ? (
            <div className="flex-1 flex items-center justify-center text-on-surface-variant gap-2">
              <Loader2 className="w-5 h-5 animate-spin" /> جاري تحميل المنتجات...
            </div>
          ) : catalogError ? (
            <div className="flex-1 flex items-center justify-center gap-2 text-body-sm text-error">
              <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل المنتجات.
            </div>
          ) : filteredCatalog.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-on-surface-variant gap-2">
              <Package className="w-7 h-7 text-outline-variant" />
              <p className="text-body-sm">لا توجد منتجات مطابقة.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-3 overflow-y-auto content-start flex-1">
              {filteredCatalog.map((entry) => (
                <button
                  key={entry.variant_id}
                  onClick={() => addToCart(entry)}
                  className="text-right p-3 rounded-lg border border-outline-variant/40 bg-surface-container-lowest hover:border-primary hover:bg-primary-container/5 transition-colors flex flex-col gap-2"
                >
                  <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
                    <Package className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-body-sm font-semibold text-on-surface line-clamp-2">{entry.name}</p>
                    <p className="text-[11px] text-outline font-data-mono" dir="ltr">{entry.sku}</p>
                  </div>
                  <p className="text-body-md font-bold font-data-mono text-primary" dir="ltr">
                    {entry.price} EGP
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Cart / ticket — left side in RTL */}
        <div className="glass-card rounded-xl p-4 flex flex-col min-h-0">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-9 h-9 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center">
              <ShoppingCart className="w-4 h-4" />
            </div>
            <h2 className="font-headline-sm text-headline-sm text-on-surface">الفاتورة الحالية</h2>
          </div>

          {cart.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-on-surface-variant gap-2">
              <ShoppingCart className="w-7 h-7 text-outline-variant" />
              <p className="text-body-sm">السلة فارغة. اختر منتجًا من القائمة.</p>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto divide-y divide-outline-variant/30">
              {cart.map((line) => (
                <div key={line.variant_id} className="py-2.5 flex items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-body-sm font-medium text-on-surface truncate">{line.name}</p>
                    <p className="text-[11px] text-outline font-data-mono" dir="ltr">
                      {line.unit_price} × {line.qty} = {(line.unit_price * line.qty).toFixed(2)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => updateQty(line.variant_id, -1)}
                      className="w-7 h-7 rounded-md bg-surface-container flex items-center justify-center hover:bg-error-container hover:text-on-error-container transition-colors"
                    >
                      <Minus className="w-3.5 h-3.5" />
                    </button>
                    <span className="w-6 text-center text-body-sm font-data-mono" dir="ltr">{line.qty}</span>
                    <button
                      onClick={() => updateQty(line.variant_id, 1)}
                      className="w-7 h-7 rounded-md bg-surface-container flex items-center justify-center hover:bg-primary-container/20 hover:text-primary transition-colors"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => removeLine(line.variant_id)}
                      className="w-7 h-7 rounded-md flex items-center justify-center text-error hover:bg-error-container transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="pt-3 mt-2 border-t border-outline-variant/40 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-body-md font-semibold text-on-surface-variant">الإجمالي</span>
              <span className="text-headline-sm font-headline-sm font-data-mono text-on-surface" dir="ltr">
                {cartTotal.toFixed(2)} EGP
              </span>
            </div>

            {checkoutError && (
              <div className="flex items-center gap-2 bg-error-container text-on-error-container p-2.5 rounded-lg text-body-sm font-medium">
                <AlertCircle className="w-4 h-4 shrink-0" /> {checkoutError}
              </div>
            )}
            {lastReceipt && (
              <div className="flex items-center gap-2 bg-success-bg text-success p-2.5 rounded-lg text-body-sm font-medium">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                تمت الفاتورة {lastReceipt.invoice_number} — {lastReceipt.grand_total} EGP
              </div>
            )}

            <button
              onClick={() => checkoutMutation.mutate()}
              disabled={cart.length === 0 || checkoutMutation.isPending}
              className="w-full h-14 rounded-xl bg-primary text-on-primary font-bold text-headline-sm flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {checkoutMutation.isPending ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Wallet className="w-5 h-5" />
              )}
              الدفع وإتمام البيع
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Shift bar (top strip while a shift is open) ──────────────────────────────

function ShiftBar({ shift, onClosed }: { shift: CashShift; onClosed: () => void }) {
  const [showClose, setShowClose] = useState(false);
  const [showSales, setShowSales] = useState(false);

  return (
    <div className="glass-card rounded-xl px-4 py-2.5 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <span className="px-2 py-1 rounded text-[11px] font-bold bg-success-bg text-success">وردية مفتوحة</span>
        <span className="text-body-sm text-on-surface-variant">
          رصيد الافتتاح:{" "}
          <span className="font-data-mono text-on-surface" dir="ltr">{shift.opening_balance} EGP</span>
        </span>
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={() => setShowSales(true)}
          className="flex items-center gap-1.5 h-9 px-3 rounded-lg text-body-sm font-semibold text-on-surface-variant hover:bg-surface-container transition-colors"
        >
          <History className="w-4 h-4" /> مبيعات الوردية
        </button>
        <button
          onClick={() => setShowClose(true)}
          className="flex items-center gap-1.5 h-9 px-3 rounded-lg text-body-sm font-semibold text-error hover:bg-error-container transition-colors"
        >
          <LogOut className="w-4 h-4" /> إغلاق الوردية
        </button>
      </div>

      {showClose && (
        <CloseShiftModal shift={shift} onClose={() => setShowClose(false)} onClosed={onClosed} />
      )}
      {showSales && <ShiftSalesModal shift={shift} onClose={() => setShowSales(false)} />}
    </div>
  );
}

// ── Shift sales history + refund ─────────────────────────────────────────────

function ShiftSalesModal({ shift, onClose }: { shift: CashShift; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [refundTarget, setRefundTarget] = useState<PosSaleRow | null>(null);

  const { data: sales, isLoading, isError } = useQuery({
    queryKey: ["pos-shift-sales", shift.id],
    queryFn: async () => {
      const res = await apiClient.get<PosSaleRow[]>(`/pos/shifts/${shift.id}/sales`);
      return res.data;
    },
  });

  // Rendered via a portal into document.body: ShiftBar's own wrapper (the
  // "glass-card" class, which sets backdrop-filter) establishes a new CSS
  // stacking context, which traps a plain `fixed` descendant instead of
  // truly overlaying the whole viewport — confirmed live: without the
  // portal, this modal was reachable in the DOM/accessibility tree but
  // visually painted BEHIND the catalog grid panel (a later DOM sibling at
  // the same stacking level), so clicks on it landed on the grid instead.
  // Escaping to document.body sidesteps the ancestor's stacking context
  // entirely, matching the standard fix for this exact backdrop-filter/
  // fixed-position interaction.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div
        className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding space-y-4 max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">مبيعات الوردية الحالية</h3>
          <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-surface-container transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {isLoading ? (
          <div className="flex-1 flex items-center justify-center text-on-surface-variant gap-2 py-8">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 text-body-sm text-error py-4">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل مبيعات الوردية.
          </div>
        ) : !sales || sales.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-on-surface-variant gap-2 py-8">
            <ShoppingCart className="w-7 h-7 text-outline-variant" />
            <p className="text-body-sm">لا توجد مبيعات على هذه الوردية بعد.</p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto divide-y divide-outline-variant/30">
            {sales.map((sale) => (
              <div key={sale.id} className="py-2.5 flex items-center gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-body-sm font-medium text-on-surface truncate" dir="ltr">
                    {sale.invoice_number}
                  </p>
                  <p className="text-[11px] text-outline">
                    {new Date(sale.created_at).toLocaleString("ar-EG")}
                  </p>
                </div>
                <span
                  className={`text-body-sm font-bold font-data-mono ${sale.is_refund ? "text-error" : "text-on-surface"}`}
                  dir="ltr"
                >
                  {sale.amount} EGP
                </span>
                {!sale.is_refund && (
                  <button
                    onClick={() => setRefundTarget(sale)}
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-warning-bg text-warning font-semibold text-[11px] hover:opacity-80 transition-opacity shrink-0"
                  >
                    <Undo2 className="w-3.5 h-3.5" /> استرجاع
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {refundTarget && (
        <RefundSaleModal
          sale={refundTarget}
          shift={shift}
          onClose={() => setRefundTarget(null)}
          onRefunded={() => {
            queryClient.invalidateQueries({ queryKey: ["pos-shift-sales", shift.id] });
            queryClient.invalidateQueries({ queryKey: ["pos-current-shift"] });
          }}
        />
      )}
    </div>,
    document.body
  );
}

function RefundSaleModal({
  sale,
  shift,
  onClose,
  onRefunded,
}: {
  sale: PosSaleRow;
  shift: CashShift;
  onClose: () => void;
  onRefunded: () => void;
}) {
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const mutation = useMutation({
    mutationFn: async () => {
      await apiClient.post(`/pos/sales/${sale.id}/refund`, { shift_id: shift.id });
    },
    onSuccess: () => {
      setDone(true);
      onRefunded();
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setError(pickDetail(err, "تعذر تسجيل المرتجع."));
    },
  });

  // Portal for the same reason as ShiftSalesModal above — this modal is
  // opened FROM inside ShiftSalesModal's own tree, so it inherits the exact
  // same backdrop-filter stacking-context trap if not escaped separately.
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-inverse-surface/40 p-gutter"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-headline-sm text-headline-sm text-on-surface">استرجاع عملية بيع</h3>
        <p className="text-body-sm text-on-surface-variant">
          فاتورة <span dir="ltr">{sale.invoice_number}</span> بقيمة{" "}
          <span className="font-data-mono text-on-surface" dir="ltr">{sale.amount} EGP</span>
          {" "}— سيتم إصدار إشعار دائن (Credit Note) واسترجاع كامل قيمة الفاتورة.
        </p>

        {error && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-2.5 rounded-lg text-body-sm font-medium">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}
        {done && (
          <div className="flex items-center gap-2 bg-success-bg text-success p-2.5 rounded-lg text-body-sm font-medium">
            <CheckCircle2 className="w-4 h-4 shrink-0" /> تم تسجيل المرتجع بنجاح.
          </div>
        )}

        <div className="flex gap-2">
          {!done && (
            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending}
              className="flex-1 h-11 rounded-lg bg-warning-bg text-warning font-bold text-body-md flex items-center justify-center gap-2 hover:opacity-80 transition-opacity disabled:opacity-70"
            >
              {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} تأكيد الاسترجاع
            </button>
          )}
          <button
            onClick={onClose}
            className={
              done
                ? "flex-1 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md flex items-center justify-center hover:opacity-90 transition-opacity"
                : "h-11 px-4 rounded-lg border border-outline-variant text-on-surface-variant font-semibold text-body-md hover:bg-surface-container transition-colors"
            }
          >
            {done ? "تم" : "إلغاء"}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

function CloseShiftModal({
  shift,
  onClose,
  onClosed,
}: {
  shift: CashShift;
  onClose: () => void;
  onClosed: () => void;
}) {
  const [closingBalance, setClosingBalance] = useState("");
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      await apiClient.post(`/pos/shifts/${shift.id}/close`, {
        closing_balance: Number(closingBalance || 0),
      });
    },
    onSuccess: () => {
      onClosed();
      onClose();
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setError(pickDetail(err, "تعذر إغلاق الوردية."));
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div
        className="w-full max-w-sm bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-headline-sm text-headline-sm text-on-surface">إغلاق الوردية</h3>
        <div className="space-y-1.5">
          <label className="text-body-sm font-semibold text-on-surface-variant">الرصيد الفعلي بالدرج</label>
          <input
            type="number"
            dir="ltr"
            value={closingBalance}
            onChange={(e) => setClosingBalance(e.target.value)}
            className="input-field font-mono"
            placeholder="0.00"
          />
        </div>
        {error && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-2.5 rounded-lg text-body-sm font-medium">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}
        <div className="flex gap-2">
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="flex-1 h-11 rounded-lg bg-error text-on-error font-bold text-body-md flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-70"
          >
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} تأكيد الإغلاق
          </button>
          <button
            onClick={onClose}
            className="h-11 px-4 rounded-lg border border-outline-variant text-on-surface-variant font-semibold text-body-md hover:bg-surface-container transition-colors"
          >
            إلغاء
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Open shift gate (shown before any sale can happen) ───────────────────────

function OpenShiftPanel({ onOpened }: { onOpened: () => void }) {
  const [openingBalance, setOpeningBalance] = useState("");
  const [error, setError] = useState("");

  const mutation = useMutation({
    mutationFn: async () => {
      await apiClient.post("/pos/shifts/open", {
        opening_balance: Number(openingBalance || 0),
      });
    },
    onSuccess: () => onOpened(),
    onError: (err: AxiosError<{ detail?: string }>) => {
      setError(pickDetail(err, "تعذر فتح الوردية."));
    },
  });

  return (
    <div className="h-[70vh] flex items-center justify-center">
      <div className="glass-card rounded-xl p-card-padding w-full max-w-sm space-y-4 text-center">
        <div className="w-14 h-14 mx-auto rounded-full bg-primary-container/10 text-primary flex items-center justify-center">
          <Wallet className="w-6 h-6" />
        </div>
        <div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface">لا توجد وردية مفتوحة</h2>
          <p className="text-body-sm text-on-surface-variant mt-1">
            أدخل رصيد بداية الوردية لفتح شاشة نقطة البيع.
          </p>
        </div>
        <div className="space-y-1.5 text-right">
          <label className="text-body-sm font-semibold text-on-surface-variant">رصيد الافتتاح</label>
          <input
            type="number"
            dir="ltr"
            value={openingBalance}
            onChange={(e) => setOpeningBalance(e.target.value)}
            className="input-field font-mono"
            placeholder="0.00"
          />
        </div>
        {error && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-2.5 rounded-lg text-body-sm font-medium text-right">
            <AlertCircle className="w-4 h-4 shrink-0" /> {error}
          </div>
        )}
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="w-full h-12 rounded-xl bg-primary text-on-primary font-bold text-body-md flex items-center justify-center gap-2 hover:opacity-90 transition-opacity disabled:opacity-70"
        >
          {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} فتح الوردية
        </button>
      </div>
    </div>
  );
}
