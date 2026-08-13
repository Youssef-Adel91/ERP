"use client";

import { useCallback, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import {
  BedDouble,
  Plus,
  Loader2,
  AlertCircle,
  X,
  Users2,
  LogIn,
  LogOut,
  Receipt,
  CheckCircle2,
  CalendarSearch,
} from "lucide-react";

interface Room {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  attributes: { room_type?: string; floor?: number; capacity?: number; base_rate?: number };
}

interface RoomAvailability extends Room {
  is_available: boolean;
  conflicting_case_id: string | null;
}

interface CaseType {
  id: string;
  code: string;
  plugin_key: string;
}

interface Reservation {
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

interface FolioLine {
  category: string;
  description: string;
  quantity: string;
  unit_price: string;
  amount: string;
  currency: string;
}

interface FolioSummary {
  case_id: string;
  currency: string;
  nights: number;
  check_in: string;
  check_out: string;
  room_charge: string;
  board_charge: string;
  extras_total: string;
  discount_total: string;
  deposit_total: string;
  service_charge: string;
  tax_amount: string;
  tax_rate: string;
  total: string;
  balance_due: string;
  lines: FolioLine[];
}

const schema = z.object({
  code: z.string().min(1, "رقم الغرفة مطلوب"),
  name: z.string().min(1, "اسم الغرفة مطلوب"),
  room_type: z.string().min(1),
  floor: z.coerce.number().min(0),
  capacity: z.coerce.number().min(1),
  base_rate: z.coerce.number().min(0).optional(),
});
type FormOut = z.output<typeof schema>;
type FormIn = z.input<typeof schema>;

const roomTypes = ["single", "double", "twin", "suite", "deluxe", "family", "studio", "penthouse"];

const stageLabel: Record<string, string> = {
  booked: "محجوز",
  confirmed: "مؤكد",
  checked_in: "تم تسجيل الدخول",
  checked_out: "تم تسجيل المغادرة",
  closed: "مغلق",
  cancelled: "ملغي",
};

const stageTone: Record<string, string> = {
  booked: "bg-primary-container/10 text-primary",
  confirmed: "bg-tertiary-container/20 text-tertiary",
  checked_in: "bg-secondary-container/30 text-secondary",
  checked_out: "bg-surface-container-high text-on-surface-variant",
  closed: "bg-surface-container text-outline",
  cancelled: "bg-error-container/40 text-error",
};

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 2 })} ج.م`;

export default function HospitalityPage() {
  const [tab, setTab] = useState<"rooms" | "reservations">("rooms");
  const [rooms, setRooms] = useState<Room[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { data } = await apiClient.get<Room[]>("/hospitality/rooms");
      setRooms(data);
    } catch {
      setError("تعذر تحميل الغرف. فعّل موديول الضيافة من صفحة الحالات أولاً.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الضيافة والفنادق</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">إدارة الغرف والحجوزات النشطة.</p>
        </div>
        {tab === "rooms" && (
          <button onClick={() => setModalOpen(true)} className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit">
            <Plus className="w-4 h-4" /> غرفة جديدة
          </button>
        )}
      </div>

      <div className="flex gap-2 border-b border-outline-variant">
        <button
          onClick={() => setTab("rooms")}
          className={`px-4 py-2.5 text-body-md font-semibold border-b-2 transition-colors ${tab === "rooms" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}
        >
          الغرف
        </button>
        <button
          onClick={() => setTab("reservations")}
          className={`px-4 py-2.5 text-body-md font-semibold border-b-2 transition-colors ${tab === "reservations" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}
        >
          الحجوزات النشطة
        </button>
      </div>

      {tab === "rooms" ? (
        <>
          {error && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {error}</div>}

          {loading ? (
            <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
          ) : rooms.length === 0 ? (
            <div className="glass-card rounded-xl flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2"><BedDouble className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد غرف مسجّلة بعد.</p></div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-gutter">
              {rooms.map((r) => (
                <div key={r.id} className="glass-card rounded-xl p-card-padding">
                  <div className="flex justify-between items-start mb-3">
                    <div className="w-10 h-10 rounded-lg bg-primary-container/10 text-primary flex items-center justify-center"><BedDouble className="w-5 h-5" /></div>
                    <span className={`px-2 py-1 rounded text-[11px] font-bold ${r.is_active ? "bg-secondary-container/30 text-secondary" : "bg-surface-container text-on-surface-variant"}`}>{r.is_active ? "متاحة" : "غير نشطة"}</span>
                  </div>
                  <h3 className="font-headline-sm text-headline-sm text-on-surface">{r.name}</h3>
                  <p className="text-body-sm text-outline font-data-mono" dir="ltr">{r.code}</p>
                  <div className="flex items-center gap-3 mt-3 text-body-sm text-on-surface-variant">
                    <span>{r.attributes.room_type}</span>
                    <span className="flex items-center gap-1"><Users2 className="w-3.5 h-3.5" /> {r.attributes.capacity}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {modalOpen && <CreateRoomModal onClose={() => setModalOpen(false)} onCreated={() => { setModalOpen(false); fetchAll(); }} />}
        </>
      ) : (
        <ReservationsTab rooms={rooms} />
      )}
    </div>
  );
}

function CreateRoomModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<FormIn, any, FormOut>({
    resolver: zodResolver(schema),
    defaultValues: { code: "", name: "", room_type: "double", floor: 1, capacity: 2, base_rate: 0 },
  });

  const onSubmit = async (data: FormOut) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/hospitality/rooms", {
        code: data.code,
        name: data.name,
        attributes: { room_type: data.room_type, floor: data.floor, capacity: data.capacity, base_rate: data.base_rate },
      });
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, "تعذر إضافة الغرفة. تأكد من تفعيل موديول الضيافة أولاً."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">غرفة جديدة</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">رقم الغرفة</label><input {...register("code")} dir="ltr" className="input-field font-mono" />{errors.code && <p className="text-body-sm text-error">{errors.code.message}</p>}</div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">اسم الغرفة</label><input {...register("name")} className="input-field" />{errors.name && <p className="text-body-sm text-error">{errors.name.message}</p>}</div>
          </div>
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">النوع</label>
            <select {...register("room_type")} className="input-field">
              {roomTypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الدور</label><input type="number" {...register("floor")} dir="ltr" className="input-field font-mono" /></div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">السعة</label><input type="number" {...register("capacity")} dir="ltr" className="input-field font-mono" /></div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">السعر/ليلة</label><input type="number" step="0.01" {...register("base_rate")} dir="ltr" className="input-field font-mono" /></div>
          </div>
          <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الغرفة
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Reservations Tab ────────────────────────────────────────────────────────

function ReservationsTab({ rooms }: { rooms: Room[] }) {
  const queryClient = useQueryClient();
  const [newModalOpen, setNewModalOpen] = useState(false);
  const [folioCaseId, setFolioCaseId] = useState<string | null>(null);
  const [showClosed, setShowClosed] = useState(false);

  const { data: caseTypes } = useQuery({
    queryKey: ["case-types", "hospitality"],
    queryFn: async () => {
      const res = await apiClient.get<CaseType[]>("/case-types", { params: { plugin_key: "hospitality" } });
      return res.data;
    },
  });
  const caseType = caseTypes?.find((c) => c.code === "room_reservation");

  const { data: reservations, isLoading, isError } = useQuery({
    queryKey: ["hospitality-reservations", caseType?.id],
    enabled: !!caseType,
    queryFn: async () => {
      const res = await apiClient.get<Reservation[]>("/cases", { params: { case_type_id: caseType!.id } });
      return res.data;
    },
  });

  const roomById = new Map(rooms.map((r) => [r.id, r]));
  const visible = (reservations ?? []).filter((r) => showClosed || !["closed", "cancelled"].includes(r.current_stage));

  const transitionMutation = useMutation({
    mutationFn: async ({ id, to_stage, data_patch }: { id: string; to_stage: string; data_patch?: Record<string, any> }) =>
      apiClient.post(`/cases/${id}/transition`, { to_stage, data_patch }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["hospitality-reservations"] }),
  });

  if (!caseType) {
    return (
      <div className="glass-card rounded-xl flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
        <BedDouble className="w-8 h-8 text-outline-variant" />
        <p className="text-body-md">موديول الحجوزات غير مفعّل بعد. فعّله من صفحة الحالات أولاً.</p>
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
          <Plus className="w-4 h-4" /> حجز جديد
        </button>
      </div>

      <div className="glass-card rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : isError ? (
          <div className="flex items-center gap-2 p-6 text-body-sm text-error"><AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الحجوزات.</div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
            <BedDouble className="w-7 h-7 text-outline-variant" />
            <p className="text-body-sm">لا توجد حجوزات نشطة.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">الضيف</th>
                  <th className="px-6 py-4">الغرفة</th>
                  <th className="px-6 py-4">الوصول</th>
                  <th className="px-6 py-4">المغادرة</th>
                  <th className="px-6 py-4">الحالة</th>
                  <th className="px-6 py-4" />
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {visible.map((r) => {
                  const room = r.resource_id ? roomById.get(r.resource_id) : undefined;
                  return (
                    <tr key={r.id} className="hover:bg-surface-container-lowest transition-colors">
                      <td className="px-6 py-4 font-medium">{r.data?.guest_name ?? "—"}</td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{room ? `${room.code} · ${room.name}` : "—"}</td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{r.start_date ?? "—"}</td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{r.end_date ?? "—"}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-[11px] font-bold ${stageTone[r.current_stage] ?? ""}`}>
                          {stageLabel[r.current_stage] ?? r.current_stage}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3 flex-wrap">
                          <button
                            onClick={() => setFolioCaseId(r.id)}
                            className="flex items-center gap-1.5 text-primary font-semibold text-body-sm hover:underline"
                          >
                            <Receipt className="w-3.5 h-3.5" /> الفاتورة
                          </button>
                          {(r.current_stage === "booked" || r.current_stage === "confirmed") && (
                            <button
                              disabled={transitionMutation.isPending}
                              onClick={() => transitionMutation.mutate({ id: r.id, to_stage: "checked_in", data_patch: { checkin_actual: new Date().toISOString() } })}
                              className="flex items-center gap-1.5 text-secondary font-semibold text-body-sm hover:underline disabled:opacity-50"
                            >
                              <LogIn className="w-3.5 h-3.5" /> تسجيل الدخول
                            </button>
                          )}
                          {r.current_stage === "checked_in" && (
                            <button
                              disabled={transitionMutation.isPending}
                              onClick={() => transitionMutation.mutate({ id: r.id, to_stage: "checked_out", data_patch: { checkout_actual: new Date().toISOString(), payment_method: "cash" } })}
                              className="flex items-center gap-1.5 text-tertiary font-semibold text-body-sm hover:underline disabled:opacity-50"
                            >
                              <LogOut className="w-3.5 h-3.5" /> تسجيل المغادرة
                            </button>
                          )}
                          {r.current_stage === "checked_out" && (
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
        <NewReservationModal
          caseTypeId={caseType.id}
          rooms={rooms}
          onClose={() => setNewModalOpen(false)}
          onCreated={() => { setNewModalOpen(false); queryClient.invalidateQueries({ queryKey: ["hospitality-reservations"] }); }}
        />
      )}
      {folioCaseId && <FolioModal caseId={folioCaseId} onClose={() => setFolioCaseId(null)} />}
    </div>
  );
}

// ── New Reservation Modal (includes availability search) ───────────────────

const reservationSchema = z.object({
  guest_name: z.string().min(1, "اسم الضيف مطلوب"),
  guest_phone: z.string().optional(),
  guest_count: z.coerce.number().min(1),
  daily_rate: z.coerce.number().min(0),
  board_type: z.string().min(1),
  check_in: z.string().min(1, "تاريخ الوصول مطلوب"),
  check_out: z.string().min(1, "تاريخ المغادرة مطلوب"),
});
type ReservationOut = z.output<typeof reservationSchema>;
type ReservationIn = z.input<typeof reservationSchema>;

function NewReservationModal({
  caseTypeId,
  rooms,
  onClose,
  onCreated,
}: {
  caseTypeId: string;
  rooms: Room[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [selectedRoomId, setSelectedRoomId] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, watch, formState: { errors } } = useForm<ReservationIn, any, ReservationOut>({
    resolver: zodResolver(reservationSchema),
    defaultValues: { guest_name: "", guest_phone: "", guest_count: 1, daily_rate: 0, board_type: "room_only", check_in: "", check_out: "" },
  });

  const checkIn = watch("check_in");
  const checkOut = watch("check_out");

  const { data: availability, isFetching: checkingAvailability } = useQuery({
    queryKey: ["room-availability", checkIn, checkOut],
    enabled: !!checkIn && !!checkOut && checkOut > checkIn,
    queryFn: async () => {
      const res = await apiClient.get<RoomAvailability[]>("/hospitality/rooms/availability", {
        params: { check_in: checkIn, check_out: checkOut },
      });
      return res.data;
    },
  });

  const availableRoomIds = new Set((availability ?? []).filter((r) => r.is_available).map((r) => r.id));
  const roomsToShow = availability ?? rooms.map((r) => ({ ...r, is_available: true, conflicting_case_id: null }));

  const mutation = useMutation({
    mutationFn: async (data: ReservationOut) => {
      if (!selectedRoomId) throw new Error("NO_ROOM");
      return apiClient.post("/cases", {
        case_type_id: caseTypeId,
        resource_id: selectedRoomId,
        title: `حجز — ${data.guest_name}`,
        start_date: data.check_in,
        end_date: data.check_out,
        data: {
          guest_name: data.guest_name,
          guest_phone: data.guest_phone || undefined,
          guest_count: data.guest_count,
          daily_rate: data.daily_rate,
          board_type: data.board_type,
        },
      });
    },
    onSuccess: onCreated,
    onError: (err) => {
      if ((err as Error).message === "NO_ROOM") {
        setErrorMsg("اختر غرفة متاحة أولاً.");
        return;
      }
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, "تعذر إنشاء الحجز."));
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-lg bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">حجز جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">تاريخ الوصول</label><input type="date" {...register("check_in")} dir="ltr" className="input-field font-mono" />{errors.check_in && <p className="text-body-sm text-error">{errors.check_in.message}</p>}</div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">تاريخ المغادرة</label><input type="date" {...register("check_out")} dir="ltr" className="input-field font-mono" />{errors.check_out && <p className="text-body-sm text-error">{errors.check_out.message}</p>}</div>
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant flex items-center gap-1.5">
              <CalendarSearch className="w-4 h-4" /> اختر غرفة متاحة
            </label>
            {!checkIn || !checkOut ? (
              <p className="text-body-sm text-outline">اختر التواريخ أولاً لعرض الغرف المتاحة.</p>
            ) : checkingAvailability ? (
              <div className="flex items-center gap-2 text-body-sm text-on-surface-variant"><Loader2 className="w-4 h-4 animate-spin" /> جاري البحث...</div>
            ) : (
              <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto">
                {roomsToShow.map((r) => (
                  <button
                    type="button"
                    key={r.id}
                    disabled={!availableRoomIds.has(r.id) && !!availability}
                    onClick={() => setSelectedRoomId(r.id)}
                    className={`text-right px-3 py-2 rounded-lg border text-body-sm transition-colors ${
                      selectedRoomId === r.id
                        ? "border-primary bg-primary-container/10 text-primary font-semibold"
                        : availability && !availableRoomIds.has(r.id)
                        ? "border-outline-variant text-outline opacity-50 cursor-not-allowed"
                        : "border-outline-variant hover:bg-surface-container"
                    }`}
                  >
                    {r.code} · {r.name}
                    {availability && !availableRoomIds.has(r.id) && <span className="block text-[11px] text-error">محجوزة</span>}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">اسم الضيف</label><input {...register("guest_name")} className="input-field" />{errors.guest_name && <p className="text-body-sm text-error">{errors.guest_name.message}</p>}</div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">رقم الهاتف</label><input {...register("guest_phone")} dir="ltr" className="input-field font-mono" /></div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">عدد الضيوف</label><input type="number" {...register("guest_count")} dir="ltr" className="input-field font-mono" /></div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">السعر لليلة (ج.م)</label><input type="number" step="0.01" {...register("daily_rate")} dir="ltr" className="input-field font-mono" /></div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">نوع الإقامة</label>
              <select {...register("board_type")} className="input-field">
                <option value="room_only">غرفة فقط</option>
                <option value="bed_breakfast">إفطار</option>
                <option value="half_board">نصف إقامة</option>
                <option value="full_board">إقامة كاملة</option>
                <option value="all_inclusive">شامل كل شيء</option>
              </select>
            </div>
          </div>

          <button type="submit" disabled={mutation.isPending} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {mutation.isPending && <Loader2 className="w-4 h-4 animate-spin" />} تأكيد الحجز
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Folio Modal ──────────────────────────────────────────────────────────────

const chargeSchema = z.object({
  category: z.string().min(1),
  description: z.string().min(1, "الوصف مطلوب"),
  amount: z.coerce.number(),
  quantity: z.coerce.number().min(0.01).default(1),
});
type ChargeOut = z.output<typeof chargeSchema>;
type ChargeIn = z.input<typeof chargeSchema>;

const chargeCategories = [
  { value: "restaurant", label: "مطعم" },
  { value: "laundry", label: "غسيل ملابس" },
  { value: "minibar", label: "ميني بار" },
  { value: "spa", label: "سبا" },
  { value: "telephone", label: "مكالمات" },
  { value: "transport", label: "مواصلات" },
  { value: "discount", label: "خصم (سالب)" },
  { value: "deposit", label: "عربون (سالب)" },
  { value: "other", label: "أخرى" },
];

function FolioModal({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: folio, isLoading, isError } = useQuery({
    queryKey: ["folio", caseId],
    queryFn: async () => {
      const res = await apiClient.get<FolioSummary>(`/hospitality/reservations/${caseId}/folio`);
      return res.data;
    },
  });

  const { register, handleSubmit, reset, formState: { errors } } = useForm<ChargeIn, any, ChargeOut>({
    resolver: zodResolver(chargeSchema),
    defaultValues: { category: "restaurant", description: "", amount: 0, quantity: 1 },
  });

  const addCharge = useMutation({
    mutationFn: async (data: ChargeOut) =>
      apiClient.post(`/hospitality/reservations/${caseId}/folio/items`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["folio", caseId] });
      reset({ category: "restaurant", description: "", amount: 0, quantity: 1 });
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-2xl bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">فاتورة الحجز</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-10 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
        ) : isError || !folio ? (
          <div className="flex items-center gap-2 p-4 text-body-sm text-error"><AlertCircle className="w-4 h-4 shrink-0" /> تعذر تحميل الفاتورة.</div>
        ) : (
          <>
            <div className="text-body-sm text-on-surface-variant mb-3" dir="ltr">
              {folio.check_in} → {folio.check_out} ({folio.nights} ليالي)
            </div>
            <div className="border border-outline-variant rounded-lg overflow-hidden mb-4">
              <table className="w-full text-right text-body-sm">
                <tbody className="divide-y divide-outline-variant/30">
                  {folio.lines.map((line, i) => (
                    <tr key={i}>
                      <td className="px-4 py-2">{line.description}</td>
                      <td className="px-4 py-2 font-data-mono text-left" dir="ltr">{egp(line.amount)}</td>
                    </tr>
                  ))}
                  <tr className="bg-surface-container-low font-bold">
                    <td className="px-4 py-2">الإجمالي</td>
                    <td className="px-4 py-2 font-data-mono text-left" dir="ltr">{egp(folio.total)}</td>
                  </tr>
                  {Number(folio.deposit_total) > 0 && (
                    <tr>
                      <td className="px-4 py-2">المتبقي بعد العربون</td>
                      <td className="px-4 py-2 font-data-mono text-left" dir="ltr">{egp(folio.balance_due)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <form onSubmit={handleSubmit((d) => addCharge.mutate(d))} className="space-y-3 bg-surface-container-low rounded-lg p-4">
              <p className="text-body-sm font-semibold text-on-surface-variant">إضافة رسم إلى الفاتورة</p>
              {addCharge.isError && (
                <div className="flex items-center gap-2 bg-error-container text-on-error-container p-2.5 rounded-lg text-body-sm font-medium border border-error">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  {pickDetail(addCharge.error, "تعذر إضافة الرسم.")}
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <select {...register("category")} className="input-field">
                  {chargeCategories.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
                <input {...register("description")} placeholder="الوصف" className="input-field" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <input type="number" step="0.01" {...register("amount")} placeholder="المبلغ" dir="ltr" className="input-field font-mono" />
                <input type="number" step="0.01" {...register("quantity")} placeholder="الكمية" dir="ltr" className="input-field font-mono" />
              </div>
              {(errors.description || errors.amount) && (
                <p className="text-body-sm text-error">{errors.description?.message || errors.amount?.message}</p>
              )}
              <button type="submit" disabled={addCharge.isPending} className="flex items-center gap-2 h-10 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-70">
                {addCharge.isPending && <Loader2 className="w-4 h-4 animate-spin" />} إضافة
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
