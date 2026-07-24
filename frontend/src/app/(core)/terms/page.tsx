'use client';

import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { FileText, ShieldCheck } from 'lucide-react';

export default function TermsPage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-12">
      <div className="text-center py-12 bg-card rounded-2xl border border-border shadow-sm">
        <div className="w-16 h-16 bg-primary/10 text-primary flex items-center justify-center rounded-full mx-auto mb-4">
          <FileText className="w-8 h-8" />
        </div>
        <h1 className="text-3xl font-bold text-foreground mb-3">
          {isAr ? 'شروط وأحكام الاستخدام' : 'Terms & Conditions of Use'}
        </h1>
        <p className="text-muted-foreground">
          {isAr ? 'آخر تحديث: مايو 2024' : 'Last Updated: May 2024'}
        </p>
      </div>

      <Card className="border-border shadow-sm">
        <CardContent className="p-8 prose prose-slate dark:prose-invert max-w-none text-foreground">
          <div className="space-y-8">
            <section>
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary" />
                {isAr ? '1. قبول الشروط' : '1. Acceptance of Terms'}
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                {isAr 
                  ? 'بوصولك إلى نظام Trust Core ERP واستخدامه، فإنك توافق على الالتزام بهذه الشروط والأحكام. إذا كنت لا توافق على أي جزء من هذه الشروط، فلا يحق لك الوصول إلى النظام أو استخدامه.'
                  : 'By accessing and using the Trust Core ERP system, you agree to be bound by these Terms and Conditions. If you disagree with any part of these terms, you may not access or use the system.'}
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary" />
                {isAr ? '2. ترخيص الاستخدام' : '2. Use License'}
              </h2>
              <p className="text-muted-foreground leading-relaxed mb-4">
                {isAr 
                  ? 'يتم منحك ترخيصاً محدوداً وغير حصري وقابل للإلغاء للوصول إلى النظام واستخدامه لأغراض أعمالك الداخلية فقط. يمنع منعاً باتاً التعديل أو الهندسة العكسية أو استنساخ أي جزء من المنصة.'
                  : 'You are granted a limited, non-exclusive, revocable license to access and use the system solely for your internal business purposes. Modification, reverse engineering, or cloning of any platform part is strictly prohibited.'}
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary" />
                {isAr ? '3. خصوصية البيانات وأمانها' : '3. Data Privacy and Security'}
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                {isAr 
                  ? 'نحن نلتزم بحماية بيانات أعمالك ومعلوماتك المالية بأعلى معايير التشفير المتوافقة مع الأنظمة المحلية. لمزيد من التفاصيل، يرجى مراجعة سياسة الخصوصية الخاصة بنا.'
                  : 'We are committed to protecting your business data and financial information with the highest encryption standards compliant with local regulations. For more details, please review our Privacy Policy.'}
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary" />
                {isAr ? '4. توفر الخدمة والتحديثات' : '4. Service Availability and Updates'}
              </h2>
              <p className="text-muted-foreground leading-relaxed">
                {isAr 
                  ? 'نسعى لضمان توفر النظام بنسبة 99.9%، ومع ذلك، نحتفظ بالحق في إجراء تحديثات أو صيانة دورية قد تتطلب إيقافاً مؤقتاً للخدمة بعد إشعار مسبق.'
                  : 'We strive to ensure 99.9% system availability; however, we reserve the right to perform routine updates or maintenance which may require temporary service interruption following prior notice.'}
              </p>
            </section>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
