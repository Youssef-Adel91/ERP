'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutGrid,
  Wallet,
  Users,
  ListOrdered,
  ShieldCheck,
  BarChart3,
  Settings,
  Shield,
  HeadphonesIcon,
  LogOut,
  Plus,
  Puzzle,
  Package,
  Truck,
  ShoppingCart,
  Globe,
  Landmark,
  Megaphone,
  LucideIcon,
} from 'lucide-react';
import { useAppStore } from '@/store/use-app-store';
import { cn } from '@/lib/utils';
import { Button, buttonVariants } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { clearSession } from '@/lib/api-client';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog';

// ── Icon registry maps plugin slug → Lucide component ────────────────────────
const ICON_MAP: Record<string, LucideIcon> = {
  LayoutGrid,
  Wallet,
  Users,
  ListOrdered,
  ShieldCheck,
  BarChart3,
  Settings,
  Package,
  Truck,
  ShoppingCart,
  Globe,
  Landmark,
  Puzzle,
  Megaphone,
};

// ── Navigation item definition ────────────────────────────────────────────────

interface NavItem {
  href: string;
  labelAr: string;
  labelEn: string;
  iconKey: string;
  /** Plugin slug required to see this item. undefined = always visible. */
  requiredPlugin?: string;
  /** Sub-group label shown as a section header above this item. */
  group?: string;
  /** Roles allowed to see this item. OWNER is always allowed. */
  allowedRoles?: string[];
}

// ── Master navigation manifest ─────────────────────────────────────────────────
// Every possible nav item lives here. `requiredPlugin` controls visibility.
const ALL_NAV_ITEMS: NavItem[] = [
  // Universal — always shown
  { href: '/dashboard',      labelAr: 'لوحة القيادة',        labelEn: 'Dashboard',      iconKey: 'LayoutGrid' },
  { href: '/reports',        labelAr: 'التقارير',             labelEn: 'Reports',        iconKey: 'BarChart3' },

  // Universal Core
  { href: '/news',           labelAr: 'الأخبار',              labelEn: 'News',           iconKey: 'Megaphone',      group: 'Universal Core' },
  { href: '/financial-core', labelAr: 'الحسابات',            labelEn: 'Accounting',     iconKey: 'Wallet',        requiredPlugin: 'accounting', allowedRoles: ['ACCOUNTING'] },
  { href: '/transactions',   labelAr: 'المعاملات',           labelEn: 'Transactions',   iconKey: 'ListOrdered',   requiredPlugin: 'accounting', allowedRoles: ['ACCOUNTING'] },
  { href: '/compliance',     labelAr: 'الامتثال',            labelEn: 'Compliance',     iconKey: 'ShieldCheck',   requiredPlugin: 'accounting', allowedRoles: ['ACCOUNTING'] },
  { href: '/contacts',       labelAr: 'جهات الاتصال',        labelEn: 'Contacts',       iconKey: 'Users',         requiredPlugin: 'contacts', allowedRoles: ['SALES', 'ACCOUNTING'] },

  // Plugins
  { href: '/inventory',      labelAr: 'المخزن',              labelEn: 'Inventory',      iconKey: 'Package',       requiredPlugin: 'inventory',  group: 'Plugins', allowedRoles: ['WAREHOUSE'] },
  { href: '/shipping',       labelAr: 'الشحن والتوصيل',     labelEn: 'Shipping',       iconKey: 'Truck',         requiredPlugin: 'shipping', allowedRoles: ['WAREHOUSE'] },
  { href: '/pos',            labelAr: 'نقطة البيع',          labelEn: 'Point of Sale',  iconKey: 'ShoppingCart',  requiredPlugin: 'pos', allowedRoles: ['SALES'] },
  { href: '/ecommerce',      labelAr: 'التجارة الإلكترونية', labelEn: 'E-Commerce',    iconKey: 'Globe',         requiredPlugin: 'ecommerce', allowedRoles: ['SALES'] },
  { href: '/assets',         labelAr: 'الأصول الثابتة',     labelEn: 'Fixed Assets',   iconKey: 'Landmark',      requiredPlugin: 'assets', allowedRoles: ['ACCOUNTING'] },

  // Always shown at the bottom (restricted to OWNER)
  { href: '/settings',       labelAr: 'الإعدادات',          labelEn: 'Settings',       iconKey: 'Settings', allowedRoles: [] },
  { href: '/marketplace',    labelAr: 'متجر الملحقات',      labelEn: 'Marketplace',    iconKey: 'Puzzle', allowedRoles: [] },
];

// ── Component ─────────────────────────────────────────────────────────────────

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  const language = useAppStore((s) => s.language);
  const activePlugins = useAppStore((s) => s.activePlugins);
  const fetchActivePlugins = useAppStore((s) => s.fetchActivePlugins);
  const setUser = useAppStore((s) => s.setUser);

  const isAr = language === 'ar';
  const [isQuickAddOpen, setIsQuickAddOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [desc, setDesc] = useState('');

  // Hydrate active plugins from API on first render
  useEffect(() => {
    fetchActivePlugins();
  }, [fetchActivePlugins]);

  // Compute the set of active plugin slugs for O(1) lookups
  const activePluginIds = new Set(activePlugins.map((p) => p.id));

  const userRole = useAppStore((s) => s.user?.role) || 'OWNER';

  // Filter the master manifest down to what this tenant can see and what this user's role permits
  const visibleNavItems = ALL_NAV_ITEMS.filter((item) => {
    // 1. Check plugin access
    if (item.requiredPlugin && !activePluginIds.has(item.requiredPlugin)) {
      return false;
    }
    
    // 2. Check role access (OWNER always sees everything except when we explicitly want to hide something, but OWNER implies full access)
    if (userRole !== 'OWNER') {
      if (item.allowedRoles && !item.allowedRoles.includes(userRole)) {
        return false;
      }
    }
    
    return true;
  });

  // Inject group headers between sections
  type RenderItem = { type: 'link'; item: NavItem } | { type: 'header'; label: string };
  const renderList: RenderItem[] = [];
  let lastGroup: string | undefined;
  for (const item of visibleNavItems) {
    if (item.group && item.group !== lastGroup) {
      renderList.push({ type: 'header', label: item.group });
      lastGroup = item.group;
    }
    renderList.push({ type: 'link', item });
  }

  const handleQuickAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || !desc) return;
    toast.success(isAr ? 'تم حفظ المعاملة بنجاح' : 'Transaction saved successfully');
    setAmount('');
    setDesc('');
    setIsQuickAddOpen(false);
  };

  const handleLogout = () => {
    clearSession();
    setUser(null);
    router.push('/login');
  };

  return (
    <aside className="w-64 bg-sidebar flex-shrink-0 flex flex-col h-full border-e border-sidebar-border overflow-y-auto">
      {/* Brand */}
      <div className="p-6 flex flex-col items-center pt-8">
        <div className="w-12 h-12 rounded-lg bg-primary flex items-center justify-center mb-3">
          <Shield className="w-6 h-6 text-sidebar" />
        </div>
        <h1 className="text-sidebar-primary-foreground font-bold text-xl">Omni ERP</h1>
        <p className="text-sidebar-subtitle text-xs mt-1 text-center">
          {isAr ? 'المرجع الرقمي للتاجر المصري' : 'The Egyptian Merchant Platform'}
        </p>
      </div>

      {/* Dynamic navigation */}
      <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5">
        {renderList.map((entry, i) => {
          if (entry.type === 'header') {
            return (
              <p
                key={`header-${i}`}
                className="px-4 pt-4 pb-1 text-[10px] font-bold uppercase tracking-widest text-sidebar-subtitle opacity-60 select-none"
              >
                {isAr ? entry.label : entry.label}
              </p>
            );
          }

          const { item } = entry;
          const isActive = pathname.startsWith(item.href);
          const Icon = ICON_MAP[item.iconKey] ?? LayoutGrid;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex items-center gap-3 px-4 py-2.5 rounded-md transition-colors relative',
                isActive
                  ? 'bg-primary text-sidebar font-semibold'
                  : 'text-sidebar-text hover:bg-sidebar-accent hover:text-sidebar-primary-foreground'
              )}
            >
              <Icon className={cn('w-4 h-4 flex-shrink-0', isActive ? 'text-sidebar' : '')} />
              <span className="text-sm">{isAr ? item.labelAr : item.labelEn}</span>
              {item.requiredPlugin && !isActive && (
                <span className="ml-auto w-1.5 h-1.5 rounded-full bg-primary opacity-60" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Bottom actions */}
      <div className="p-4 space-y-4">
        <Dialog open={isQuickAddOpen} onOpenChange={setIsQuickAddOpen}>
          <DialogTrigger className={cn(buttonVariants({ variant: 'default' }), "w-full gap-2 text-sidebar font-bold text-sm h-12 rounded-md hover:bg-accent-hover transition-colors")}>
            <Plus className="w-5 h-5" />
            {isAr ? 'معاملة جديدة' : 'New Transaction'}
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{isAr ? 'إضافة معاملة سريعة' : 'Add Quick Transaction'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleQuickAdd} className="space-y-4 pt-4 text-foreground">
              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'المبلغ (EGP)' : 'Amount (EGP)'}</label>
                <Input
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0.00"
                  dir="ltr"
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'البيان' : 'Description'}</label>
                <Input
                  value={desc}
                  onChange={(e) => setDesc(e.target.value)}
                  placeholder={isAr ? 'وصف المعاملة' : 'Transaction description'}
                  required
                />
              </div>
              <DialogFooter>
                <Button type="submit" className="w-full font-bold h-11">
                  {isAr ? 'حفظ' : 'Save'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        <div className="flex flex-col gap-1 px-2 pb-4">
          <Link
            href="/support"
            className="flex items-center gap-3 py-2 text-sidebar-text hover:text-sidebar-primary-foreground transition-colors"
          >
            <HeadphonesIcon className="w-5 h-5" />
            <span className="text-sm font-medium">{isAr ? 'الدعم' : 'Support'}</span>
          </Link>
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 py-2 text-sidebar-text hover:text-sidebar-primary-foreground transition-colors w-full text-left"
          >
            <LogOut className="w-5 h-5" />
            <span className="text-sm font-medium">{isAr ? 'تسجيل الخروج' : 'Logout'}</span>
          </button>
        </div>
      </div>
    </aside>
  );
}
