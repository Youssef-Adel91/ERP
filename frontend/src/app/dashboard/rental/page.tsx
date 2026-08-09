"use client";

import { useCallback, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient } from "@/lib/api-client";
import {
  Car,
  Plus,
  Loader2,
  AlertCircle,
  X,
  Gauge,
  LogIn,
  LogOut,
  ClipboardCheck,
  CheckCircle2,
  CalendarSearch,
  Fuel,
} from "lucide-react";

interface Vehicle {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  attributes: { make?: string; model?: string; year?: number; current_mileage?: number; plate_number?: string };
}

interface VehicleAvailability extends Vehicle {
  is_available: boolean;
  conflicting_case_id: string | null;
}

interface CaseType {
  id: string;
  code: string;
  plugin_key: string;
}

interface RentalCase {
  id: string;
  case_type_id: string;
  resource_id: string | null;
  title: string | null;
  current_stage: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  data: Record<string, any>;
}

interface InspectionDiff {
  pickup_mileage: number;
  return_mileage: number;
  driven_distance: number;
  extra_mileage: number;
  extra_mileage_charge: string;
  pickup_fuel: string;
  return_fuel: string;
  fuel_shortage_quarters: number;
  fuel_penalty: string;
  new_damages: Record<string, any>[];
  total_penalties: string;
}

const schema = z.object({
  code: z.string().min(1, "كود المركبة مطلوب"),
  name: z.string().min(1, "اسم المركبة مطلوب"),
  plate_number: z.string().min(1, "رقم اللوحة مطلوب"),
  make: z.string().min(1, "الماركة مطلوبة"),
  model: z.string().min(1, "الموديل مطلوب"),
  year: z.coerce.number().min(1990),
});
type FormOut = z.output<typeof schema>;
type FormIn = z.input<typeof schema>;

const stageLabel: Record<string, string> = {
  reserved: "محجوز",
  picked_up: "تم الاستلام",
  returned: "تم الإرجاع",
  closed: "مغلق",
  cancelled: "ملغي",
};

const stageTone: Record<string, string> = {
  reserved: "bg-primary-container/10 text-primary",
  picked_up: "bg-secondary-container/30 text-secondary",
  returned: "bg-tertiary-container/20 text-tertiary",
  closed: "bg-surface-container text-outline",
  cancelled: "bg-error-container/40 text-error",
};

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 2 })} ج.م`;

const fuelLevels = [
  { value: "0/4", label: "فارغ (0/4)" },
  { value: "1/4", label: "1/4" },
  { value: "2/4", label: "2/4" },
  { value: "3/4", label: "3/4" },
  { value: "4/4", label: "ممتلئ (4/4)" },
];

export default function RentalPage() {
  const [tab, setTab] = useState<"fleet" | "rentals">("fleet");
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get<Vehicle[]>("/rental/fleet");
      setVehicles(data);
    } catch {
      setError("تعذر تحميل الأسطول. فعّل موديول تأجير السيارات من صفحة الحالات أولاً.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">تأجير السيارات</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">إدارة الأسطول وعمليات التأجير النشطة.</p>
        </div>
        {tab === "fleet" && (
          <button onClick={() => setModalOpen(true)} className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit">
            <Plus className="w-4 h-4" /> مركبة جديدة
          </button>
        )}
      </div>

      <div className="flex gap-2 border-b border-outline-variant">
        <button
          onClick={() => setTab("fleet")}
          className={`px-4 py-2.5 text-body-md font-semibold border-b-2 transition-colors ${tab === "fleet" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}
        >
          الأسطول
        </button>
        <button
          onClick={() => setTab("rentals")}
          className={`px-4 py-2.5 text-body-md font-semibold border-b-2 transition-colors ${tab === "rentals" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}
        >
          عمليات التأجير النشطة
        </button>
      </div>

      {tab === "fleet" ? (
        <>
          {error && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {error}</div>}

          {loading ? (
            <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
          ) : vehicles.length === 0 ? (
            <div className="glass-card rounded-xl flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2"><Car className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد مركبات مسجّلة بعد.</p></div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-gutter">
              {vehicles.map((v) => (
                <div key={v.id} className="glass-card rounded-xl p-card-padding">
                  <div className="flex justify-between items-start mb-3">
                    <div className="w-10 h-10 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center"><Car className="w-5 h-5" /></div>
                    <span className={`px-2 py-1 rounded text-[11px] font-bold ${v.is_active ? "bg-secondary-container/30 text-secondary" : "bg-surface-container text-on-surface-variant"}`}>{v.is_active ? "متاحة" : "غير نشطة"}</span>
                  </div>
                  <h3 className="font-headline-sm text-headline-sm text-on-surface">{v.name}</h3>
                  <p className="text-body-sm text-outline font-data-mono" dir="ltr">{v.attributes.plate_number}</p>
                  <div className="flex items-center gap-3 mt-3 text-body-sm text-on-surface-variant">
                    <span>{v.attributes.make} {v.attributes.model} · {v.attributes.year}</span>
                  </div>
                  <div className="flex items-center gap-1 mt-1 text-body-sm text-outline">
                    <Gauge className="w-3.5 h-3.5" /> {Number(v.attributes.current_mileage ?? 0).toLocaleString("ar-EG")} كم
                  </div>
                </div>
              ))}
            </div>
          )}

          {modalOpen && <CreateVehicleModal onClose={() => setModalOpen(false)} onCreated={() => { setModalOpen(false); fetchAll(); }} />}
        </>
      ) : (
        <RentalsTab vehicles={vehicles} />
      )}
    </div>
  );
}

function CreateVehicleModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<FormIn, any, FormOut>({
    resolver: zodResolver(schema),
    defaultValues: { code: "", name: "", plate_number: "", make: "", model: "", year: 2024 },
  });

  const onSubmit = async (data: FormOut) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/rental/fleet", {
        code: data.code,
        name: data.name,
        attributes: { plate_number: data.plate_number, make: data.make, model: data.model, year: data.year },
      });
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(axiosErr.response?.data?.detail || "تعذر إضافة المركبة. تأكد من تفعيل موديول التأجير أولاً.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">مركبة جديدة</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">كود المركبة</label><input {...register("code")} dir="ltr" className="input-field font-mono" />{errors.code && <p className="text-body-sm text-error">{errors.code.message}</p>}</div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">اسم العرض</label><input {...register("name")} className="input-field" />{errors.name && <p className="text-body-sm text-error">{errors.name.message}</p>}</div>
          </div>
          <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">رقم اللوحة</label><input {...register("plate_number")} dir="ltr" className="input-field font-mono" />{errors.plate_number && <p className="text-body-sm text-error">{errors.plate_number.message}</p>}</div>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الماركة</label><input {...register("make")} className="input-field" />{errors.make && <p className="text-body-sm text-error">{errors.make.message}</p>}</div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الموديل</label><input {...register("model")} className="input-field" />{errors.model && <p className="text-body-sm text-error">{errors.model.message}</p>}</div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">السنة</label><input type="number" {...register("year")} dir="ltr" className="input-field font-mono" /></div>
          </div>
          <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />} حفظ المركبة
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Rentals Tab ──────────────────────────────────────────────────────────────

function RentalsTab({ vehicles }: { vehicles: Vehicle[] }) {
  const queryClient = useQueryClient();
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [inspectionTarget, setInspectionTarget] = useState<{ rentalCase: RentalCase; type: "pickup" | "return" } | null>(null);
  const [showClosed, setShowClosed] = useState(false);

  const { data: caseTypes } = useQuery({
    queryKey: ["case-types", "rental"],
    queryFn: async () => {
      const res = await apiClient.get<CaseType[]>("/case-types", { params: { plugin_key: "rental" } });
      return res.data;
    },
  });
  const caseType = caseTypes?.find((c) => c.code === "vehicle_rental");

  const { data: rentals, isLoading, isError } = useQuery({
    queryKey: ["rental-cases", caseType?.id],
    enabled: !!caseType,
    queryFn: async () => {
      const res = await apiClient.get<RentalCase[]>("/cases", { params: { case_type_id: caseType!.id } });
      return res.data;
    },
  });

  const vehicleById = new Map(vehicles.map((v) => [v.id, v]));
  const visible = (rentals ?? []).filter((r) => showClosed || !["closed", "cancelled"].includes(r.current_stage));

  const transitionMutation = useMutation({
    mutationFn: async ({ id, to_stage, data_patch }: { id: string; to_stage: string; data_patch?: Record<string, any> }) =>
      apiClient.post(`/cases/${id}/transition`, { to_stage, data_patch }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rental-cases"] }),
  });

  if (!caseType) {
    return (
      <div className="glass-card rounded-xl flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
        <Car className="w-8 h-8 text-outline-variant" />
        <p className="text-body-md">موديول التأجير غير مفعّل بعد. فعّله من صفحة الحالات أولاً.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <label className="flex items-center gap-2 text-body-sm text-on-surface-variant">
          <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
          إظهار المغلقة والملغاة
        </label>
        <button
          onClick={() => setNewModalOpen(true)}
          className="flex items-center gap-2 h-10 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity"
        >
          <Plus className="w-4 h-4" /> تأجير جديد
        </button>
      </div>

      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error"><AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل عمليات التأجير.</div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <Car className="w-7 h-7 text-outline-variant" />
            <p className="text-body-sm">لا توجد عمليات تأجير نشطة.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">المستأجر</th>
                  <th className="px-6 py-4">المركبة</th>
                  <th className="px-6 py-4">الاستلام</th>
                  <th className="px-6 py-4">الإرجاع</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {visible.map((r) => {
                  const vehicle = r.resource_id ? vehicleById.get(r.resource_id) : undefined;
                  return (
                    <tr key={r.id} className="hover:bg-surface-container-lowest transition-colors">
                      <td className="px-6 py-4 font-medium">{r.data?.renter_name ?? "—"}</td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{vehicle ? `${vehicle.attributes.plate_number} · ${vehicle.name}` : "—"}</td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{r.start_date ?? "—"}</td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{r.end_date ?? "—"}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-[11px] font-bold ${stageTone[r.current_stage] ?? ""}`}>
                          {stageLabel[r.current_stage] ?? r.current_stage}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3 flex-wrap">
                          {r.current_stage === "reserved" && (
                            <button
                              onClick={() => setInspectionTarget({ rentalCase: r, type: "pickup" })}
                              className="flex items-center gap-1.5 text-secondary font-semibold text-body-sm hover:underline"
                            >
                              <LogIn className="w-3.5 h-3.5" /> فحص الاستلام
                            </button>
                          )}
                          {r.current_stage === "picked_up" && (
                            <button
                              onClick={() => setInspectionTarget({ rentalCase: r, type: "return" })}
                              className="flex items-center gap-1.5 text-tertiary font-semibold text-body-sm hover:underline"
                            >
                              <LogOut className="w-3.5 h-3.5" /> فحص الإرجاع
                            </button>
                          )}
                          {r.current_stage === "returned" && (
                            <button
                              disabled={transitionMutation.isPending}
                              onClick={() => transitionMutation.mutate({ id: r.id, to_stage: "closed" })}
                              className="flex items-center gap-1.5 text-on-surface-variant font-semibold text-body-sm hover:underline disabled:opacity-50"
                            >
                              <CheckCircle2 className="w-3.5 h-3.5" /> إغلاق وتسوية
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {newModalOpen && caseType && (
        <NewRentalModal
          caseTypeId={caseType.id}
          vehicles={vehicles}
          onClose={() => setNewModalOpen(false)}
          onCreated={() => { setNewModalOpen(false); queryClient.invalidateQueries({ queryKey: ["rental-cases"] }); }}
        />
      )}
      {inspectionTarget && (
        <InspectionModal
          rentalCase={inspectionTarget.rentalCase}
          inspectionType={inspectionTarget.type}
          onClose={() => setInspectionTarget(null)}
          onDone={() => {
            setInspectionTarget(null);
            queryClient.invalidateQueries({ queryKey: ["rental-cases"] });
          }}
        />
      )}
    </div>
  );
}

// ── New Rental Modal ─────────────────────────────────────────────────────────

const rentalSchema = z.object({
  renter_name: z.string().min(1, "اسم المستأجر مطلوب"),
  renter_phone: z.string().optional(),
  driver_license_number: z.string().min(1, "رقم رخصة القيادة مطلوب"),
  daily_rate: z.coerce.number().min(0),
  mileage_limit_per_day: z.coerce.number().min(0).default(0),
  extra_mileage_rate: z.coerce.number().min(0).default(0),
  pickup_date: z.string().min(1, "تاريخ الاستلام مطلوب"),
  return_date: z.string().min(1, "تاريخ الإرجاع مطلوب"),
});
type RentalOut = z.output<typeof rentalSchema>;
type RentalIn = z.input<typeof rentalSchema>;

function NewRentalModal({
  caseTypeId,
  vehicles,
  onClose,
  onCreated,
}: {
  caseTypeId: string;
  vehicles: Vehicle[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [selectedVehicleId, setSelectedVehicleId] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, watch, formState: { errors } } = useForm<RentalIn, any, RentalOut>({
    resolver: zodResolver(rentalSchema),
    defaultValues: { renter_name: "", renter_phone: "", driver_license_number: "", daily_rate: 0, mileage_limit_per_day: 0, extra_mileage_rate: 0, pickup_date: "", return_date: "" },
  });

  const pickupDate = watch("pickup_date");
  const returnDate = watch("return_date");

  const { data: availability, isFetching: checkingAvailability } = useQuery({
    queryKey: ["vehicle-availability", pickupDate, returnDate],
    enabled: !!pickupDate && !!returnDate && returnDate > pickupDate,
    queryFn: async () => {
      const res = await apiClient.get<VehicleAvailability[]>("/rental/fleet/availability", {
        params: { pickup_date: pickupDate, return_date: returnDate },
      });
      return res.data;
    },
  });

  const availableIds = new Set((availability ?? []).filter((v) => v.is_available).map((v) => v.id));
  const vehiclesToShow = availability ?? vehicles.map((v) => ({ ...v, is_available: true, conflicting_case_id: null }));

  const mutation = useMutation({
    mutationFn: async (data: RentalOut) => {
      if (!selectedVehicleId) throw new Error("NO_VEHICLE");
      return apiClient.post("/cases", {
        case_type_id: caseTypeId,
        resource_id: selectedVehicleId,
        title: `تأجير — ${data.renter_name}`,
        start_date: data.pickup_date,
        end_date: data.return_date,
        data: {
          renter_name: data.renter_name,
          renter_phone: data.renter_phone || undefined,
          driver_license_number: data.driver_license_number,
          daily_rate: data.daily_rate,
          mileage_limit_per_day: data.mileage_limit_per_day,
          extra_mileage_rate: data.extra_mileage_rate,
        },
      });
    },
    onSuccess: onCreated,
    onError: (err) => {
      if ((err as Error).message === "NO_VEHICLE") {
        setErrorMsg("اختر مركبة متاحة أولاً.");
        return;
      }
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(axiosErr.response?.data?.detail || "تعذر إنشاء عملية التأجير.");
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">تأجير جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">تاريخ الاستلام</label><input type="date" {...register("pickup_date")} dir="ltr" className="input-field font-mono" />{errors.pickup_date && <p className="text-body-sm text-error">{errors.pickup_date.message}</p>}</div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">تاريخ الإرجاع</label><input type="date" {...register("return_date")} dir="ltr" className="input-field font-mono" />{errors.return_date && <p className="text-body-sm text-error">{errors.return_date.message}</p>}</div>
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant flex items-center gap-1.5">
              <CalendarSearch className="w-4 h-4" /> اختر مركبة متاحة
            </label>
            {!pickupDate || !returnDate ? (
              <p className="text-body-sm text-outline">اختر التواريخ أولاً لعرض المركبات المتاحة.</p>
            ) : checkingAvailability ? (
              <div className="flex items-center gap-2 text-body-sm text-on-surface-variant"><Loader2 className="w-4 h-4 animate-spin" /> جاري البحث...</div>
            ) : (
              <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto">
                {vehiclesToShow.map((v) => (
                  <button
                    type="button"
                    key={v.id}
                    disabled={!availableIds.has(v.id) && !!availability}
                    onClick={() => setSelectedVehicleId(v.id)}
                    className={`text-right px-3 py-2 rounded-lg border text-body-sm transition-colors ${
                      selectedVehicleId === v.id
                        ? "border-primary bg-primary-container/10 text-primary font-semibold"
                        : availability && !availableIds.has(v.id)
                        ? "border-outline-variant text-outline opacity-50 cursor-not-allowed"
                        : "border-outline-variant hover:bg-surface-container"
                    }`}
                  >
                    {v.attributes.plate_number} · {v.name}
                    {availability && !availableIds.has(v.id) && <span className="block text-[11px] text-error">محجوزة</span>}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">اسم المستأجر</label><input {...register("renter_name")} className="input-field" />{errors.renter_name && <p className="text-body-sm text-error">{errors.renter_name.message}</p>}</div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">رقم الهاتف</label><input {...register("renter_phone")} dir="ltr" className="input-field font-mono" /></div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">رقم رخصة القيادة</label><input {...register("driver_license_number")} dir="ltr" className="input-field font-mono" />{errors.driver_license_number && <p className="text-body-sm text-error">{errors.driver_license_number.message}</p>}</div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">السعر لليوم (ج.م)</label><input type="number" step="0.01" {...register("daily_rate")} dir="ltr" className="input-field font-mono" /></div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">حد الكيلومترات/يوم</label><input type="number" {...register("mileage_limit_per_day")} dir="ltr" className="input-field font-mono" /></div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">سعر الكيلومتر الإضافي</label><input type="number" step="0.01" {...register("extra_mileage_rate")} dir="ltr" className="input-field font-mono" /></div>
          </div>

          <button type="submit" disabled={mutation.isPending} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} تأكيد التأجير
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Inspection Modal (pickup or return) ─────────────────────────────────────

const inspectionSchema = z.object({
  mileage: z.coerce.number().min(0, "العداد مطلوب"),
  fuel_level: z.string().min(1),
  notes: z.string().optional(),
});
type InspectionOut = z.output<typeof inspectionSchema>;
type InspectionIn = z.input<typeof inspectionSchema>;

function InspectionModal({
  rentalCase,
  inspectionType,
  onClose,
  onDone,
}: {
  rentalCase: RentalCase;
  inspectionType: "pickup" | "return";
  onClose: () => void;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<InspectionIn, any, InspectionOut>({
    resolver: zodResolver(inspectionSchema),
    defaultValues: { mileage: 0, fuel_level: "4/4", notes: "" },
  });

  // Only meaningful once both inspections exist — safe to just try fetching.
  const { data: diff } = useQuery({
    queryKey: ["inspection-diff", rentalCase.id],
    enabled: inspectionType === "return",
    queryFn: async () => {
      try {
        const res = await apiClient.get<InspectionDiff>(`/rental/cases/${rentalCase.id}/inspections/diff`);
        return res.data;
      } catch {
        return null;
      }
    },
  });

  const submitInspection = useMutation({
    mutationFn: async (data: InspectionOut) =>
      apiClient.post(`/rental/cases/${rentalCase.id}/inspections`, {
        inspection_type: inspectionType,
        mileage: data.mileage,
        fuel_level: data.fuel_level,
        notes: data.notes || undefined,
        damage_notes: [],
      }),
    onSuccess: async () => {
      // Advance the case's stage: pickup inspection -> picked_up, return inspection -> returned.
      await apiClient.post(`/cases/${rentalCase.id}/transition`, {
        to_stage: inspectionType === "pickup" ? "picked_up" : "returned",
        data_patch:
          inspectionType === "pickup"
            ? { pickup_actual: new Date().toISOString() }
            : { return_actual: new Date().toISOString() },
      });
      queryClient.invalidateQueries({ queryKey: ["rental-cases"] });
      onDone();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(axiosErr.response?.data?.detail || "تعذر حفظ الفحص.");
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface flex items-center gap-2">
            <ClipboardCheck className="w-5 h-5 text-primary" />
            {inspectionType === "pickup" ? "فحص الاستلام" : "فحص الإرجاع"} — {rentalCase.data?.renter_name}
          </h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>

        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}

        {inspectionType === "return" && diff && (
          <div className="bg-surface-container-low rounded-lg p-4 mb-4 space-y-1.5 text-body-sm">
            <p className="font-semibold text-on-surface-variant mb-1">ملخص الفحص السابق (الاستلام)</p>
            <div className="flex justify-between"><span>المسافة المقطوعة</span><span dir="ltr" className="font-data-mono">{diff.driven_distance} كم</span></div>
            {diff.extra_mileage > 0 && <div className="flex justify-between text-error"><span>كيلومترات إضافية</span><span dir="ltr" className="font-data-mono">{diff.extra_mileage} كم = {egp(diff.extra_mileage_charge)}</span></div>}
          </div>
        )}

        <form onSubmit={handleSubmit((d) => submitInspection.mutate(d))} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">قراءة العداد (كم)</label>
            <input type="number" {...register("mileage")} dir="ltr" className="input-field font-mono" />
            {errors.mileage && <p className="text-body-sm text-error">{errors.mileage.message}</p>}
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant flex items-center gap-1.5">
              <Fuel className="w-4 h-4" /> مستوى الوقود
            </label>
            <select {...register("fuel_level")} className="input-field">
              {fuelLevels.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">ملاحظات (أضرار، حالة عامة...)</label>
            <textarea {...register("notes")} rows={3} className="input-field" />
          </div>
          <button type="submit" disabled={submitInspection.isPending} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {submitInspection.isPending && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الفحص
          </button>
        </form>
      </div>
    </div>
  );
}
