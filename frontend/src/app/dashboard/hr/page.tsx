"use client";

import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, getApiErrorMessage, pickDetail } from "@/lib/api-client";
import { Users, Wallet, Plus, Loader2, AlertCircle, X, CheckCircle2 } from "lucide-react";

type EmployeeStatus = "ACTIVE" | "ON_LEAVE" | "TERMINATED";
type PayslipStatus = "DRAFT" | "APPROVED" | "PAID";

interface Employee {
  id: string;
  first_name: string;
  last_name: string;
  national_id: string;
  base_salary: string | number;
  hire_date: string;
  status: EmployeeStatus;
}

interface Payslip {
  id: string;
  employee_id: string;
  period_start: string;
  period_end: string;
  basic_wage: string | number;
  allowances: string | number;
  deductions: string | number;
  net_pay: string | number;
  status: PayslipStatus;
}

const egp = (v: string | number) => `${Number(v).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;
const empStatusLabel: Record<EmployeeStatus, string> = { ACTIVE: "نشط", ON_LEAVE: "إجازة", TERMINATED: "منتهي الخدمة" };
const empStatusTone: Record<EmployeeStatus, string> = {
  ACTIVE: "bg-secondary-container/30 text-secondary",
  ON_LEAVE: "bg-primary-container/10 text-primary",
  TERMINATED: "bg-error-container/40 text-error",
};
const paySlipLabel: Record<PayslipStatus, string> = { DRAFT: "مسودة", APPROVED: "معتمد", PAID: "مدفوع" };
const paySlipTone: Record<PayslipStatus, string> = {
  DRAFT: "bg-primary-container/10 text-primary",
  APPROVED: "bg-tertiary-container/10 text-tertiary",
  PAID: "bg-secondary-container/30 text-secondary",
};

const employeeSchema = z.object({
  first_name: z.string().min(1, "الاسم الأول مطلوب"),
  last_name: z.string().min(1, "الاسم الأخير مطلوب"),
  national_id: z.string().min(1, "الرقم القومي مطلوب"),
  base_salary: z.coerce.number().min(0, "الراتب لازم يكون رقم موجب"),
  hire_date: z.string().min(1, "تاريخ التعيين مطلوب"),
});
type EmployeeFormOut = z.output<typeof employeeSchema>;
type EmployeeFormIn = z.input<typeof employeeSchema>;

const payslipSchema = z.object({
  employee_id: z.string().min(1, "اختر الموظف"),
  period_start: z.string().min(1, "بداية الفترة مطلوبة"),
  period_end: z.string().min(1, "نهاية الفترة مطلوبة"),
  basic_wage: z.coerce.number().min(0),
  allowances: z.coerce.number().min(0).default(0),
  deductions: z.coerce.number().min(0).default(0),
});
type PayslipFormOut = z.output<typeof payslipSchema>;
type PayslipFormIn = z.input<typeof payslipSchema>;

export default function HRPage() {
  const [tab, setTab] = useState<"employees" | "payslips">("employees");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [payslips, setPayslips] = useState<Payslip[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [empModalOpen, setEmpModalOpen] = useState(false);
  const [paySlipModalOpen, setPaySlipModalOpen] = useState(false);
  const [approvingId, setApprovingId] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [empRes, paysRes] = await Promise.all([
        apiClient.get<Employee[]>("/hr/employees"),
        apiClient.get<Payslip[]>("/hr/payslips"),
      ]);
      setEmployees(empRes.data);
      setPayslips(paysRes.data);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل بيانات الموارد البشرية."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const employeesById = new Map(employees.map((e) => [e.id, e]));

  const approve = async (id: string) => {
    setApprovingId(id);
    try {
      await apiClient.post(`/hr/payslips/${id}/approve`, {});
      await fetchAll();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(pickDetail(axiosErr, "تعذر اعتماد القسيمة."));
    } finally {
      setApprovingId(null);
    }
  };

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الموارد البشرية</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">الموظفون وقسائم الرواتب.</p>
        </div>
        <button
          onClick={() => (tab === "employees" ? setEmpModalOpen(true) : setPaySlipModalOpen(true))}
          className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit"
        >
          <Plus className="w-4 h-4" /> {tab === "employees" ? "موظف جديد" : "قسيمة راتب جديدة"}
        </button>
      </div>

      <div className="flex gap-2 border-b border-outline-variant">
        <button onClick={() => setTab("employees")} className={`flex items-center gap-2 px-4 py-3 text-body-md font-semibold border-b-2 transition-colors ${tab === "employees" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}>
          <Users className="w-4 h-4" /> الموظفون
        </button>
        <button onClick={() => setTab("payslips")} className={`flex items-center gap-2 px-4 py-3 text-body-md font-semibold border-b-2 transition-colors ${tab === "payslips" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"}`}>
          <Wallet className="w-4 h-4" /> قسائم الرواتب
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2"><Loader2 className="w-5 h-5 animate-spin" /> جاري التحميل...</div>
      ) : tab === "employees" ? (
        <div className="glass-card rounded-xl overflow-hidden">
          {employees.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2"><Users className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا يوجد موظفون مسجّلون بعد.</p></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-right">
                <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                  <tr><th className="px-6 py-4">الاسم</th><th className="px-6 py-4">الرقم القومي</th><th className="px-6 py-4">الراتب الأساسي</th><th className="px-6 py-4">تاريخ التعيين</th><th className="px-6 py-4">الحالة</th></tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30 text-body-md">
                  {employees.map((e) => (
                    <tr key={e.id} className="hover:bg-surface-container-lowest transition-colors">
                      <td className="px-6 py-4 font-medium">{e.first_name} {e.last_name}</td>
                      <td className="px-6 py-4 font-data-mono text-on-surface-variant" dir="ltr">{e.national_id}</td>
                      <td className="px-6 py-4 font-data-mono" dir="ltr">{egp(e.base_salary)}</td>
                      <td className="px-6 py-4 text-outline">{new Date(e.hire_date).toLocaleDateString("ar-EG")}</td>
                      <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${empStatusTone[e.status]}`}>{empStatusLabel[e.status]}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="glass-card rounded-xl overflow-hidden">
          {payslips.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2"><Wallet className="w-8 h-8 text-outline-variant" /><p className="text-body-md">لا توجد قسائم رواتب بعد.</p></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-right">
                <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                  <tr><th className="px-6 py-4">الموظف</th><th className="px-6 py-4">الفترة</th><th className="px-6 py-4">صافي الراتب</th><th className="px-6 py-4">الحالة</th><th className="px-6 py-4" /></tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/30 text-body-md">
                  {payslips.map((p) => {
                    const emp = employeesById.get(p.employee_id);
                    const net = Number(p.basic_wage) + Number(p.allowances) - Number(p.deductions);
                    return (
                      <tr key={p.id} className="hover:bg-surface-container-lowest transition-colors">
                        <td className="px-6 py-4 font-medium">{emp ? `${emp.first_name} ${emp.last_name}` : "—"}</td>
                        <td className="px-6 py-4 text-outline">{new Date(p.period_start).toLocaleDateString("ar-EG")} - {new Date(p.period_end).toLocaleDateString("ar-EG")}</td>
                        <td className="px-6 py-4 font-data-mono font-bold" dir="ltr">{egp(p.net_pay || net)}</td>
                        <td className="px-6 py-4"><span className={`px-2 py-1 rounded text-[11px] font-bold ${paySlipTone[p.status]}`}>{paySlipLabel[p.status]}</span></td>
                        <td className="px-6 py-4">
                          {p.status === "DRAFT" && (
                            <button onClick={() => approve(p.id)} disabled={approvingId === p.id} className="flex items-center gap-1 text-secondary font-semibold text-body-sm hover:underline disabled:opacity-50">
                              {approvingId === p.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />} اعتماد
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {empModalOpen && (
        <CreateEmployeeModal onClose={() => setEmpModalOpen(false)} onCreated={() => { setEmpModalOpen(false); fetchAll(); }} />
      )}
      {paySlipModalOpen && (
        <CreatePayslipModal employees={employees} onClose={() => setPaySlipModalOpen(false)} onCreated={() => { setPaySlipModalOpen(false); fetchAll(); }} />
      )}
    </div>
  );
}

function CreateEmployeeModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<EmployeeFormIn, any, EmployeeFormOut>({
    resolver: zodResolver(employeeSchema),
    defaultValues: { first_name: "", last_name: "", national_id: "", base_salary: 0, hire_date: "" },
  });

  const onSubmit = async (data: EmployeeFormOut) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/hr/employees", data);
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, "تعذر إضافة الموظف."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">موظف جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الاسم الأول</label><input {...register("first_name")} className="input-field" />{errors.first_name && <p className="text-body-sm text-error">{errors.first_name.message}</p>}</div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الاسم الأخير</label><input {...register("last_name")} className="input-field" />{errors.last_name && <p className="text-body-sm text-error">{errors.last_name.message}</p>}</div>
          </div>
          <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الرقم القومي</label><input {...register("national_id")} dir="ltr" className="input-field font-mono" />{errors.national_id && <p className="text-body-sm text-error">{errors.national_id.message}</p>}</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الراتب الأساسي</label><input type="number" step="0.01" {...register("base_salary")} dir="ltr" className="input-field font-mono" />{errors.base_salary && <p className="text-body-sm text-error">{errors.base_salary.message}</p>}</div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">تاريخ التعيين</label><input type="date" {...register("hire_date")} dir="ltr" className="input-field font-mono" />{errors.hire_date && <p className="text-body-sm text-error">{errors.hire_date.message}</p>}</div>
          </div>
          <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />} حفظ الموظف
          </button>
        </form>
      </div>
    </div>
  );
}

function CreatePayslipModal({ employees, onClose, onCreated }: { employees: Employee[]; onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<PayslipFormIn, any, PayslipFormOut>({
    resolver: zodResolver(payslipSchema),
    defaultValues: { employee_id: "", period_start: "", period_end: "", basic_wage: 0, allowances: 0, deductions: 0 },
  });

  const onSubmit = async (data: PayslipFormOut) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/hr/payslips", data);
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, "تعذر إنشاء قسيمة الراتب."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">قسيمة راتب جديدة</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors"><X className="w-5 h-5" /></button>
        </div>
        {errorMsg && <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error"><AlertCircle className="w-4 h-4 shrink-0" /> {errorMsg}</div>}
        {employees.length === 0 ? (
          <p className="text-body-sm text-on-surface-variant">أضف موظف واحد على الأقل قبل إنشاء قسيمة راتب.</p>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">الموظف</label>
              <select {...register("employee_id")} className="input-field">
                <option value="">اختر الموظف</option>
                {employees.map((e) => <option key={e.id} value={e.id}>{e.first_name} {e.last_name}</option>)}
              </select>
              {errors.employee_id && <p className="text-body-sm text-error">{errors.employee_id.message}</p>}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">بداية الفترة</label><input type="date" {...register("period_start")} dir="ltr" className="input-field font-mono" />{errors.period_start && <p className="text-body-sm text-error">{errors.period_start.message}</p>}</div>
              <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">نهاية الفترة</label><input type="date" {...register("period_end")} dir="ltr" className="input-field font-mono" />{errors.period_end && <p className="text-body-sm text-error">{errors.period_end.message}</p>}</div>
            </div>
            <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الراتب الأساسي</label><input type="number" step="0.01" {...register("basic_wage")} dir="ltr" className="input-field font-mono" />{errors.basic_wage && <p className="text-body-sm text-error">{errors.basic_wage.message}</p>}</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">البدلات</label><input type="number" step="0.01" {...register("allowances")} dir="ltr" className="input-field font-mono" /></div>
              <div className="space-y-1.5"><label className="text-body-sm font-semibold text-on-surface-variant">الخصومات</label><input type="number" step="0.01" {...register("deductions")} dir="ltr" className="input-field font-mono" /></div>
            </div>
            <button type="submit" disabled={submitting} className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2">
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />} حفظ القسيمة
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
