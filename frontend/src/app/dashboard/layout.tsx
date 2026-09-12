"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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

  const handleLogout = () => {
    clearSessionStorage();
    clearSession();
    router.push("/login");
  };

  return (
    <div className="min-h-screen bg-surface" dir="rtl">
      {/* ── Top Nav Bar ─────────────────────────────────────────── */}
      <header className="bg-surface-container-lowest shadow-sm fixed top-0 left-0 right-0 z-50 w-full h-16 flex flex-row-reverse justify-between items-center px-gutter border-b border-outline-variant">
        {/* Right: Logo + Nav links (desktop) */}
        <div className="flex items-center gap-4 flex-row-reverse">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-primary flex items-center justify-center">
              {/* hub icon */}
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-white">
                <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z"/>
              </svg>
            </div>
            <span className="font-headline-md text-headline-md font-bold text-primary hidden sm:inline">
              Nexus ERP
            </span>
          </Link>

          {/* Desktop Nav links */}
          <nav className="hidden md:flex gap-1 mr-4 flex-row-reverse">
            {[
              { href: "/dashboard", label: "الرئيسية" },
              { href: "/dashboard/accounting", label: "العمليات" },
              { href: "/dashboard/contacts", label: "الشركاء" },
            ].map((link) => {
              const active = link.href === "/dashboard" ? pathname === link.href : pathname?.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`px-3 py-1.5 rounded text-body-md font-medium transition-colors duration-200 ${
                    active
                      ? "text-primary font-bold border-b-2 border-primary"
                      : "text-on-surface-variant hover:bg-surface-container-low"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Left: Search + actions + avatar */}
        <div className="flex items-center gap-2">
          {/* Search bar (desktop) */}
          <div className="relative hidden sm:block">
            <Search className="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 text-outline" />
            <input
              type="text"
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              className="pr-9 pl-4 py-1.5 bg-surface-container-low border border-outline-variant rounded-full text-body-md w-56 focus:outline-none focus:ring-2 focus:ring-primary/20"
              placeholder="بحث في النظام..."
            />
          </div>

          <div className="flex items-center gap-1">
            {/* Notification bell — shows expiring passports/visas/documents,
                reusing the same query as ExpirationAlertsWidget on the dashboard. */}
            <div className="relative" ref={notifRef}>
              <button
                type="button"
                onClick={() => setNotifOpen((v) => !v)}
                aria-label="التنبيهات"
                aria-expanded={notifOpen}
                className="relative p-2 rounded-full hover:bg-surface-container-low transition-colors text-on-surface-variant"
              >
                <Bell className="w-5 h-5" />
                {!alertsLoading && alerts && alerts.length > 0 && (
                  <span className="absolute top-1 left-1 min-w-[16px] h-4 px-1 rounded-full bg-error text-white text-[10px] font-bold flex items-center justify-center leading-none">
                    {alerts.length > 9 ? "9+" : alerts.length}
                  </span>
                )}
              </button>

              {notifOpen && (
                <div className="absolute left-0 mt-2 w-80 max-h-96 overflow-y-auto bg-surface-container-lowest border border-outline-variant rounded-xl shadow-overlay z-50 text-right">
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
            <button className="p-2 rounded-full hover:bg-surface-container-low transition-colors text-on-surface-variant">
              <Settings className="w-5 h-5" />
            </button>
            <a
              href="mailto:youssefffadel555@gmail.com?subject=Nexus%20ERP%20Support"
              className="p-2 rounded-full hover:bg-surface-container-low transition-colors text-on-surface-variant"
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
                className="h-8 w-8 rounded-full bg-primary-fixed border border-outline-variant flex items-center justify-center font-bold text-on-primary-fixed text-body-sm overflow-hidden shrink-0"
              >
                {user?.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.avatar} alt={user?.name ?? ""} className="w-full h-full object-cover" />
                ) : (
                  user?.name?.[0] ?? "?"
                )}
              </button>

              {profileOpen && (
                <div
                  role="menu"
                  aria-label="قائمة الحساب"
                  className="absolute left-0 mt-2 w-56 bg-surface-container-lowest border border-outline-variant rounded-xl shadow-overlay z-50 text-right overflow-hidden"
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
                    className="flex flex-row-reverse w-full items-center gap-2 px-4 py-2.5 text-error hover:bg-error-container/20 transition-all text-body-md"
                  >
                    <LogOut className="w-4 h-4" />
                    <span>تسجيل الخروج</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Mobile hamburger */}
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="فتح القائمة"
            className="p-2 rounded-full hover:bg-surface-container-low transition-colors text-on-surface-variant md:hidden"
          >
            <Menu className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* ── Mobile Backdrop ──────────────────────────────────────── */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/40 md:hidden"
          aria-hidden="true"
        />
      )}

      {/* ── Side Nav Bar ─────────────────────────────────────────── */}
      <aside
        className={`fixed right-0 top-16 h-[calc(100vh-64px)] w-64 bg-white border-l border-outline-variant shadow-md flex flex-col z-40 text-right transition-transform duration-200 ease-out ${
          sidebarOpen ? "translate-x-0" : "translate-x-full"
        } md:translate-x-0`}
      >
        {/* Mobile close button */}
        <div className="flex items-center justify-between px-card-padding pt-3 md:hidden">
          <span className="font-headline-sm text-body-md font-bold text-primary">القائمة</span>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            aria-label="إغلاق القائمة"
            className="p-2 rounded-full hover:bg-surface-container-high transition-colors text-on-surface-variant"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Sidebar header block */}
        <div className="px-card-padding pt-4 pb-2 hidden md:block">
          <div className="flex flex-row-reverse items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary-container flex items-center justify-center">
              {/* analytics icon */}
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-white">
                <path d="M280-280h80v-280h-80v280Zm160 0h80v-400h-80v400Zm160 0h80v-160h-80v160ZM200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h560q33 0 56.5 23.5T840-760v560q0 33-23.5 56.5T760-120H200Z"/>
              </svg>
            </div>
            <div>
              <h2 className="font-headline-sm text-headline-sm text-primary font-bold">نظام نكسوس</h2>
              <p className="text-body-sm text-outline">تحليلات الشركات</p>
            </div>
          </div>
        </div>

        {/* Nav items */}
        <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {visibleNavSections.map((section, si) => (
            <div key={si} className="mb-2">
              {section.label && (
                <p className="px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-outline">
                  {section.label}
                </p>
              )}
              {section.items.map((item) => {
                const active =
                  item.href === "/dashboard"
                    ? pathname === item.href
                    : pathname?.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setSidebarOpen(false)}
                    className={`flex flex-row-reverse items-center gap-2 px-3 py-2.5 rounded-lg transition-all duration-100 text-body-md ${
                      active
                        ? "bg-secondary-container/40 text-on-secondary-container border-r-4 border-primary font-semibold"
                        : "text-on-surface-variant hover:bg-surface-container-high active:scale-95"
                    }`}
                  >
                    <item.icon className="w-4.5 h-4.5 shrink-0 w-5 h-5" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Bottom: user info + logout */}
        <div className="border-t border-outline-variant p-card-padding shrink-0">
          {user && (
            <div className="flex flex-row-reverse items-center gap-2 mb-3 px-1">
              <div className="w-8 h-8 rounded-full bg-primary-fixed border border-outline-variant overflow-hidden shrink-0">
                {user.avatar ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.avatar} alt={user.name} className="w-full h-full object-cover" />
                ) : (
                  <span className="w-full h-full flex items-center justify-center font-bold text-on-primary-fixed text-body-sm">
                    {user.name?.[0] ?? "؟"}
                  </span>
                )}
              </div>
              <div className="text-right min-w-0">
                <p className="font-body-md text-body-md font-semibold text-on-surface truncate">{user.name}</p>
                <p className="font-body-sm text-body-sm text-outline truncate">{user.role}</p>
              </div>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="flex flex-row-reverse w-full items-center gap-2 px-3 py-2.5 rounded-lg text-error hover:bg-error-container/20 transition-all text-body-md"
          >
            <LogOut className="w-5 h-5" />
            <span>تسجيل الخروج</span>
          </button>
        </div>
      </aside>

      {/* ── Main Content ─────────────────────────────────────────── */}
      <main className="md:mr-64 mt-16 p-gutter min-h-[calc(100vh-64px)]">
        {children}
      </main>
    </div>
  );
}
