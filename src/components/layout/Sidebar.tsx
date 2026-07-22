'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutGrid, 
  Wallet, 
  ListOrdered, 
  ShieldCheck, 
  BarChart3, 
  Settings,
  Shield,
  HeadphonesIcon,
  LogOut,
  Plus,
  Puzzle
} from 'lucide-react';
import { useAppStore } from '@/store/use-app-store';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter
} from "@/components/ui/dialog";

const navItems = [
  { href: '/dashboard', labelAr: 'لوحة القيادة', labelEn: 'Dashboard', icon: LayoutGrid },
  { href: '/financial-core', labelAr: 'الحسابات', labelEn: 'Accounts', icon: Wallet },
  { href: '/transactions', labelAr: 'المعاملات', labelEn: 'Transactions', icon: ListOrdered },
  { href: '/compliance', labelAr: 'الامتثال', labelEn: 'Compliance', icon: ShieldCheck },
  { href: '/reports', labelAr: 'التقارير', labelEn: 'Reports', icon: BarChart3 },
  { href: '/settings', labelAr: 'الإعدادات', labelEn: 'Settings', icon: Settings },
  { href: '/marketplace', labelAr: 'متجر الملحقات', labelEn: 'Marketplace', icon: Puzzle },
];

export function Sidebar() {
  const pathname = usePathname();
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';
  
  const [isQuickAddOpen, setIsQuickAddOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [desc, setDesc] = useState('');

  const handleQuickAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || !desc) return;
    toast.success(isAr ? 'تم حفظ المعاملة بنجاح' : 'Transaction saved successfully');
    setAmount('');
    setDesc('');
    setIsQuickAddOpen(false);
  };

  return (
    <aside className="w-64 bg-sidebar flex-shrink-0 flex flex-col h-full border-e border-sidebar-border overflow-y-auto">
      <div className="p-6 flex flex-col items-center pt-8">
        <div className="w-12 h-12 rounded-lg bg-primary flex items-center justify-center mb-3">
          <Shield className="w-6 h-6 text-sidebar" />
        </div>
        <h1 className="text-sidebar-primary-foreground font-bold text-xl">Trust Core</h1>
        <p className="text-sidebar-subtitle text-xs mt-1 text-center">
          {isAr ? 'نظام إدارة المؤسسات' : 'Enterprise Management System'}
        </p>
      </div>

      <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-md transition-colors relative",
                isActive 
                  ? "bg-primary text-sidebar font-semibold" 
                  : "text-sidebar-text hover:bg-sidebar-accent hover:text-sidebar-primary-foreground"
              )}
            >
              <item.icon className={cn("w-5 h-5 flex-shrink-0", isActive ? "text-sidebar" : "")} />
              <span className="text-sm">
                {isAr ? item.labelAr : item.labelEn}
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 space-y-4">
        <Dialog open={isQuickAddOpen} onOpenChange={setIsQuickAddOpen}>
          <DialogTrigger render={
            <Button className="w-full gap-2 text-sidebar font-bold text-sm h-12 rounded-md hover:bg-accent-hover transition-colors">
              <Plus className="w-5 h-5" />
              {isAr ? 'معاملة جديدة' : 'New Transaction'}
            </Button>
          } />
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
                <Button type="submit" className="w-full font-bold h-11">{isAr ? 'حفظ' : 'Save'}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
        <div className="flex flex-col gap-1 px-2 pb-4">
          <Link href="/support" className="flex items-center gap-3 py-2 text-sidebar-text hover:text-sidebar-primary-foreground transition-colors">
            <HeadphonesIcon className="w-5 h-5" />
            <span className="text-sm font-medium">{isAr ? 'الدعم' : 'Support'}</span>
          </Link>
          <Link href="/login" className="flex items-center gap-3 py-2 text-sidebar-text hover:text-sidebar-primary-foreground transition-colors">
            <LogOut className="w-5 h-5" />
            <span className="text-sm font-medium">{isAr ? 'تسجيل الخروج' : 'Logout'}</span>
          </Link>
        </div>
      </div>
    </aside>
  );
}
