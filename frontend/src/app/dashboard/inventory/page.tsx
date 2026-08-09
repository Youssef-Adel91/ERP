"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient } from "@/lib/api-client";
import { Package, Warehouse as WarehouseIcon, Plus, Loader2, AlertCircle, X } from "lucide-react";

/**
 * Cut over from app.plugins.inventory ("/inventory/items" + "/inventory/invoices"
 * combined) to app.modules.inventory ("/inventory/items" + "/inventory/warehouses").
 * The richer Item model no longer carries price/cost/quantity_on_hand/is_active
 * directly — those live on ItemVariant.price and StockLevel.quantity respectively,
 * neither of which has a CRUD endpoint yet. So this page is now Items +
 * Warehouses only; invoicing moved to the Sales module (/dashboard/sales).
 */

// ── Types (mirrors backend app/modules/inventory/api/items.py) ────────────────

type CostingMethod = "FIFO" | "WAC" | "LIFO" | "STANDARD";
type WarehouseType = "MAIN" | "RETAIL" | "TRANSIT" | "QUARANTINE" | "DAMAGED" | "CONSIGNMENT";

interface Item {
  id: string;
  sku: string;
  name: string;
  egs_code: string | null;
  costing_method: CostingMethod;
  requires_batch: boolean;
  requires_serial: boolean;
}

interface Warehouse {
  id: string;
  name: string;
  code: string;
  type: WarehouseType;
}

const warehouseTypeLabel: Record<WarehouseType, string> = {
  MAIN: "رئيسي",
  RETAIL: "تجزئة",
  TRANSIT: "عبور",
  QUARANTINE: "حجر",
  DAMAGED: "تالف",
  CONSIGNMENT: "أمانة",
};

export default function InventoryPage() {
  const [tab, setTab] = useState<"items" | "warehouses">("items");
  const [itemModalOpen, setItemModalOpen] = useState(false);
  const [warehouseModalOpen, setWarehouseModalOpen] = useState(false);

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">المخزون</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            الأصناف والمخازن. فواتير المبيعات انتقلت إلى صفحة المبيعات.
          </p>
        </div>
        <button
          onClick={() => (tab === "items" ? setItemModalOpen(true) : setWarehouseModalOpen(true))}
          className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit"
        >
          <Plus className="w-4 h-4" />
          {tab === "items" ? "صنف جديد" : "مخزن جديد"}
        </button>
      </div>

      <div className="flex gap-2 border-b border-outline-variant">
        <button
          onClick={() => setTab("items")}
          className={`flex items-center gap-2 px-4 py-3 text-body-md font-semibold border-b-2 transition-colors ${
            tab === "items" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          <Package className="w-4 h-4" /> الأصناف
        </button>
        <button
          onClick={() => setTab("warehouses")}
          className={`flex items-center gap-2 px-4 py-3 text-body-md font-semibold border-b-2 transition-colors ${
            tab === "warehouses" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          <WarehouseIcon className="w-4 h-4" /> المخازن
        </button>
      </div>

      {tab === "items" ? <ItemsTab modalOpen={itemModalOpen} onCloseModal={() => setItemModalOpen(false)} /> : null}
      {tab === "warehouses" ? (
        <WarehousesTab modalOpen={warehouseModalOpen} onCloseModal={() => setWarehouseModalOpen(false)} />
      ) : null}
    </div>
  );
}

// ── Items ──────────────────────────────────────────────────────────────────────

function ItemsTab({ modalOpen, onCloseModal }: { modalOpen: boolean; onCloseModal: () => void }) {
  const queryClient = useQueryClient();
  const { data: items, isLoading, isError } = useQuery({
    queryKey: ["inventory-items"],
    queryFn: async () => {
      const res = await apiClient.get<Item[]>("/inventory/items");
      return res.data;
    },
  });

  return (
    <>
      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الأصناف.
          </div>
        ) : !items || items.length === 0 ? (
          <EmptyState icon={Package} text="لا توجد أصناف مضافة بعد." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">الصنف</th>
                  <th className="px-6 py-4">SKU</th>
                  <th className="px-6 py-4">كود ETA</th>
                  <th className="px-6 py-4">طريقة التكلفة</th>
                  <th className="px-6 py-4">تتبع</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {items.map((item) => (
                  <tr key={item.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-medium">{item.name}</td>
                    <td className="px-6 py-4 font-data-mono text-on-surface-variant" dir="ltr">{item.sku}</td>
                    <td className="px-6 py-4 font-data-mono text-on-surface-variant" dir="ltr">{item.egs_code ?? "—"}</td>
                    <td className="px-6 py-4">
                      <span className="px-2 py-1 rounded text-[11px] font-bold bg-primary-container/10 text-primary font-data-mono" dir="ltr">
                        {item.costing_method}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-body-sm text-on-surface-variant">
                      {[item.requires_batch && "دفعات", item.requires_serial && "أرقام تسلسلية"].filter(Boolean).join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && (
        <CreateItemModal
          onClose={onCloseModal}
          onCreated={() => {
            onCloseModal();
            queryClient.invalidateQueries({ queryKey: ["inventory-items"] });
          }}
        />
      )}
    </>
  );
}

const createItemSchema = z.object({
  name: z.string().min(1, "الاسم مطلوب"),
  sku: z.string().min(1, "SKU مطلوب"),
  egs_code: z.string().optional(),
  costing_method: z.enum(["FIFO", "WAC", "LIFO", "STANDARD"]),
  requires_batch: z.boolean(),
  requires_serial: z.boolean(),
});
type CreateItemForm = z.infer<typeof createItemSchema>;

function CreateItemModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<CreateItemForm>({
    resolver: zodResolver(createItemSchema),
    defaultValues: { name: "", sku: "", egs_code: "", costing_method: "FIFO", requires_batch: false, requires_serial: false },
  });

  const mutation = useMutation({
    mutationFn: async (data: CreateItemForm) => {
      await apiClient.post("/inventory/items", { ...data, egs_code: data.egs_code || undefined });
    },
    onSuccess: onCreated,
    onError: (err: AxiosError<{ detail?: string }>) => {
      setErrorMsg(err.response?.data?.detail || "تعذر إنشاء الصنف.");
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">صنف جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
          <Field label="اسم الصنف" error={errors.name?.message}>
            <input {...register("name")} className="input-field" />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="SKU" error={errors.sku?.message}>
              <input {...register("sku")} dir="ltr" className="input-field font-mono" />
            </Field>
            <Field label="كود ETA (اختياري)">
              <input {...register("egs_code")} dir="ltr" className="input-field font-mono" />
            </Field>
          </div>
          <Field label="طريقة حساب التكلفة">
            <select {...register("costing_method")} className="input-field">
              <option value="FIFO">FIFO</option>
              <option value="WAC">WAC (متوسط مرجح)</option>
              <option value="LIFO">LIFO</option>
              <option value="STANDARD">تكلفة معيارية</option>
            </select>
          </Field>
          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-body-sm text-on-surface-variant">
              <input type="checkbox" {...register("requires_batch")} /> يتطلب تتبع دفعات
            </label>
            <label className="flex items-center gap-2 text-body-sm text-on-surface-variant">
              <input type="checkbox" {...register("requires_serial")} /> يتطلب رقم تسلسلي
            </label>
          </div>
          <button type="submit" disabled={mutation.isPending} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الصنف
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Warehouses ─────────────────────────────────────────────────────────────────

function WarehousesTab({ modalOpen, onCloseModal }: { modalOpen: boolean; onCloseModal: () => void }) {
  const queryClient = useQueryClient();
  const { data: warehouses, isLoading, isError } = useQuery({
    queryKey: ["inventory-warehouses"],
    queryFn: async () => {
      const res = await apiClient.get<Warehouse[]>("/inventory/warehouses");
      return res.data;
    },
  });

  return (
    <>
      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
          </div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل المخازن.
          </div>
        ) : !warehouses || warehouses.length === 0 ? (
          <EmptyState icon={WarehouseIcon} text="لا توجد مخازن مضافة بعد." />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-gutter p-card-padding">
            {warehouses.map((w) => (
              <div key={w.id} className="rounded-xl border border-outline-variant p-4">
                <div className="flex items-center gap-2 mb-2">
                  <WarehouseIcon className="w-4 h-4 text-primary" />
                  <h4 className="font-headline-sm text-headline-sm text-on-surface">{w.name}</h4>
                </div>
                <p className="font-data-mono text-body-sm text-outline" dir="ltr">{w.code}</p>
                <span className="inline-block mt-2 px-2 py-1 rounded text-[11px] font-bold bg-primary-container/10 text-primary">
                  {warehouseTypeLabel[w.type]}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {modalOpen && (
        <CreateWarehouseModal
          onClose={onCloseModal}
          onCreated={() => {
            onCloseModal();
            queryClient.invalidateQueries({ queryKey: ["inventory-warehouses"] });
          }}
        />
      )}
    </>
  );
}

const createWarehouseSchema = z.object({
  name: z.string().min(1, "الاسم مطلوب"),
  code: z.string().min(1, "الكود مطلوب"),
  type: z.enum(["MAIN", "RETAIL", "TRANSIT", "QUARANTINE", "DAMAGED", "CONSIGNMENT"]),
});
type CreateWarehouseForm = z.infer<typeof createWarehouseSchema>;

function CreateWarehouseModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<CreateWarehouseForm>({
    resolver: zodResolver(createWarehouseSchema),
    defaultValues: { name: "", code: "", type: "MAIN" },
  });

  const mutation = useMutation({
    mutationFn: async (data: CreateWarehouseForm) => {
      await apiClient.post("/inventory/warehouses", data);
    },
    onSuccess: onCreated,
    onError: (err: AxiosError<{ detail?: string }>) => {
      setErrorMsg(err.response?.data?.detail || "تعذر إنشاء المخزن.");
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">مخزن جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}
        <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
          <Field label="اسم المخزن" error={errors.name?.message}>
            <input {...register("name")} className="input-field" />
          </Field>
          <Field label="الكود" error={errors.code?.message}>
            <input {...register("code")} dir="ltr" className="input-field font-mono" />
          </Field>
          <Field label="النوع">
            <select {...register("type")} className="input-field">
              {Object.entries(warehouseTypeLabel).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </Field>
          <button type="submit" disabled={mutation.isPending} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ المخزن
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Shared ─────────────────────────────────────────────────────────────────────

function EmptyState({ icon: Icon, text }: { icon: React.ElementType; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
      <Icon className="w-8 h-8 text-outline-variant" />
      <p className="text-body-md">{text}</p>
    </div>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-body-sm font-semibold text-on-surface-variant">{label}</label>
      {children}
      {error && <p className="text-body-sm text-error">{error}</p>}
    </div>
  );
}
