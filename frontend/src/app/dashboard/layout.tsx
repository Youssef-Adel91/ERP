"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { SUPPORT_EMAIL } from "@/lib/brand";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useAppStore } from "@/store/use-app-store";
import { apiClient, clearSessionStorage } from "@/lib/api-client";
import {
  LayoutDashboard,
  BookOpenText,
  Wallet,
  Contact,
  Package,
  ShoppingCart,
  Ship,
  Truck,
  Users,
  Workflow,
  BedDouble,
  Car,
  Settings,
  HelpCircle,
  ShieldCheck,
  CheckSquare,
  Receipt,
  ReceiptText,
  CreditCard,
  Store,
  Monitor,
  UserSearch,
  Building2,
  PackageCheck,
  Menu,
  X,
  Plane,
  Megaphone,
  UsersRound,
  Bell,
  Search,
  LogOut,
  AlertTriangle,
  ShieldAlert,
  Sparkles,
  Bot,
  Sun,
  Moon,
  ChevronLeft,
} from "lucide-react";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  /** When set, this item is only shown once we know this plugin key is enabled for the tenant. */
  pluginKey?: string;
}

interface NavSection {
  label: string | null;
  items: NavItem[];
}

interface PluginEntry {
  key: string;
  is_active: boolean;
}

interface ExpirationAlert {
  case_id: string;
  case_title: string | null;
  field_path: string;
  expiry_date: string;
  days_remaining: number;
  severity: "expired" | "critical" | "warning";
}

const navSections: NavSection[] = [
  {
    label: null,
    items: [
      { href: "/dashboard", label: "لوحة القيادة", icon: LayoutDashboard },
      { href: "/dashboard/insights", label: "رؤى الذكاء الاصطناعي", icon: Sparkles },
      { href: "/dashboard/assistant", label: "المساعد الذكي والتقارير", icon: Bot },
    ],
  },
  {
    label: "المالية والعمليات",
    items: [
      { href: "/dashboard/accounting", label: "الحسابات والقيود", icon: BookOpenText },
      { href: "/dashboard/finance", label: "الشيكات", icon: Wallet },
      { href: "/dashboard/eta", label: "الفاتورة الإلكترونية", icon: Receipt },
      { href: "/dashboard/sales", label: "المبيعات", icon: ReceiptText },
      { href: "/dashboard/purchases", label: "المشتريات", icon: ShoppingCart },
      { href: "/dashboard/inventory", label: "المخزون", icon: Package },
      { href: "/dashboard/pos", label: "نقطة البيع (POS)", icon: Monitor },
    ],
  },
  {
    label: "الشركاء والعملاء",
    items: [
      { href: "/dashboard/contacts", label: "جهات الاتصال", icon: Contact },
      { href: "/dashboard/vendors", label: "الموردين والأسعار", icon: Building2 },
      { href: "/dashboard/trust", label: "شبكة الثقة", icon: ShieldCheck },
    ],
  },
  {
    label: "اللوجستيات",
    items: [
      { href: "/dashboard/shipping", label: "الشحن والتوصيل", icon: PackageCheck },
      { href: "/dashboard/settlements", label: "تسويات الشحن", icon: Truck },
      { href: "/dashboard/imports", label: "ملفات الاستيراد", icon: Ship },
    ],
  },
  {
    label: "الموارد البشرية",
    items: [
      { href: "/dashboard/hr", label: "الموارد البشرية", icon: Users },
      { href: "/dashboard/recruitment", label: "الاستقدام والتوظيف", icon: UserSearch, pluginKey: "recruitment" },
      { href: "/dashboard/team", label: "فريق العمل", icon: UsersRound },
    ],
  },
  {
    label: "القطاعات",
    items: [
      { href: "/dashboard/cases", label: "الحالات والحجوزات", icon: Workflow },
      { href: "/dashboard/travel", label: "السياحة والسفر", icon: Plane, pluginKey: "travel" },
      { href: "/dashboard/hospitality", label: "الغرف والضيافة", icon: BedDouble, pluginKey: "hospitality" },
      { href: "/dashboard/rental", label: "أسطول التأجير", icon: Car, pluginKey: "rental" },
    ],
  },
  {
    label: "الإدارة",
    items: [
      { href: "/dashboard/approvals", label: "الموافقات", icon: CheckSquare },
      { href: "/dashboard/billing", label: "الاشتراك والفوترة", icon: CreditCard },
      { href: "/dashboard/marketplace", label: "سوق الإضافات", icon: Store },
      { href: "/dashboard/news", label: "الأخبار", icon: Megaphone },
      { href: "/dashboard/settings", label: "الإعدادات", icon: Settings },
    ],
  },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, clearSession } = useAppStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchValue, setSearchValue] = useState("");
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  // Which verticals (plugins) are enabled for this tenant — drives which
  // "القطاعات"/vertical-specific nav items render. Cached for 5 minutes so
  // the sidebar doesn't refetch on every navigation.
  const { data: plugins } = useQuery({
    queryKey: ["enabled-plugins"],
    queryFn: async () => (await apiClient.get<PluginEntry[]>("/plugins")).data,
    enabled: !!user,
    staleTime: 5 * 60_000,
  });
  const enabledPluginKeys = useMemo(
    () => new Set((plugins ?? []).filter((p) => p.is_active).map((p) => p.key)),
    [plugins]
  );

  // Same expiration-alerts data source the dashboard's ExpirationAlertsWidget
  // uses — reused here in compact form for the notification bell dropdown.
  const { data: alerts, isLoading: alertsLoading } = useQuery({
    queryKey: ["case-expiration-alerts"],
    queryFn: async () =>
      (await apiClient.get<ExpirationAlert[]>("/cases/alerts/expirations", { params: { threshold_days: 60 } })).data,
    enabled: !!user,
    refetchInterval: 5 * 60_000,
  });

  useEffect(() => {
    if (!notifOpen) return;
    const onClickOutside = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [notifOpen]);

  // Header avatar dropdown — same outside-click pattern as the notification
  // bell above, plus Escape-to-close since this one holds a logout action.
  useEffect(() => {
    if (!profileOpen) return;
    const onClickOutside = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setProfileOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [profileOpen]);

  // Until we know which plugins are enabled, hide plugin-gated items rather
  // than briefly flashing everything (or crashing if the request fails).
  const visibleNavSections = useMemo(
    () =>
      navSections
        .map((section) => ({
          ...section,
          items: section.items.filter((item) => !item.pluginKey || enabledPluginKeys.has(item.pluginKey)),
        }))
        .filter((section) => section.items.length > 0),
    [enabledPluginKeys]
  );

  // Light / dark theme toggle — persisted in localStorage, applied via the `dark` class on <html>.
  const [isDark, setIsDark] = useState(false);
  useEffect(() => {
    setIsDark(document.documentElement.classList.contains("dark"));
  }, []);
  const toggleTheme = () => {
    const next = !isDark;
    setIsDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("trustcore-theme", next ? "dark" : "light");
    } catch {}
  };

  // Breadcrumb: current section label / current page label
  const currentCrumb = useMemo(() => {
    for (const section of navSections) {
      for (const item of section.items) {
        const hit = item.href === "/dashboard" ? pathname === item.href : pathname?.startsWith(item.href);
        if (hit) return { section: section.label, page: item.label };
      }
    }
    return { section: null as string | null, page: "لوحة القيادة" };
  }, [pathname]);

  const handleLogout = () => {
    clearSessionStorage();
    clearSession();
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-surface" dir="rtl">
      {/* ── Top Bar ─────────────────────────────────────────────── */}
      <header className="fixed top-0 left-0 right-0 md:right-[272px] z-30 h-[72px] flex flex-row-reverse justify-between items-center px-6 bg-surface-container-lowest border-b border-outline-variant">
        {/* Right: hamburger (mobile) + breadcrumb */}
        <div className="flex items-center gap-3 flex-row-reverse min-w-0">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="فتح القائمة"
            className="p-2 rounded-md hover:bg-surface-container-low transition-colors text-on-surface-variant md:hidden"
          >
            <Menu className="w-5 h-5" />
          </button>
          <nav aria-label="مسار الصفحة" className="flex items-center gap-2 text-body-md min-w-0">
            <span className="text-outline hidden sm:inline">Trust Core</span>
            {currentCrumb.section && (
              <>
                <ChevronLeft className="w-4 h-4 text-outline hidden sm:inline rotate-180" />
                <span className="text-outline hidden sm:inline">{currentCrumb.section}</span>
              </>
            )}
            <ChevronLeft className="w-4 h-4 text-outline rotate-180 hidden sm:inline" />
            <span className="font-semibold text-on-surface truncate">{currentCrumb.page}</span>
          </nav>
        </div>

        {/* Left: search + AI + actions + user */}
        <div className="flex items-center gap-2">
          <div className="relative hidden lg:block">
            <Search className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-outline" />
            <input
              type="text"
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              className="pr-9 pl-12 h-10 bg-surface-container-low border border-transparent rounded-md text-body-md w-72 placeholder:text-outline focus:outline-none focus:bg-surface-container-lowest focus:border-primary"
              placeholder="ابحث عن فاتورة، عميل، منتج..."
            />
            <kbd className="absolute left-2 top-1/2 -translate-y-1/2 text-[10px] font-mono px-1.5 py-0.5 rounded border border-outline-variant bg-surface-container-lowest text-outline" dir="ltr">
              Ctrl K
            </kbd>
          </div>

          <Link
            href="/dashboard/insights"
            className="hidden sm:inline-flex items-center gap-1.5 h-10 px-3 rounded-md bg-primary-fixed text-primary font-semibold text-body-md hover:opacity-90 transition-opacity"
          >
            <Sparkles className="w-4 h-4" />
            اسأل Trust AI
          </Link>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={isDark ? "الوضع الفاتح" : "الوضع الداكن"}
              className="p-2 rounded-md hover:bg-surface-container-low transition-colors text-on-surface-variant"
            >
              {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            </button>

            {/* Notification bell — expiring passports/visas/documents (same query as ExpirationAlertsWidget). */}
            <div className="relative" ref={notifRef}>
              <button
                type="button"
                onClick={() => setNotifOpen((v) => !v)}
                aria-label="التنبيهات"
                aria-expanded={notifOpen}
                className="relative p-2 rounded-md hover:bg-surface-container-low transition-colors text-on-surface-variant"
              >
                <Bell className="w-5 h-5" />
                {!alertsLoading && alerts && alerts.length > 0 && (
                  <span className="absolute top-0.5 left-0.5 min-w-[16px] h-4 px-1 rounded-full bg-error text-on-error text-[10px] font-bold flex items-center justify-center leading-none">
                    {alerts.length > 9 ? "9+" : alerts.length}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute left-0 mt-2 w-80 max-h-96 overflow-y-auto bg-surface-container-lowest border border-outline-variant rounded-lg shadow-overlay z-50 text-right">
                  <div className="flex items-center gap-2 px-4 py-3 border-b border-outline-variant">
                    <ShieldAlert className="w-4 h-4 text-warning" />
                    <h3 className="font-headline-sm text-body-md font-bold text-on-surface">تنبيهات انتهاء الصلاحية</h3>
                  </div>
                  {alertsLoading ? (
                    <p className="px-4 py-6 text-body-sm text-on-surface-variant text-center">جاري التحقق...</p>
                  ) : !alerts || alerts.length === 0 ? (
                    <p className="px-4 py-6 text-body-sm text-on-surface-variant text-center">لا توجد تنبيهات حالياً.</p>
                  ) : (
                    <ul className="divide-y divide-outline-variant/30">
                      {alerts.slice(0, 8).map((a) => (
                        <li key={`${a.case_id}:${a.field_path}`}>
                          <Link
                            href={`/dashboard/cases/${a.case_id}`}
                            onClick={() => setNotifOpen(false)}
                            className="flex items-start gap-2 px-4 py-2.5 hover:bg-surface-container-high transition-colors"
                          >
                            <AlertTriangle
                              className={`w-4 h-4 shrink-0 mt-0.5 ${a.severity === "warning" ? "text-warning" : "text-error"}`}
                            />
                            <div className="min-w-0 flex-1">
                              <p className="text-body-sm font-medium text-on-surface truncate">
                                {a.case_title ?? "بدون عنوان"} — <span className="text-on-surface-variant">{a.field_path}</span>
                              </p>
                              <p className="text-[11px] text-outline font-data-mono" dir="ltr">
                                {a.expiry_date} ·{" "}
                                {a.days_remaining < 0
                                  ? `منتهي منذ ${Math.abs(a.days_remaining)} يوم`
                                  : `متبقي ${a.days_remaining} يوم`}
                              </p>
                            </div>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>

            <a
              href={`mailto:${SUPPORT_EMAIL}?subject=Trust%20Core%20Support`}
              className="p-2 rounded-md hover:bg-surface-container-low transition-colors text-on-surface-variant"
              title="الدعم الفني"
            >
              <HelpCircle className="w-5 h-5" />
            </a>

            {/* Avatar + dropdown menu */}
            <div className="relative mr-1" ref={profileRef}>
              <button
                type="button"
                onClick={() => setProfileOpen((v) => !v)}
                aria-label="قائمة الحساب"
                aria-haspopup="menu"
                aria-expanded={profileOpen}
                className="flex flex-row-reverse items-center gap-2 h-10 pl-2 pr-1 rounded-md hover:bg-surface-container-low transition-colors"
              >
                <span className="h-8 w-8 rounded-full bg-primary-fixed flex items-center justify-center font-bold text-primary text-body-sm overflow-hidden shrink-0">
                  {user?.avatar ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={user.avatar} alt={user?.name ?? ""} className="w-full h-full object-cover" />
                  ) : (
                    user?.name?.[0] ?? "؟"
                  )}
                </span>
                <span className="hidden sm:inline text-body-md font-medium text-on-surface">{user?.name}</span>
              </button>

              {profileOpen && (
                <div
                  role="menu"
                  aria-label="قائمة الحساب"
                  className="absolute left-0 mt-2 w-56 bg-surface-container-lowest border border-outline-variant rounded-lg shadow-overlay z-50 text-right overflow-hidden"
                >
                  {user && (
                    <div className="px-4 py-3 border-b border-outline-variant">
                      <p className="font-body-md text-body-md font-semibold text-on-surface truncate">{user.name}</p>
                      <p className="font-body-sm text-body-sm text-outline truncate">{user.role}</p>
                    </div>
                  )}
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setProfileOpen(false);
                      handleLogout();
                    }}
                    className="flex flex-row-reverse w-full items-center gap-2 px-4 py-2.5 text-error hover:bg-error-container transition-all text-body-md"
                  >
                    <LogOut className="w-4 h-4" />
                    <span>تسجيل الخروج</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* ── Mobile Backdrop ──────────────────────────────────────── */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          aria-hidden="true"
        />
      )}

      {/* ── Sidebar (navy, full height, right) ───────────────────── */}
      <aside
        className={`fixed right-0 top-0 h-screen w-[272px] bg-sidebar text-sidebar-text flex flex-col z-50 text-right transition-transform duration-200 ease-out ${
          sidebarOpen ? "translate-x-0" : "translate-x-full"
        } md:translate-x-0`}
      >
        {/* Logo block */}
        <div className="h-[72px] shrink-0 flex flex-row-reverse items-center justify-between px-5 border-b border-sidebar-border">
          <Link href="/dashboard" className="flex flex-row-reverse items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-primary flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-on-primary" />
            </div>
            <div className="text-right leading-tight">
              <p className="text-[17px] font-bold text-sidebar-on">Trust Core</p>
              <p className="text-[11px] text-sidebar-text">المرجع الرقمي للتاجر المصري</p>
            </div>
          </Link>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            aria-label="إغلاق القائمة"
            className="p-2 rounded-md hover:bg-sidebar-hover text-sidebar-text md:hidden"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Nav items */}
        <nav className="flex-1 overflow-y-auto px-3 py-3">
          {visibleNavSections.map((section, si) => (
            <div key={si} className="mb-3">
              {section.label && (
                <p className="px-3 pt-2 pb-1.5 text-[11px] font-semibold tracking-wide text-sidebar-text/70">
                  {section.label}
                </p>
              )}
              {section.items.map((item) => {
                const active =
                  item.href === "/dashboard" ? pathname === item.href : pathname?.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setSidebarOpen(false)}
                    className={`flex flex-row-reverse items-center gap-3 px-3 h-11 rounded-md transition-colors text-body-md ${
                      active
                        ? "bg-sidebar-active text-sidebar-on font-semibold"
                        : "text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-on"
                    }`}
                  >
                    <item.icon className="w-5 h-5 shrink-0" />
                    <span className="flex-1 text-right">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Bottom: user card */}
        <div className="shrink-0 p-3">
          <div className="flex flex-row-reverse items-center gap-3 p-3 rounded-md bg-sidebar-hover">
            <div className="w-9 h-9 rounded-full bg-primary-fixed overflow-hidden shrink-0 flex items-center justify-center">
              {user?.avatar ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={user.avatar} alt={user.name} className="w-full h-full object-cover" />
              ) : (
                <span className="font-bold text-primary text-body-sm">{user?.name?.[0] ?? "؟"}</span>
              )}
            </div>
            <div className="text-right min-w-0 flex-1">
              <p className="text-body-md font-semibold text-sidebar-on truncate">{user?.name}</p>
              <p className="text-[11px] text-sidebar-text truncate">{user?.role}</p>
            </div>
            <button
              onClick={handleLogout}
              aria-label="تسجيل الخروج"
              title="تسجيل الخروج"
              className="p-1.5 rounded-md text-sidebar-text hover:text-sidebar-on hover:bg-sidebar-active transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main Content ─────────────────────────────────────────── */}
      <main className="md:mr-[272px] mt-[72px] p-6 lg:p-8 min-h-[calc(100vh-72px)]">
        {children}
      </main>
    </div>
  );
}
