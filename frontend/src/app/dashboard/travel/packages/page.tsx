"use client";

import { useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  Plane,
  Loader2,
  AlertCircle,
  Plus,
  Trash2,
  Pencil,
  ArrowRight,
  MapPin,
  Calendar,
  Users2,
  Wallet,
  X,
  Save,
  CalendarDays,
} from "lucide-react";

// ── Types (mirrors backend app/plugins/travel/api_packages.py) ──────────────

interface ItineraryDay {
  id?: string;
  day_number: number;
  title_ar: string;
  title_en?: string | null;
  description_ar?: string | null;
  meals_included: string[];
}

interface Component {
  id?: string;
  day_number: number | null;
  component_type: string;
  vendor_id: string | null;
  vendor_name?: string | null;
  description: string;
  net_cost: number;
  sell_price: number;
  currency: string;
  quantity: number;
  sort_order: number;
}

interface TravelPackage {
  id: string;
  name_ar: string;
  destination: string;
  category: string;
  duration_days: number;
  duration_nights: number;
  description_ar?: string | null;
  base_price: number;
  base_cost: number;
  currency: string;
  min_pax: number;
  max_pax: number | null;
  is_active: boolean;
  itinerary_days?: ItineraryDay[];
  components?: Component[];
}

interface Vendor {
  id: string;
  name_ar: string | null;
  name: string;
  vendor_type: string;
}

const SERVICE_TYPES: Record<string, string> = {
  flight: "طيران",
  hotel: "فندق",
  transfer: "نقل",
  visa: "تأشيرة",
  travel_insurance: "تأمين سفر",
  excursion: "رحلة/جولة",
  car_rental: "تأجير سيارة",
  other: "أخرى",
};

const CATEGORIES: Record<string, string> = {
  family: "عائلي",
  honeymoon: "شهر عسل",
  religious: "ديني",
  adventure: "مغامرات",
  corporate: "شركات",
  group: "جماعي",
  beach: "شواطئ",
  city_break: "رحلة مدينة",
  other: "أخرى",
};

const egp = (v: number, currency = "EGP") =>
  `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ${currency === "EGP" ? "ج.م" : currency}`;

const emptyPackage = () => ({
  name_ar: "",
  name_en: "",
  destination: "",
  category: "other",
  duration_days: 1,
  duration_nights: 0,
  description_ar: "",
  currency: "EGP",
  min_pax: 1,
  max_pax: null as number | null,
  is_active: true,
  itinerary_days: [] as ItineraryDay[],
  components: [] as Component[],
});

export default function TravelPackagesPage() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<null | ReturnType<typeof emptyPackage>>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [loadingEditId, setLoadingEditId] = useState<string | null>(null);

  const { data: packages, isLoading, isError } = useQuery({
    queryKey: ["travel-packages"],
    queryFn: async () => {
      const res = await apiClient.get<TravelPackage[]>("/travel/packages");
      return res.data;
    },
  });

  const { data: vendors } = useQuery({
    queryKey: ["travel-vendors"],
    queryFn: async () => {
      const res = await apiClient.get<Vendor[]>("/cases/vendors").catch(() => ({ data: [] as Vendor[] }));
      return res.data;
    },
  });

  const saveMutation = useMutation({
    mutationFn: async (pkg: ReturnType<typeof emptyPackage>) => {
      if (editingId) {
        // PATCH only supports flat fields — itinerary/components are managed
        // via their own sub-resources once a package exists, so on edit we
        // just sync the flat fields here; nested items are saved inline
        // (see addDay/addComponent mutations below) as soon as the user adds them.
        const { itinerary_days: _d, components: _c, ...flat } = pkg;
        await apiClient.patch(`/travel/packages/${editingId}`, flat);
      } else {
        await apiClient.post("/travel/packages", pkg);
      }
    },
    onSuccess: () => {
      setErrorMsg("");
      setEditing(null);
      setEditingId(null);
      queryClient.invalidateQueries({ queryKey: ["travel-packages"] });
    },
    onError: (err: AxiosError<{ detail?: string }>) => {
      setErrorMsg(pickDetail(err, "تعذر حفظ الباقة، حاول مرة أخرى."));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/travel/packages/${id}`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["travel-packages"] }),
  });

  const startCreate = () => {
    setEditingId(null);
    setEditing(emptyPackage());
  };

  // NOTE: GET /travel/packages (the list this page's table is built from)
  // returns PackageOut — a flat summary with NO itinerary_days/components.
  // Building the edit form straight from that row (the old behavior) meant
  // the editor always opened with "no days/no items" for existing packages
  // that in fact had real itinerary/components — confirmed live: a package
  // with a fully-priced hotel component showed both lists empty when
  // edited. The full nested shape only comes back from the detail endpoint
  // GET /travel/packages/{id} (PackageDetailOut), so we fetch that here
  // instead of trusting the list row.
  const startEdit = async (pkg: TravelPackage) => {
    setLoadingEditId(pkg.id);
    setErrorMsg("");
    try {
      const res = await apiClient.get<TravelPackage>(`/travel/packages/${pkg.id}`);
      const full = res.data;
      setEditingId(full.id);
      setEditing({
        name_ar: full.name_ar,
        name_en: "",
        destination: full.destination,
        category: full.category,
        duration_days: full.duration_days,
        duration_nights: full.duration_nights,
        description_ar: full.description_ar ?? "",
        currency: full.currency,
        min_pax: full.min_pax,
        max_pax: full.max_pax,
        is_active: full.is_active,
        itinerary_days: full.itinerary_days ?? [],
        components: full.components ?? [],
      });
    } catch {
      setErrorMsg("تعذر تحميل بيانات الباقة الكاملة، حاول مرة أخرى.");
    } finally {
      setLoadingEditId(null);
    }
  };

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div className="flex items-center gap-3">
          <Link href="/dashboard/travel" className="text-on-surface-variant hover:text-on-surface">
            <ArrowRight className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">باقات السياحة</h1>
            <p className="font-body-md text-body-md text-on-surface-variant">
              كتالوج الباقات الجاهزة للبيع — برنامج رحلة وعناصر مسعّرة لكل باقة.
            </p>
          </div>
        </div>
        <button
          onClick={startCreate}
          className="flex items-center gap-2 h-10 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity w-fit"
        >
          <Plus className="w-4 h-4" /> باقة جديدة
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-body-sm text-error py-6">
          <AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الباقات.
        </div>
      ) : !packages || packages.length === 0 ? (
        <Card>
          <EmptyState icon={Plane} title="لا توجد باقات بعد" description="ابدأ بإنشاء أول باقة سياحية جاهزة للبيع." />
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-gutter">
          {packages.map((pkg) => {
            const margin = pkg.base_price - pkg.base_cost;
            return (
              <Card key={pkg.id} className="flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-headline-sm text-headline-sm text-on-surface">{pkg.name_ar}</h3>
                    <p className="text-body-sm text-on-surface-variant flex items-center gap-1 mt-0.5">
                      <MapPin className="w-3.5 h-3.5" /> {pkg.destination}
                    </p>
                  </div>
                  <Badge tone={pkg.is_active ? "success" : "neutral"}>{pkg.is_active ? "نشطة" : "معطلة"}</Badge>
                </div>

                <div className="flex flex-wrap gap-2 text-[11px] text-on-surface-variant">
                  <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> {pkg.duration_days} أيام / {pkg.duration_nights} ليالي</span>
                  <span className="flex items-center gap-1"><Users2 className="w-3.5 h-3.5" /> {pkg.min_pax}{pkg.max_pax ? `–${pkg.max_pax}` : "+"} فرد</span>
                  <Badge tone="tertiary">{CATEGORIES[pkg.category] ?? pkg.category}</Badge>
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-outline-variant/40">
                  <div>
                    <p className="text-[11px] text-on-surface-variant">سعر البيع</p>
                    <p className="font-data-mono font-bold text-on-surface" dir="ltr">{egp(pkg.base_price, pkg.currency)}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-on-surface-variant flex items-center gap-1 justify-end"><Wallet className="w-3 h-3" /> الهامش</p>
                    <p className="font-data-mono font-bold text-secondary" dir="ltr">{egp(margin, pkg.currency)}</p>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <button
                    onClick={() => startEdit(pkg)}
                    disabled={loadingEditId === pkg.id}
                    className="flex-1 h-9 rounded-lg border border-outline-variant text-body-sm font-semibold hover:bg-surface-container transition-colors flex items-center justify-center gap-1.5 disabled:opacity-60"
                  >
                    {loadingEditId === pkg.id ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Pencil className="w-3.5 h-3.5" />
                    )}
                    تعديل
                  </button>
                  <Link
                    href={`/dashboard/travel/new?package_id=${pkg.id}`}
                    className="flex-1 h-9 rounded-lg bg-primary text-on-primary text-body-sm font-bold hover:opacity-90 transition-opacity flex items-center justify-center gap-1.5"
                  >
                    بيع الباقة
                  </Link>
                  <button
                    onClick={() => confirm("متأكد من حذف الباقة دي؟") && deleteMutation.mutate(pkg.id)}
                    className="h-9 w-9 rounded-lg border border-error/30 text-error hover:bg-error-container/20 transition-colors flex items-center justify-center shrink-0"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {editing && (
        <PackageEditor
          value={editing}
          onChange={setEditing}
          onClose={() => { setEditing(null); setEditingId(null); }}
          onSave={() => saveMutation.mutate(editing)}
          saving={saveMutation.isPending}
          errorMsg={errorMsg}
          vendors={vendors ?? []}
          isEditingExisting={!!editingId}
          packageId={editingId}
        />
      )}
    </div>
  );
}

// ── Editor Panel ──────────────────────────────────────────────────────────────

function PackageEditor({
  value,
  onChange,
  onClose,
  onSave,
  saving,
  errorMsg,
  vendors,
  isEditingExisting,
  packageId,
}: {
  value: ReturnType<typeof emptyPackage>;
  onChange: (v: ReturnType<typeof emptyPackage>) => void;
  onClose: () => void;
  onSave: () => void;
  saving: boolean;
  errorMsg: string;
  vendors: Vendor[];
  isEditingExisting: boolean;
  packageId: string | null;
}) {
  const queryClient = useQueryClient();
  const set = <K extends keyof typeof value>(key: K, v: (typeof value)[K]) => onChange({ ...value, [key]: v });

  // Debounce PATCH requests fired from field-change handlers below (components,
  // itinerary days) so a fast typist doesn't flood the API with one request per
  // keystroke. Each debounced call is keyed by a stable id (e.g. `component:<id>`)
  // so edits to different rows/fields don't cancel each other out.
  const debounceTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const debouncedPatch = (key: string, fn: () => void, delay = 500) => {
    if (debounceTimers.current[key]) clearTimeout(debounceTimers.current[key]);
    debounceTimers.current[key] = setTimeout(fn, delay);
  };

  const totalCost = value.components.reduce((s, c) => s + c.net_cost * c.quantity, 0);
  const totalSell = value.components.reduce((s, c) => s + c.sell_price * c.quantity, 0);

  const addDayMutation = useMutation({
    mutationFn: async (day: ItineraryDay) => {
      if (!packageId) return null;
      const res = await apiClient.post(`/travel/packages/${packageId}/itinerary-days`, day);
      return res.data;
    },
  });

  const addComponentMutation = useMutation({
    mutationFn: async (comp: Component) => {
      if (!packageId) return null;
      const res = await apiClient.post(`/travel/packages/${packageId}/components`, comp);
      return res.data;
    },
  });

  const addDay = () => {
    const day: ItineraryDay = {
      day_number: value.itinerary_days.length + 1,
      title_ar: `اليوم ${value.itinerary_days.length + 1}`,
      meals_included: [],
    };
    if (packageId) {
      addDayMutation.mutate(day, {
        onSuccess: (created) => {
          set("itinerary_days", [...value.itinerary_days, created ?? day]);
          queryClient.invalidateQueries({ queryKey: ["travel-packages"] });
        },
      });
    } else {
      set("itinerary_days", [...value.itinerary_days, day]);
    }
  };

  const addComponent = () => {
    const comp: Component = {
      day_number: null,
      component_type: "other",
      vendor_id: null,
      description: "",
      net_cost: 0,
      sell_price: 0,
      currency: value.currency,
      quantity: 1,
      sort_order: value.components.length,
    };
    if (packageId) {
      addComponentMutation.mutate(comp, {
        onSuccess: (created) => {
          set("components", [...value.components, created ?? comp]);
          queryClient.invalidateQueries({ queryKey: ["travel-packages"] });
        },
      });
    } else {
      set("components", [...value.components, comp]);
    }
  };

  const removeComponent = async (idx: number) => {
    const comp = value.components[idx];
    if (packageId && comp.id) {
      await apiClient.delete(`/travel/components/${comp.id}`);
      queryClient.invalidateQueries({ queryKey: ["travel-packages"] });
    }
    set("components", value.components.filter((_, i) => i !== idx));
  };

  const updateComponent = async (idx: number, patch: Partial<Component>) => {
    const next = value.components.map((c, i) => (i === idx ? { ...c, ...patch } : c));
    set("components", next);
    const comp = next[idx];
    if (packageId && comp.id) {
      debouncedPatch(`component:${comp.id}`, () => {
        apiClient.patch(`/travel/components/${comp.id}`, comp).catch(() => {});
      });
    }
  };

  const removeDay = async (idx: number) => {
    const day = value.itinerary_days[idx];
    if (packageId && day.id) {
      await apiClient.delete(`/travel/itinerary-days/${day.id}`);
      queryClient.invalidateQueries({ queryKey: ["travel-packages"] });
    }
    set("itinerary_days", value.itinerary_days.filter((_, i) => i !== idx));
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-gutter" onClick={onClose}>
      <div
        className="glass-card rounded-xl w-full max-w-3xl max-h-[90vh] overflow-y-auto p-card-padding space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-headline-sm text-headline-sm text-on-surface">
            {isEditingExisting ? "تعديل الباقة" : "باقة جديدة"}
          </h2>
          <button onClick={onClose} className="text-on-surface-variant hover:text-on-surface">
            <X className="w-5 h-5" />
          </button>
        </div>

        {!isEditingExisting && (
          <p className="text-body-sm text-on-surface-variant bg-surface-container-low rounded-lg p-3">
            احفظ البيانات الأساسية الأول عشان تقدر تضيف برنامج الرحلة والعناصر المسعّرة.
          </p>
        )}

        {/* Basic fields */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="اسم الباقة">
            <input className="input" value={value.name_ar} onChange={(e) => set("name_ar", e.target.value)} />
          </Field>
          <Field label="الوجهة">
            <input className="input" value={value.destination} onChange={(e) => set("destination", e.target.value)} />
          </Field>
          <Field label="التصنيف">
            <select className="input" value={value.category} onChange={(e) => set("category", e.target.value)}>
              {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="العملة">
            <input className="input" value={value.currency} onChange={(e) => set("currency", e.target.value)} />
          </Field>
          <Field label="عدد الأيام">
            <input type="number" min={1} className="input" value={value.duration_days} onChange={(e) => set("duration_days", Number(e.target.value))} />
          </Field>
          <Field label="عدد الليالي">
            <input type="number" min={0} className="input" value={value.duration_nights} onChange={(e) => set("duration_nights", Number(e.target.value))} />
          </Field>
          <Field label="أقل عدد أفراد">
            <input type="number" min={1} className="input" value={value.min_pax} onChange={(e) => set("min_pax", Number(e.target.value))} />
          </Field>
          <Field label="أقصى عدد أفراد (اختياري)">
            <input type="number" min={1} className="input" value={value.max_pax ?? ""} onChange={(e) => set("max_pax", e.target.value ? Number(e.target.value) : null)} />
          </Field>
        </div>
        <Field label="الوصف">
          <textarea className="input min-h-20" value={value.description_ar ?? ""} onChange={(e) => set("description_ar", e.target.value)} />
        </Field>

        {isEditingExisting && (
          <>
            {/* Itinerary */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-headline-sm text-body-md font-bold text-on-surface flex items-center gap-1.5">
                  <CalendarDays className="w-4 h-4" /> برنامج الرحلة
                </h3>
                <button onClick={addDay} className="text-primary text-body-sm font-semibold flex items-center gap-1">
                  <Plus className="w-3.5 h-3.5" /> إضافة يوم
                </button>
              </div>
              <div className="space-y-2">
                {value.itinerary_days.map((day, idx) => (
                  <div key={day.id ?? idx} className="flex items-center gap-2 bg-surface-container-low rounded-lg p-2">
                    <span className="text-[11px] font-bold text-on-surface-variant w-14 shrink-0">يوم {day.day_number}</span>
                    <input
                      className="input flex-1"
                      value={day.title_ar}
                      onChange={(e) => {
                        const newTitle = e.target.value;
                        const next = value.itinerary_days.map((d, i) => (i === idx ? { ...d, title_ar: newTitle } : d));
                        set("itinerary_days", next);
                        if (packageId && day.id) {
                          debouncedPatch(`day:${day.id}`, () => {
                            apiClient.patch(`/travel/itinerary-days/${day.id}`, { ...day, title_ar: newTitle }).catch(() => {});
                          });
                        }
                      }}
                      placeholder="عنوان اليوم"
                    />
                    <button onClick={() => removeDay(idx)} className="text-error shrink-0"><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
                {value.itinerary_days.length === 0 && <p className="text-body-sm text-on-surface-variant">لا توجد أيام مضافة.</p>}
              </div>
            </div>

            {/* Components */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-headline-sm text-body-md font-bold text-on-surface">العناصر المسعّرة</h3>
                <button onClick={addComponent} className="text-primary text-body-sm font-semibold flex items-center gap-1">
                  <Plus className="w-3.5 h-3.5" /> إضافة عنصر
                </button>
              </div>
              <div className="space-y-2">
                {value.components.map((comp, idx) => (
                  <div key={comp.id ?? idx} className="grid grid-cols-12 gap-2 items-center bg-surface-container-low rounded-lg p-2">
                    <select
                      className="input col-span-2 text-[12px]"
                      value={comp.component_type}
                      onChange={(e) => updateComponent(idx, { component_type: e.target.value })}
                    >
                      {Object.entries(SERVICE_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                    <input
                      className="input col-span-3 text-[12px]"
                      placeholder="الوصف"
                      value={comp.description}
                      onChange={(e) => updateComponent(idx, { description: e.target.value })}
                    />
                    <select
                      className="input col-span-2 text-[12px]"
                      value={comp.vendor_id ?? ""}
                      onChange={(e) => updateComponent(idx, { vendor_id: e.target.value || null })}
                    >
                      <option value="">بدون مورد</option>
                      {vendors.map((v) => <option key={v.id} value={v.id}>{v.name_ar ?? v.name}</option>)}
                    </select>
                    <input
                      type="number"
                      className="input col-span-2 text-[12px]"
                      placeholder="التكلفة"
                      dir="ltr"
                      value={comp.net_cost}
                      onChange={(e) => updateComponent(idx, { net_cost: Number(e.target.value) })}
                    />
                    <input
                      type="number"
                      className="input col-span-2 text-[12px]"
                      placeholder="سعر البيع"
                      dir="ltr"
                      value={comp.sell_price}
                      onChange={(e) => updateComponent(idx, { sell_price: Number(e.target.value) })}
                    />
                    <button onClick={() => removeComponent(idx)} className="text-error col-span-1 flex justify-center"><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
                {value.components.length === 0 && <p className="text-body-sm text-on-surface-variant">لا توجد عناصر مضافة.</p>}
              </div>
              {value.components.length > 0 && (
                <div className="flex items-center justify-end gap-6 mt-3 text-body-sm">
                  <span className="text-on-surface-variant">إجمالي التكلفة: <b className="font-data-mono" dir="ltr">{egp(totalCost, value.currency)}</b></span>
                  <span className="text-on-surface-variant">إجمالي البيع: <b className="font-data-mono" dir="ltr">{egp(totalSell, value.currency)}</b></span>
                  <span className="text-secondary font-bold">الهامش: <b className="font-data-mono" dir="ltr">{egp(totalSell - totalCost, value.currency)}</b></span>
                </div>
              )}
            </div>
          </>
        )}

        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-outline-variant/40">
          <button onClick={onClose} className="h-10 px-4 rounded-lg border border-outline-variant text-body-sm font-semibold">إلغاء</button>
          <button
            onClick={onSave}
            disabled={saving || !value.name_ar || !value.destination}
            className="h-10 px-5 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-60 flex items-center gap-1.5"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {isEditingExisting ? "حفظ التعديلات" : "إنشاء الباقة"}
          </button>
        </div>
      </div>

      <style jsx global>{`
        .input {
          height: 2.5rem;
          border-radius: 0.5rem;
          border: 1px solid var(--outline-variant);
          padding: 0 0.75rem;
          font-size: 0.875rem;
          background: var(--surface);
          color: var(--on-surface);
          width: 100%;
        }
        textarea.input { height: auto; padding: 0.5rem 0.75rem; }
      `}</style>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold text-on-surface-variant mb-1 block">{label}</span>
      {children}
    </label>
  );
}
