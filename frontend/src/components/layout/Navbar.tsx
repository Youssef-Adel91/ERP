'use client';

import { Search, Bell, Settings, Globe, LogOut, CheckCircle2, AlertTriangle, Info } from 'lucide-react';
import { useAppStore } from '@/store/use-app-store';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function Navbar() {
  const router = useRouter();
  const { language, setLanguage, user } = useAppStore();
  const isAr = language === 'ar';

  const toggleLanguage = () => {
    const newLang = language === 'ar' ? 'en' : 'ar';
    setLanguage(newLang);
    document.documentElement.lang = newLang;
    document.documentElement.dir = newLang === 'ar' ? 'rtl' : 'ltr';
  };

  return (
    <header className="h-20 bg-card border-b border-border flex items-center justify-between px-6 flex-shrink-0 shadow-sm">
      <div className="flex items-center gap-6">
        <Link href="/profile" className="flex items-center gap-3 border-e border-border pe-6 hover:bg-muted/50 p-2 rounded-lg transition-colors cursor-pointer">
          <div className="w-10 h-10 rounded-full bg-primary/20 overflow-hidden">
            <img src={user?.avatar || "https://ui-avatars.com/api/?name=User&background=random"} alt="Avatar" className="w-full h-full object-cover" />
          </div>
          <div>
            <p className="text-sm font-bold text-foreground">{user?.name || (isAr ? 'أحمد منصور' : 'Ahmed Mansour')}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{user?.role || (isAr ? 'مدير الحسابات' : 'Account Manager')}</p>
          </div>
        </Link>

        <div className="flex items-center gap-4 text-muted-foreground">
          <button onClick={() => router.push('/settings')} className="hover:text-foreground transition-colors p-1">
            <Settings className="w-5 h-5" />
          </button>
          <DropdownMenu>
            <DropdownMenuTrigger render={
              <button className="relative hover:text-foreground transition-colors p-1">
                <Bell className="w-5 h-5" />
                <span className="absolute top-1 end-1 w-2 h-2 bg-destructive rounded-full border border-card"></span>
              </button>
            } />
            <DropdownMenuContent align="end" className="w-80 p-0 shadow-xl border-border bg-card">
              <div className="flex items-center justify-between p-4 border-b border-border">
                <h3 className="font-bold text-sm">{isAr ? 'الإشعارات' : 'Notifications'}</h3>
                <span className="text-xs text-primary font-bold hover:underline cursor-pointer">
                  {isAr ? 'تحديد الكل كمقروء' : 'Mark all read'}
                </span>
              </div>
              <div className="max-h-80 overflow-auto flex flex-col">
                <div className="p-4 flex gap-3 hover:bg-muted/50 transition-colors border-b border-border/50 cursor-pointer">
                  <div className="w-8 h-8 rounded-full bg-success/10 text-success flex items-center justify-center flex-shrink-0 mt-0.5">
                    <CheckCircle2 className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-foreground mb-1">{isAr ? 'تم استلام الدفعة بنجاح' : 'Payment received successfully'}</p>
                    <p className="text-xs text-muted-foreground mb-1">{isAr ? 'تم استلام دفعة بقيمة 45,000 ج.م من مؤسسة الرمال' : 'Received a payment of 45,000 EGP from Al Rimal'}</p>
                    <span className="text-[10px] text-muted-foreground font-mono">10:30 AM</span>
                  </div>
                </div>
                <div className="p-4 flex gap-3 hover:bg-muted/50 transition-colors border-b border-border/50 cursor-pointer">
                  <div className="w-8 h-8 rounded-full bg-warning/10 text-warning-foreground flex items-center justify-center flex-shrink-0 mt-0.5">
                    <AlertTriangle className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-foreground mb-1">{isAr ? 'فاتورة مستحقة الدفع' : 'Invoice due for payment'}</p>
                    <p className="text-xs text-muted-foreground mb-1">{isAr ? 'فاتورة الكهرباء لشهر مايو تستحق الدفع اليوم' : 'May electricity invoice is due today'}</p>
                    <span className="text-[10px] text-muted-foreground font-mono">09:00 AM</span>
                  </div>
                </div>
                <div className="p-4 flex gap-3 hover:bg-muted/50 transition-colors cursor-pointer">
                  <div className="w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center flex-shrink-0 mt-0.5">
                    <Info className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-foreground mb-1">{isAr ? 'تحديث النظام' : 'System update'}</p>
                    <p className="text-xs text-muted-foreground mb-1">{isAr ? 'تم إطلاق الإصدار 2.1 بنجاح، اكتشف المزايا الجديدة' : 'Version 2.1 released successfully, discover new features'}</p>
                    <span className="text-[10px] text-muted-foreground font-mono">{isAr ? 'أمس' : 'Yesterday'}</span>
                  </div>
                </div>
              </div>
              <div className="p-2 border-t border-border text-center">
                <button className="text-xs font-bold text-muted-foreground hover:text-foreground w-full py-2 transition-colors">
                  {isAr ? 'عرض كل الإشعارات' : 'View all notifications'}
                </button>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>
          <button onClick={toggleLanguage} className="hover:text-foreground transition-colors p-1">
            <Globe className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="flex items-center">
        <div className="relative w-80">
          <div className="absolute inset-y-0 end-0 flex items-center pe-4 pointer-events-none">
            <Search className="w-4 h-4 text-muted-foreground" />
          </div>
          <input 
            type="text" 
            className="w-full h-10 bg-muted/50 border border-border rounded-full text-sm pe-10 ps-4 focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all placeholder:text-muted-foreground"
            placeholder={isAr ? 'بحث...' : 'Search...'} 
          />
        </div>
      </div>
    </header>
  );
}
