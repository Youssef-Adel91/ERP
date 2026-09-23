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
  BarChart3,
  Lock,
  Unlock,
  CalendarClock,
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

interface TrialBalanceRow {
  account_id: string | null;
  account_code: string;
  account_name: string;
  account_type: string;
  total_debit: string | number;
  total_credit: string | number;
  net_balance: string | number;
  is_grand_total: boolean;
  is_balanced: boolean | null;
}

interface AccountingPeriod {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: "OPEN" | "CLOSED";
  closed_by: string | null;
  closed_at: string | null;
}

const createAccountSchema = z.object({
  code: z.string().min(1, "الكود مطلوب"),
  name: z.string().min(1, "الاسم مطلوب"),
  account_type: z.enum(["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"]),
});
type CreateAccountForm = z.infer<typeof createAccountSchema>;

export default function AccountingPage() {
  const [tab, setTab] = useState<"accounts" | "entries" | "reports" | "periods">("entries");
  const [periods, setPeriods] = useState<AccountingPeriod[]>([]);
  const [periodsLoading, setPeriodsLoading] = useState(false);
  const [periodsError, setPeriodsError] = useState("");
  const [periodsLoaded, setPeriodsLoaded] = useState(false);
  const [periodActionId, setPeriodActionId] = useState<string | null>(null);
  const [periodFilter, setPeriodFilter] = useState("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [journalModalOpen, setJournalModalOpen] = useState(false);
  const [postingId, setPostingId] = useState<string | null>(null);

  const [trialBalance, setTrialBalance] = useState<TrialBalanceRow[]>([]);
  const [tbLoading, setTbLoading] = useState(false);
  const [tbError, setTbError] = useState("");
  const [tbAsOfDate, setTbAsOfDate] = useState("");
  const [tbIncludeZero, setTbIncludeZero] = useState(false);
  const [tbLoaded, setTbLoaded] = useState(false);

  const fetchTrialBalance = useCallback(async () => {
    setTbLoading(true);
    setTbError("");
    try {
      const res = await apiClient.get<TrialBalanceRow[]>("/accounting/reports/trial-balance", {
        params: {
          as_of_date: tbAsOfDate || undefined,
          include_zero_balances: tbIncludeZero,
        },
      });
      setTrialBalance(res.data);
      setTbLoaded(true);
    } catch (err) {
      setTbError(getApiErrorMessage(err, "تعذر تحميل ميزان المراجعة."));
    } finally {
      setTbLoading(false);
    }
  }, [tbAsOfDate, tbIncludeZero]);

  useEffect(() => {
    if (tab === "reports" && !tbLoaded) {
      fetchTrialBalance();
    }
  }, [tab, tbLoaded, fetchTrialBalance]);

  const fetchPeriods = useCallback(async () => {
    setPeriodsLoading(true);
    setPeriodsError("");
    try {
      const res = await apiClient.get<AccountingPeriod[]>("/accounting/periods", { params: { limit: 1200 } });
      setPeriods(res.data);
      setPeriodsLoaded(true);
    } catch (err) {
      setPeriodsError(getApiErrorMessage(err, "تعذر تحميل الفترات المحاسبية."));
    } finally {
      setPeriodsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "periods" && !periodsLoaded) {
      fetchPeriods();
    }
  }, [tab, periodsLoaded, fetchPeriods]);

  const closePeriod = async (id: string) => {
    setPeriodActionId(id);
    setPeriodsError("");
    try {
      await apiClient.post(`/accounting/periods/${id}/close`, {});
      await fetchPeriods();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string | { message?: string } }>;
      setPeriodsError(pickDetail(axiosErr, "تعذر قفل الفترة. (لازم تكون OWNER)"));
    } finally {
      setPeriodActionId(null);
    }
  };

  const reopenPeriod = async (id: string) => {
    setPeriodActionId(id);
    setPeriodsError("");
    try {
      await apiClient.post(`/accounting/periods/${id}/reopen`, {});
      await fetchPeriods();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string | { message?: string } }>;
      setPeriodsError(pickDetail(axiosErr, "تعذر فتح الفترة. (لازم تكون OWNER)"));
    } finally {
      setPeriodActionId(null);
    }
  };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [accountsRes, entriesRes] = await Promise.allSettled([
        apiClient.get<Account[]>("/accounting/accounts"),
        apiClient.get<JournalEntry[]>("/accounting/journal-entries", { params: { limit: 100 } }),
      ]);
      if (accountsRes.status === "fulfilled") setAccounts(accountsRes.value.data);
      if (entriesRes.status === "fulfilled") setEntries(entriesRes.value.data);
      const failed = [accountsRes, entriesRes].find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
      if (failed) setError(getApiErrorMessage(failed.reason, "تعذر تحميل بعض بيانات الحسابات، جرّب التحديث."));
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
        {/* Bug fix (live-reproduced, 20 Sep 2026): the backend has always had
            full support for manual journal entries (POST /accounting/journal-entries,
            /post, /reverse — see router.py) but the "القيود المحاسبية" tab had no
            way to create one: only the "شجرة الحسابات" tab got a "+ جديد" button.
            Added the matching button here plus CreateJournalEntryModal below. */}
        {tab === "entries" && (
          <button
            onClick={() => setJournalModalOpen(true)}
            className="bg-primary text-on-primary px-4 py-2 rounded-lg flex items-center gap-2 text-body-md font-medium hover:opacity-90 transition-opacity w-fit"
          >
            <Plus className="w-4 h-4" />
            قيد يدوي جديد
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
        <button
          onClick={() => setTab("reports")}
          className={`flex items-center gap-2 px-4 py-3 text-body-md font-semibold border-b-2 transition-colors ${
            tab === "reports" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          ميزان المراجعة
        </button>
        <button
          onClick={() => setTab("periods")}
          className={`flex items-center gap-2 px-4 py-3 text-body-md font-semibold border-b-2 transition-colors ${
            tab === "periods" ? "border-primary text-primary" : "border-transparent text-on-surface-variant hover:text-on-surface"
          }`}
        >
          <CalendarClock className="w-4 h-4" />
          الفترات المحاسبية
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
      ) : tab === "reports" ? (
        <div className="space-y-4">
          <div className="glass-card rounded-xl p-card-padding flex flex-wrap items-end gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">حتى تاريخ</label>
              <input
                type="date"
                value={tbAsOfDate}
                onChange={(e) => { setTbAsOfDate(e.target.value); setTbLoaded(false); }}
                className="h-11 rounded-lg border border-outline-variant bg-surface-container-low px-4 text-body-md text-on-surface outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
                dir="ltr"
              />
            </div>
            <label className="flex items-center gap-2 h-11 text-body-sm font-medium text-on-surface-variant cursor-pointer">
              <input
                type="checkbox"
                checked={tbIncludeZero}
                onChange={(e) => { setTbIncludeZero(e.target.checked); setTbLoaded(false); }}
                className="w-4 h-4 accent-primary"
              />
              عرض الحسابات بدون رصيد
            </label>
            <button
              onClick={() => { setTbLoaded(false); fetchTrialBalance(); }}
              disabled={tbLoading}
              className="flex items-center gap-2 h-11 px-5 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70"
            >
              {tbLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              تحديث
            </button>
          </div>

          {tbError && (
            <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {tbError}
            </div>
          )}

          {tbLoading ? (
            <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
              <Loader2 className="w-5 h-5 animate-spin" />
              جاري التحميل...
            </div>
          ) : trialBalance.length === 0 ? (
            <div className="glass-card rounded-xl flex flex-col items-center justify-center py-16 text-on-surface-variant gap-2">
              <BarChart3 className="w-8 h-8 text-outline-variant" />
              <p className="text-body-md">لا توجد بيانات لعرضها.</p>
            </div>
          ) : (
            <div className="glass-card rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-right">
                  <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant">
                    <tr>
                      <th className="px-6 py-4">الكود</th>
                      <th className="px-6 py-4">اسم الحساب</th>
                      <th className="px-6 py-4">النوع</th>
                      <th className="px-6 py-4">مدين</th>
                      <th className="px-6 py-4">دائن</th>
                      <th className="px-6 py-4">الرصيد الصافي</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/30 text-body-md">
                    {trialBalance.map((row, i) => (
                      <tr
                        key={row.account_id ?? `grand-total-${i}`}
                        className={row.is_grand_total ? "bg-surface-container-low font-bold" : "hover:bg-surface-container-lowest transition-colors"}
                      >
                        <td className="px-6 py-4 font-data-mono" dir="ltr">{row.account_code}</td>
                        <td className="px-6 py-4 font-medium">
                          {row.account_name}
                          {row.is_grand_total && (
                            <span className={`mr-2 px-2 py-1 rounded text-[11px] font-bold ${row.is_balanced ? "bg-secondary-container/30 text-secondary" : "bg-error-container/40 text-error"}`}>
                              {row.is_balanced ? "متوازن" : "غير متوازن"}
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-on-surface-variant">
                          {row.is_grand_total ? "—" : (accountTypeLabel[row.account_type as AccountType] ?? row.account_type)}
                        </td>
                        <td className="px-6 py-4 font-data-mono" dir="ltr">{egp(row.total_debit)}</td>
                        <td className="px-6 py-4 font-data-mono" dir="ltr">{egp(row.total_credit)}</td>
                        <td className="px-6 py-4 font-data-mono" dir="ltr">{egp(row.net_balance)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : tab === "periods" ? (
        <div className="space-y-4">
          <p className="text-body-sm text-on-surface-variant">
            قفل/فتح فترة محاسبية متاح فقط لدور <b>OWNER</b>. أي قيد بتاريخ داخل فترة مقفولة هيترفض تلقائيًا (سواء ترحيل آلي من حجز/فاتورة، أو ترحيل يدوي).
          </p>

          <div className="flex items-center gap-3">
            <input
              type="text"
              value={periodFilter}
              onChange={(e) => setPeriodFilter(e.target.value)}
              placeholder="فلترة بالاسم (مثال: 2026-09)"
              dir="ltr"
              className="h-10 rounded-lg border border-outline-variant bg-surface-container-low px-3 text-body-sm text-on-surface outline-none focus:border-primary w-56"
            />
            <button
              onClick={() => { setPeriodsLoaded(false); }}
              disabled={periodsLoading}
              className="flex items-center gap-2 h-10 px-4 rounded-lg bg-primary text-on-primary font-bold text-body-sm hover:opacity-90 transition-opacity disabled:opacity-70"
            >
              {periodsLoading && <Loader2 className="w-4 h-4 animate-spin" />}
              تحديث
            </button>
          </div>

          {periodsError && (
            <div className="flex items-center gap-2 bg-error-container text-on-error-container p-4 rounded-lg text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {periodsError}
            </div>
          )}

          {periodsLoading ? (
            <div className="flex items-center justify-center py-24 text-on-surface-variant gap-2">
              <Loader2 className="w-5 h-5 animate-spin" />
              جاري التحميل...
            </div>
          ) : (
            <div className="glass-card rounded-xl overflow-hidden">
              <div className="overflow-x-auto max-h-[70vh]">
                <table className="w-full text-right">
                  <thead className="bg-surface-container-low text-outline text-body-sm font-bold border-b border-outline-variant sticky top-0">
                    <tr>
                      <th className="px-6 py-4">الفترة</th>
                      <th className="px-6 py-4">من</th>
                      <th className="px-6 py-4">إلى</th>
                      <th className="px-6 py-4">الحالة</th>
                      <th className="px-6 py-4">آخر إقفال</th>
                      <th className="px-6 py-4"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant/30 text-body-md">
                    {periods
                      .filter((p) => !periodFilter || p.name.includes(periodFilter))
                      .map((p) => (
                        <tr key={p.id} className="hover:bg-surface-container-lowest transition-colors">
                          <td className="px-6 py-4 font-data-mono font-semibold" dir="ltr">{p.name}</td>
                          <td className="px-6 py-4 font-data-mono text-on-surface-variant" dir="ltr">{p.start_date.slice(0, 10)}</td>
                          <td className="px-6 py-4 font-data-mono text-on-surface-variant" dir="ltr">{p.end_date.slice(0, 10)}</td>
                          <td className="px-6 py-4">
                            <span className={`px-2 py-1 rounded text-[11px] font-bold flex items-center gap-1 w-fit ${p.status === "CLOSED" ? "bg-error-container/40 text-error" : "bg-secondary-container/30 text-secondary"}`}>
                              {p.status === "CLOSED" ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
                              {p.status === "CLOSED" ? "مقفولة" : "مفتوحة"}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-on-surface-variant text-body-sm" dir="ltr">
                            {p.closed_at ? p.closed_at.slice(0, 10) : "—"}
                          </td>
                          <td className="px-6 py-4">
                            {p.status === "CLOSED" ? (
                              <button
                                onClick={() => reopenPeriod(p.id)}
                                disabled={periodActionId === p.id}
                                className="flex items-center gap-1 bg-secondary text-on-secondary px-3 py-1.5 rounded-lg text-body-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-70"
                              >
                                {periodActionId === p.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Unlock className="w-3.5 h-3.5" />}
                                فتح
                              </button>
                            ) : (
                              <button
                                onClick={() => closePeriod(p.id)}
                                disabled={periodActionId === p.id}
                                className="flex items-center gap-1 bg-error text-on-error px-3 py-1.5 rounded-lg text-body-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-70"
                              >
                                {periodActionId === p.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Lock className="w-3.5 h-3.5" />}
                                قفل
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
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

      {journalModalOpen && (
        <CreateJournalEntryModal
          accounts={accounts}
          onClose={() => setJournalModalOpen(false)}
          onCreated={() => {
            setJournalModalOpen(false);
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

// Bug fix (live-reproduced, 20 Sep 2026): "لا يوجد زر لإنشاء قيد يومية يدوي" —
// the accounting router has always fully supported manual journal entries
// (POST /accounting/journal-entries, balanced-debit/credit validation server
// side via TransactionLineCreateRequest/JournalEntryCreateRequest in
// schemas.py, plus /post and /reverse), but no frontend UI ever called it.
// This modal mirrors that exact request shape: { reference, description,
// lines: [{ account_code, debit, credit, description }] }, with the same
// Σdebit == Σcredit balance rule enforced client-side first (for fast
// feedback) and then re-validated by the backend regardless.
interface JournalLineDraft {
  account_code: string;
  debit: string;
  credit: string;
  description: string;
}

function emptyLine(): JournalLineDraft {
  return { account_code: "", debit: "", credit: "", description: "" };
}

function CreateJournalEntryModal({
  accounts,
  onClose,
  onCreated,
}: {
  accounts: Account[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [reference, setReference] = useState("");
  const [description, setDescription] = useState("");
  const [lines, setLines] = useState<JournalLineDraft[]>([emptyLine(), emptyLine()]);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const totalDebit = lines.reduce((sum, l) => sum + (Number(l.debit) || 0), 0);
  const totalCredit = lines.reduce((sum, l) => sum + (Number(l.credit) || 0), 0);
  const isBalanced = lines.length > 0 && totalDebit > 0 && Math.abs(totalDebit - totalCredit) < 0.0001;

  const updateLine = (index: number, patch: Partial<JournalLineDraft>) => {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  };

  const addLine = () => setLines((prev) => [...prev, emptyLine()]);
  const removeLine = (index: number) => setLines((prev) => (prev.length > 2 ? prev.filter((_, i) => i !== index) : prev));

  const onSubmit = async () => {
    setErrorMsg("");

    if (!reference.trim() || !description.trim()) {
      setErrorMsg("المرجع والوصف مطلوبان.");
      return;
    }
    const activeLines = lines.filter((l) => l.account_code && (Number(l.debit) > 0 || Number(l.credit) > 0));
    if (activeLines.length < 2) {
      setErrorMsg("القيد لازم يحتوي على سطرين على الأقل، كل سطر بحساب ومبلغ.");
      return;
    }
    if (!isBalanced) {
      setErrorMsg(`القيد غير متوازن: مدين ${totalDebit.toFixed(2)} ≠ دائن ${totalCredit.toFixed(2)}.`);
      return;
    }

    setSubmitting(true);
    try {
      await apiClient.post("/accounting/journal-entries", {
        reference: reference.trim(),
        description: description.trim(),
        lines: activeLines.map((l) => ({
          account_code: l.account_code,
          debit: Number(l.debit) || 0,
          credit: Number(l.credit) || 0,
          description: l.description.trim() || undefined,
        })),
      });
      onCreated();
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, "تعذر إنشاء القيد."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-gutter" onClick={onClose}>
      <div
        className="w-full max-w-2xl bg-surface-container-lowest rounded-xl shadow-overlay p-card-padding max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-6">
          <h3 className="font-headline-sm text-headline-sm text-on-surface">قيد يدوي جديد</h3>
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

        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">المرجع</label>
              <input
                value={reference}
                onChange={(e) => setReference(e.target.value)}
                dir="ltr"
                placeholder="مثال: JE-2026-001"
                className="w-full h-11 rounded-lg border border-outline-variant bg-surface-container-low px-4 text-body-md text-on-surface outline-none text-right font-mono focus:border-primary focus:ring-2 focus:ring-primary/30"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-body-sm font-semibold text-on-surface-variant">الوصف</label>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full h-11 rounded-lg border border-outline-variant bg-surface-container-low px-4 text-body-md text-on-surface outline-none text-right focus:border-primary focus:ring-2 focus:ring-primary/30"
              />
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <label className="text-body-sm font-semibold text-on-surface-variant">السطور</label>
              <button
                type="button"
                onClick={addLine}
                className="flex items-center gap-1 text-body-sm font-semibold text-primary hover:opacity-80 transition-opacity"
              >
                <Plus className="w-3.5 h-3.5" />
                إضافة سطر
              </button>
            </div>

            {lines.map((line, i) => (
              <div key={i} className="grid grid-cols-1 sm:grid-cols-[2fr_1fr_1fr_auto] gap-2 items-center">
                <select
                  value={line.account_code}
                  onChange={(e) => updateLine(i, { account_code: e.target.value })}
                  className="h-11 rounded-lg border border-outline-variant bg-surface-container-low px-3 text-body-sm text-on-surface outline-none text-right focus:border-primary focus:ring-2 focus:ring-primary/30"
                >
                  <option value="">اختر حساب...</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.code}>
                      {a.code} — {a.name_ar || a.name}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={line.debit}
                  onChange={(e) => updateLine(i, { debit: e.target.value, credit: e.target.value ? "" : line.credit })}
                  placeholder="مدين"
                  dir="ltr"
                  className="h-11 rounded-lg border border-outline-variant bg-surface-container-low px-3 text-body-sm text-on-surface outline-none font-mono focus:border-primary focus:ring-2 focus:ring-primary/30"
                />
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={line.credit}
                  onChange={(e) => updateLine(i, { credit: e.target.value, debit: e.target.value ? "" : line.debit })}
                  placeholder="دائن"
                  dir="ltr"
                  className="h-11 rounded-lg border border-outline-variant bg-surface-container-low px-3 text-body-sm text-on-surface outline-none font-mono focus:border-primary focus:ring-2 focus:ring-primary/30"
                />
                <button
                  type="button"
                  onClick={() => removeLine(i)}
                  disabled={lines.length <= 2}
                  className="text-on-surface-variant hover:text-error transition-colors disabled:opacity-30 justify-self-center"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}

            <div className={`flex justify-between text-body-sm font-semibold pt-2 ${isBalanced ? "text-secondary" : "text-error"}`}>
              <span>مدين: {totalDebit.toFixed(2)}</span>
              <span>دائن: {totalCredit.toFixed(2)}</span>
              <span>{isBalanced ? "متوازن ✓" : "غير متوازن"}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 h-11 rounded-lg bg-primary text-on-primary font-bold text-body-md hover:opacity-90 transition-opacity disabled:opacity-70 mt-2"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            حفظ القيد
          </button>
        </div>
      </div>
    </div>
  );
}
