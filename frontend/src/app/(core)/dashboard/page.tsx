'use client';

import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { 
  TrendingUp, 
  Users, 
  Wallet, 
  ArrowUpRight, 
  ArrowDownLeft, 
  Activity,
  CreditCard,
  Building
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useRouter } from 'next/navigation';

export default function DashboardPage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';
  const router = useRouter();

  const metrics = [
    {
      title: isAr ? 'إجمالي الإيرادات' : 'Total Revenue',
      value: 'EGP 1.2M',
      change: '+14%',
      up: true,
      icon: TrendingUp,
      color: 'text-success',
      bg: 'bg-success/20'
    },
    {
      title: isAr ? 'المصروفات' : 'Expenses',
      value: 'EGP 450K',
      change: '-5%',
      up: false,
      icon: ArrowDownLeft,
      color: 'text-warning-foreground',
      bg: 'bg-warning/20'
    },
    {
      title: isAr ? 'الرصيد النقدي' : 'Cash Balance',
      value: 'EGP 750K',
      change: '+2%',
      up: true,
      icon: Wallet,
      color: 'text-primary',
      bg: 'bg-primary/20'
    },
    {
      title: isAr ? 'العملاء النشطين' : 'Active Clients',
      value: '1,240',
      change: '+12%',
      up: true,
      icon: Users,
      color: 'text-sidebar-text',
      bg: 'bg-sidebar-accent'
    }
  ];

  const recentActivities = [
    { id: 1, title: 'سند قبض جديد', titleEn: 'New Receipt Voucher', desc: 'تم تحصيل 45,000 ج.م من شركة الرمال', descEn: 'Collected 45,000 EGP from Al-Rimal Co', time: '10:30 AM', icon: ArrowUpRight, color: 'text-success' },
    { id: 2, title: 'سند صرف', titleEn: 'Payment Voucher', desc: 'سداد فاتورة الكهرباء 4,200 ج.م', descEn: 'Paid electricity bill 4,200 EGP', time: '09:15 AM', icon: ArrowDownLeft, color: 'text-warning-foreground' },
    { id: 3, title: 'عميل جديد', titleEn: 'New Client', desc: 'تمت إضافة مؤسسة القمة', descEn: 'Al-Qimmah Est was added', time: 'أمس', timeEn: 'Yesterday', icon: Building, color: 'text-primary' },
    { id: 4, title: 'تحديث نظام', titleEn: 'System Update', desc: 'اكتمل النسخ الاحتياطي التلقائي', descEn: 'Auto backup completed', time: 'أمس', timeEn: 'Yesterday', icon: Activity, color: 'text-muted-foreground' }
  ];

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground">
            {isAr ? 'لوحة القيادة' : 'Dashboard'}
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            {isAr ? 'مرحباً بك مجدداً! إليك ملخص الأداء لهذا اليوم.' : 'Welcome back! Here is your performance overview for today.'}
          </p>
        </div>
        <div className="flex gap-3">
          <Button 
            className="gap-2 font-bold shadow hover:bg-accent-hover transition-colors"
            onClick={() => router.push('/financial-core')}
          >
            <CreditCard className="w-4 h-4" />
            {isAr ? 'إدارة الشؤون المالية' : 'Manage Financials'}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric, i) => (
          <Card key={i} className="border-border shadow-sm hover:shadow-md transition-shadow">
            <CardContent className="p-6">
              <div className="flex justify-between items-start">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${metric.bg}`}>
                  <metric.icon className={`w-6 h-6 ${metric.color}`} />
                </div>
                <Badge variant="outline" className={`font-mono border-transparent shadow-none text-xs font-bold ${metric.up ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger'}`}>
                  {metric.change}
                </Badge>
              </div>
              <div className="mt-4">
                <p className="text-sm text-muted-foreground mb-1 font-medium">{metric.title}</p>
                <h3 className="text-2xl font-bold font-mono text-foreground" dir="ltr">{metric.value}</h3>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Simple mock chart area */}
        <div className="lg:col-span-2 space-y-6">
          <Card className="border-border shadow-sm">
            <div className="p-5 border-b border-border flex justify-between items-center">
              <h2 className="font-bold text-lg text-foreground">{isAr ? 'التدفقات النقدية (آخر 6 أشهر)' : 'Cash Flows (Last 6 Months)'}</h2>
            </div>
            <CardContent className="p-6">
              <div className="h-64 flex items-end justify-between gap-2 pt-10 relative">
                {/* Horizontal lines */}
                <div className="absolute inset-0 flex flex-col justify-between pt-10 pb-6 opacity-10 pointer-events-none">
                  <div className="border-b border-foreground w-full"></div>
                  <div className="border-b border-foreground w-full"></div>
                  <div className="border-b border-foreground w-full"></div>
                  <div className="border-b border-foreground w-full"></div>
                </div>
                
                {/* Bars */}
                {[45, 60, 30, 80, 55, 90].map((h, i) => (
                  <div key={i} className="w-1/6 flex flex-col items-center gap-2 group relative z-10">
                    <div className="absolute -top-8 bg-foreground text-background text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity">
                      EGP {h}K
                    </div>
                    <div 
                      className="w-full max-w-[40px] bg-primary rounded-t-sm hover:bg-primary/80 transition-colors cursor-pointer"
                      style={{ height: `${h}%` }}
                    ></div>
                    <span className="text-xs text-muted-foreground">{isAr ? `شهر ${i+1}` : `Mon ${i+1}`}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Recent Activity */}
        <div className="space-y-6">
          <Card className="border-border shadow-sm h-full flex flex-col">
            <div className="p-5 border-b border-border flex justify-between items-center">
              <h2 className="font-bold text-lg text-foreground">{isAr ? 'أحدث النشاطات' : 'Recent Activities'}</h2>
              <Button variant="ghost" size="sm" className="text-primary text-xs" onClick={() => router.push('/reports')}>
                {isAr ? 'عرض الكل' : 'View All'}
              </Button>
            </div>
            <CardContent className="p-0 flex-1 overflow-auto">
              <div className="divide-y divide-border">
                {recentActivities.map((activity) => (
                  <div key={activity.id} className="p-4 hover:bg-muted/30 transition-colors flex gap-4">
                    <div className={`w-10 h-10 rounded-full flex-shrink-0 flex items-center justify-center bg-muted ${activity.color}`}>
                      <activity.icon className="w-5 h-5" />
                    </div>
                    <div className="flex-1">
                      <div className="flex justify-between items-start mb-1">
                        <p className="font-bold text-sm text-foreground">{isAr ? activity.title : activity.titleEn}</p>
                        <span className="text-[10px] text-muted-foreground font-mono">{isAr ? activity.time : activity.timeEn}</span>
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                        {isAr ? activity.desc : activity.descEn}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
