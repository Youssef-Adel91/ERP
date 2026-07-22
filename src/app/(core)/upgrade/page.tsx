'use client';

import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Check, Zap, Building2, ShieldCheck, Crown } from 'lucide-react';
import { toast } from 'sonner';

export default function UpgradePage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  const handleSubscribe = (planName: string) => {
    toast.success(isAr ? `تم تقديم طلب ترقية لـ ${planName}. سيتواصل معك المبيعات.` : `Upgrade request for ${planName} submitted. Sales will contact you.`);
  };

  const plans = [
    {
      id: 'pro',
      name: isAr ? 'المحترف' : 'Professional',
      desc: isAr ? 'مثالي للشركات الصغيرة والمتوسطة' : 'Ideal for small and medium businesses',
      price: '399',
      icon: Zap,
      color: 'text-primary',
      bg: 'bg-primary/10',
      border: 'border-border',
      features: [
        isAr ? 'ما يصل إلى 5 مستخدمين' : 'Up to 5 users',
        isAr ? 'الإدارة المالية الأساسية' : 'Basic financial management',
        isAr ? 'دليل جهات الاتصال' : 'Contacts directory',
        isAr ? 'تقارير شهرية' : 'Monthly reports',
        isAr ? 'دعم فني عبر البريد' : 'Email support'
      ]
    },
    {
      id: 'enterprise',
      name: isAr ? 'المؤسسي' : 'Enterprise',
      desc: isAr ? 'للشركات الكبيرة التي تحتاج صلاحيات متقدمة' : 'For large companies needing advanced access',
      price: '999',
      popular: true,
      icon: Building2,
      color: 'text-accent',
      bg: 'bg-accent/10',
      border: 'border-accent shadow-lg shadow-accent/10',
      features: [
        isAr ? 'عدد غير محدود من المستخدمين' : 'Unlimited users',
        isAr ? 'الوصول لجميع الملحقات (Plugins)' : 'Access to all plugins',
        isAr ? 'إدارة الموارد البشرية والمخزون' : 'HR and Inventory management',
        isAr ? 'لوحات قيادة وتقارير مخصصة' : 'Custom dashboards and reports',
        isAr ? 'دعم فني على مدار الساعة' : '24/7 dedicated support'
      ]
    },
    {
      id: 'custom',
      name: isAr ? 'الحل الشامل' : 'Custom Solution',
      desc: isAr ? 'استضافة خاصة وتخصيص كامل للنظام' : 'Private hosting and complete customization',
      price: isAr ? 'مخصص' : 'Custom',
      icon: Crown,
      color: 'text-warning',
      bg: 'bg-warning/10',
      border: 'border-border',
      features: [
        isAr ? 'استضافة على خوادم خاصة' : 'Private server hosting',
        isAr ? 'واجهة بيضاء بشعار شركتك' : 'White-label with your logo',
        isAr ? 'ربط مع أنظمة خارجية (API)' : 'API integrations',
        isAr ? 'مدير حساب مخصص' : 'Dedicated account manager',
        isAr ? 'تدريب موقعي للموظفين' : 'On-site staff training'
      ]
    }
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-12">
      <div className="text-center py-16">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-accent/10 text-accent font-bold text-sm mb-6">
          <ShieldCheck className="w-4 h-4" />
          {isAr ? 'ارتقِ بأعمالك إلى مستوى جديد' : 'Take your business to the next level'}
        </div>
        <h1 className="text-4xl md:text-5xl font-bold text-foreground mb-4 tracking-tight">
          {isAr ? 'اختر الباقة المناسبة لطموحك' : 'Choose the right plan for your ambition'}
        </h1>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          {isAr ? 'نظام متكامل ينمو مع نمو أعمالك. قم بالترقية الآن واستفد من كافة الخصائص المتقدمة التي يوفرها Trust Core.' : 'An integrated system that grows with your business. Upgrade now and leverage all advanced features.'}
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-8 px-4">
        {plans.map((plan) => (
          <Card key={plan.id} className={`relative flex flex-col ${plan.border} transition-transform hover:-translate-y-1 duration-300`}>
            {plan.popular && (
              <div className="absolute -top-4 left-0 right-0 flex justify-center">
                <span className="bg-accent text-accent-foreground text-xs font-bold px-3 py-1 rounded-full shadow-sm">
                  {isAr ? 'الأكثر طلباً' : 'Most Popular'}
                </span>
              </div>
            )}
            <CardContent className="p-8 flex-1 flex flex-col">
              <div className={`w-14 h-14 rounded-2xl ${plan.bg} ${plan.color} flex items-center justify-center mb-6`}>
                <plan.icon className="w-7 h-7" />
              </div>
              <h3 className="text-2xl font-bold mb-2 text-foreground">{plan.name}</h3>
              <p className="text-sm text-muted-foreground mb-6 h-10">{plan.desc}</p>
              
              <div className="mb-8 flex items-baseline gap-1">
                {plan.price !== 'مخصص' && plan.price !== 'Custom' && (
                  <span className="text-lg font-bold text-muted-foreground">EGP</span>
                )}
                <span className="text-4xl font-black font-mono tracking-tighter" dir="ltr">{plan.price}</span>
                {plan.price !== 'مخصص' && plan.price !== 'Custom' && (
                  <span className="text-sm text-muted-foreground font-medium">/{isAr ? 'شهرياً' : 'month'}</span>
                )}
              </div>

              <div className="space-y-4 mb-8 flex-1">
                {plan.features.map((feature, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="w-5 h-5 rounded-full bg-success/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                      <Check className="w-3 h-3 text-success font-bold" />
                    </div>
                    <span className="text-sm font-medium text-foreground">{feature}</span>
                  </div>
                ))}
              </div>

              <Button 
                variant={plan.popular ? 'default' : 'outline'}
                className={`w-full h-12 font-bold text-base ${plan.popular ? 'bg-accent hover:bg-accent-hover text-accent-foreground shadow-md' : 'border-border'}`}
                onClick={() => handleSubscribe(plan.name)}
              >
                {isAr ? 'اشترك الآن' : 'Subscribe Now'}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
