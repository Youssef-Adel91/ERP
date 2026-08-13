"use client";

import { useCallback, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, getApiErrorMessage, pickDetail } from "@/lib/api-client";
import {
  BookOpenText,
  ScrollText,
  Plus,
  Loader2,
  AlertCircle,
  X,
  CheckCircle2,
} from "lucide-react";

type AccountType = "ASSET" | "LIABILITY" | "EQUITY" | "REVENUE" | "EXPENSE";
type JournalEntryStatus = "DRAFT" | "POSTED" | "VOIDED";

interface Account {
  id: string;
  code: string;
  name: string;
  name_ar: string | null;
  account_type: AccountType;
  is_active: boolean;
  is_system: boolean;
  created_at: string;
}

interface TransactionLine {
  id: string;
  account_code: string;
  account_name: string;
  debit: string | number;
  credit: string | number;
  description: string | null;
}

interface JournalEntry {
  id: string;
  reference: string;
  description: string;
  status: JournalEntryStatus;
  source_type: string | null;
  created_at: string;
  posted_at: string | null;
  lines: TransactionLine[];
}

const accountTypeLabel: Record<AccountType, string> = {
  ASSET: "أصول",
  LIABILITY: "خصوم",
  EQUITY: "حقوق ملكية",
  REVENUE: "إيرادات",
  EXPENSE: "مصروفات",
};

const statusLabel: Record<JournalEntryStatus, string> = {
  DRAFT: "مسودة",
  POSTED: "مرحّل",
  VOIDED: "ملغي",
};

const statusTone: Record<JournalEntryStatus, string> = {
  DRAFT: "bg-primary-container/10 text-primary",
  POSTED: "bg-secondary-container/30 text-secondary",
  VOIDED: "bg-error-container/40 text-error",
};

const egp = (value: string | number) => `${Number(value).toLocaleString("ar-EG", { maximumFractionDigits: 0 })} ج.م`;

const createAccountSchema = z.object({
  code: z.string().min(1, "الكود مطلوب"),
  name: z.string().min(1, "الاسم مطلوب"),
  account_type: z.enum(["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"]),
});
type CreateAccountForm = z.infer<typeof createAccountSchema>;

export default function AccountingPage() {
  const [tab, setTab] = useState<"accounts" | "entries">("entries");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [postingId, setPostingId] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [accountsRes, entriesRes] = await Promise.all([
        apiClient.get<Account[]>("/accounting/accounts"),
        apiClient.get<JournalEntry[]>("/accounting/journal-entries", { params: { limit: 100 } }),
      ]);
      setAccounts(accountsRes.data);
      setEntries(entriesRes.data);
    } catch (err) {
      setError(getApiErrorMessage(err, "تعذر تحميل بيانات الحسابات."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const postEntry = async (id: string) => {
    setPostingId(id);
    try {
      await apiClient.post(`/accounting/journal-entries/${id}/post`, {});
      await fetchAll();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setError(pickDetail(axiosErr, "تعذر ترحيل القيد."));
    } finally {
      setPostingId(null);
    }
  };

  return (
    <div className="space-y-gutter">
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface mb-1">الحسابات والقيود</h1>
          <p className="font-body-md text-body-md text-on-surface-variant">شجرة الحسابات والقيود المحاسبية اليومية.</p>
        </div>
        {tab === "accounts" && (
          <button
            onClick={() => setModalOpen(true)}
            className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit"
          >
            <Plus className="w-4 h-4" />
            حساب جديد
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-outline-variant">
        <button
          onClick={() => setTab("entries")}
          className={`flex items-center gap-2 px-4 py-3 text-body-md font-semibold border-b-2 transition-colors ${
            tab === "entries" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          <ScrollText className="w-4 h-4" />
          القيود المحاسبية
        </button>
        <button
          onClick={() => setTab("accounts")}
          className={`flex items-center gap-2 px-4 py-3 text-body-md font-semibold border-b-2 transition-colors ${
            tab === "accounts" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          <BookOpenText className="w-4 h-4" />
          شجرة الحسابات
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
          <Loader2 className="w-5 h-5 animate-spin" />
          جاري التحميل...
        </div>
      ) : tab === "accounts" ? (
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                <tr>
                  <th className="px-6 py-4">الكود</th>
                  <th className="px-6 py-4">اسم الحساب</th>
                  <th className="px-6 py-4">النوع</th>
                  <th className="px-6 py-4">الحالة</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/30 text-body-md">
                {accounts.map((a) => (
                  <tr key={a.id} className="hover:bg-surface-container-lowest transition-colors">
                    <td className="px-6 py-4 font-data-mono" dir="ltr">{a.code}</td>
                    <td className="px-6 py-4 font-medium">{a.name_ar || a.name}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{accountTypeLabel[a.account_type]}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded text-[11px] font-bold ${a.is_active ? "bg-secondary-container/30 text-secondary" : "bg-surface-container text-on-surface-variant"}`}>
                        {a.is_active ? "نشط" : "غير نشط"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {entries.length === 0 ? (
            <div className="glass-card rounded-xl flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
              <ScrollText className="w-8 h-8 text-outline-variant" />
              <p className="text-body-md">لا توجد قيود محاسبية بعد.</p>
            </div>
          ) : (
            entries.map((entry) => {
              const total = entry.lines.reduce((sum, l) => sum + Number(l.debit || 0), 0);
              return (
                <div key={entry.id} className="glass-card rounded-xl p-card-padding">
                  <div className="flex flex-wrap justify-between items-center gap-3 mb-4">
                    <div className="flex items-center gap-3">
                      <span className="font-data-mono text-body-sm text-on-surface-variant" dir="ltr">{entry.reference}</span>
                      <span className={`px-2 py-1 rounded text-[11px] font-bold ${statusTone[entry.status]}`}>
                        {statusLabel[entry.status]}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-data-mono font-bold text-body-md" dir="ltr">{egp(total)}</span>
                      {entry.status === "DRAFT" && (
                        <button
                          onClick={() => postEntry(entry.id)}
                          disabled={postingId === entry.id}
                          className="flex items-center gap-1 bg-secondary text-on-secondary px-3 py-1.5 rounded-lg text-body-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-70"
                        >
                          {postingId === entry.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                          ترحيل
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="text-body-md text-on-surface mb-4">{entry.description}</p>
                  <div className="overflow-x-auto rounded-lg border border-outline-variant">
                    <table className="w-full text-right text-body-sm">
                      <thead className="bg-surface-container-low text-outline">
                        <tr>
                          <th className="px-4 py-2">الحساب</th>
                          <th className="px-4 py-2">مدين</th>
                          <th className="px-4 py-2">دائن</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-outline-variant/30">
                        {entry.lines.map((line) => (
                          <tr key={line.id}>
                            <td className="px-4 py-2 font-medium">{line.account_name} <span className="text-outline font-data-mono" dir="ltr">({line.account_code})</span></td>
                            <td className="px-4 py-2 font-data-mono" dir="ltr">{Number(line.debit) > 0 ? egp(line.debit) : "—"}</td>
                            <td className="px-4 py-2 font-data-mono" dir="ltr">{Number(line.credit) > 0 ? egp(line.credit) : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {modalOpen && (
        <CreateAccountModal
          onClose={() => setModalOpen(false)}
          onCreated={() => {
            setModalOpen(false);
            fetchAll();
          }}
        />
      )}
    </div>
  );
}

function CreateAccountModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateAccountForm>({
    resolver: zodResolver(createAccountSchema),
    defaultValues: { code: "", name: "", account_type: "ASSET" },
  });

  const onSubmit = async (data: CreateAccountForm) => {
    setSubmitting(true);
    setErrorMsg("");
    try {
      await apiClient.post("/accounting/accounts", data);
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, "تعذر إنشاء الحساب."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">حساب جديد</h3>
          <button onClick={onClose} className="text-on-surface-variant hover:text-error transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {errorMsg && (
          <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-4 text-body-sm font-medium border border-error">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">الكود</label>
            <input
              {...register("code")}
              dir="ltr"
              placeholder="مثال: 1300"
              className={`w-full h-11 rounded-lg border bg-surface-container-low px-4 text-body-md text-on-surface outline-none text-right font-mono ${
                errors.code ? "border-error" : "border-outline-variant focus:border-primary focus:ring-2 focus:ring-primary/30"
              }`}
            />
            {errors.code && <p className="text-body-sm text-error">{errors.code.message}</p>}
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">اسم الحساب</label>
            <input
              {...register("name")}
              className={`w-full h-11 rounded-lg border bg-surface-container-low px-4 text-body-md text-on-surface outline-none text-right ${
                errors.name ? "border-error" : "border-outline-variant focus:border-primary focus:ring-2 focus:ring-primary/30"
              }`}
            />
            {errors.name && <p className="text-body-sm text-error">{errors.name.message}</p>}
          </div>

          <div className="space-y-1.5">
            <label className="text-body-sm font-semibold text-on-surface-variant">نوع الحساب</label>
            <select
              {...register("account_type")}
              className="w-full h-11 rounded-lg border border-outline-variant bg-surface-container-low px-4 text-body-md text-on-surface outline-none text-right focus:border-primary focus:ring-2 focus:ring-primary/30"
            >
              {Object.entries(accountTypeLabel).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            حفظ الحساب
          </button>
        </form>
      </div>
    </div>
  );
}
