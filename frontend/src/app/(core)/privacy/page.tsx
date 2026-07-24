'use client';

import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { ShieldAlert, Lock, Eye, Database } from 'lucide-react';

export default function PrivacyPage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-12">
      <div className="text-center py-12 bg-card rounded-2xl border border-border shadow-sm">
        <div className="w-16 h-16 bg-primary/10 text-primary flex items-center justify-center rounded-full mx-auto mb-4">
          <ShieldAlert className="w-8 h-8" />
        </div>
        <h1 className="text-3xl font-bold text-foreground mb-3">
          {isAr ? 'سياسة الخصوصية' : 'Privacy Policy'}
        </h1>
        <p className="text-muted-foreground">
          {isAr ? 'نلتزم بحماية بيانات مؤسستك بأعلى المعايير' : 'Committed to protecting your enterprise data with the highest standards'}
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-3 mb-8">
        <Card className="border-border shadow-sm text-center">
          <CardContent className="pt-6">
            <Lock className="w-8 h-8 text-primary mx-auto mb-3" />
            <h3 className="font-bold mb-2">{isAr ? 'تشفير شامل' : 'End-to-End Encryption'}</h3>
            <p className="text-xs text-muted-foreground">{isAr ? 'جميع بياناتك المالية مشفرة باستخدام AES-256' : 'All financial data is encrypted using AES-256'}</p>
          </CardContent>
        </Card>
        <Card className="border-border shadow-sm text-center">
          <CardContent className="pt-6">
            <Database className="w-8 h-8 text-primary mx-auto mb-3" />
            <h3 className="font-bold mb-2">{isAr ? 'الاستضافة المحلية' : 'Local Hosting'}</h3>
            <p className="text-xs text-muted-foreground">{isAr ? 'بياناتك محفوظة في خوادم سحابية محلية آمنة' : 'Your data is stored in secure local cloud servers'}</p>
          </CardContent>
        </Card>
        <Card className="border-border shadow-sm text-center">
          <CardContent className="pt-6">
            <Eye className="w-8 h-8 text-primary mx-auto mb-3" />
            <h3 className="font-bold mb-2">{isAr ? 'الشفافية المطلقة' : 'Absolute Transparency'}</h3>
            <p className="text-xs text-muted-foreground">{isAr ? 'أنت تتحكم كلياً بمن يمكنه الوصول لبياناتك' : 'You have complete control over who accesses your data'}</p>
          </CardContent>
        </Card>
      </div>

      <Card className="border-border shadow-sm">
        <CardContent className="p-8 prose prose-slate dark:prose-invert max-w-none text-foreground">
          <div className="space-y-8">
            <section>
              <h2 className="text-xl font-bold mb-4">{isAr ? 'جمع البيانات' : 'Data Collection'}</h2>
              <p className="text-muted-foreground leading-relaxed">
                {isAr 
                  ? 'يقوم نظام Trust Core بجمع المعلومات الضرورية فقط لتشغيل المنصة وتوفير الخدمات المطلوبة، بما في ذلك بيانات المستخدمين، العمليات المالية، وسجلات الوصول لأغراض الأمان والامتثال.'
                  : 'Trust Core collects only the information necessary to operate the platform and provide requested services, including user data, financial transactions, and access logs for security and compliance purposes.'}
              </p>
            </section>

            <section>
              <h2 className="text-xl font-bold mb-4">{isAr ? 'استخدام البيانات' : 'Data Usage'}</h2>
              <p className="text-muted-foreground leading-relaxed mb-4">
                {isAr 
                  ? 'لا نقوم مطلقاً ببيع أو مشاركة بياناتك أو القوائم المالية الخاصة بك مع أي طرف ثالث لأغراض تسويقية. يتم استخدام البيانات حصرياً لـ:'
                  : 'We never sell or share your data or financial statements with any third party for marketing purposes. Data is used exclusively for:'}
              </p>
              <ul className="list-disc list-inside text-muted-foreground space-y-2 marker:text-primary">
                <li>{isAr ? 'توفير وظائف النظام وإصدار التقارير.' : 'Providing system functionality and report generation.'}</li>
                <li>{isAr ? 'الامتثال للأنظمة والتشريعات المحلية المتعلقة بالفوترة الإلكترونية.' : 'Compliance with local e-invoicing laws and regulations.'}</li>
                <li>{isAr ? 'تحسين أداء النظام عبر تحليلات مجهولة المصدر.' : 'Improving system performance via anonymized analytics.'}</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-bold mb-4">{isAr ? 'الوصول والصلاحيات' : 'Access and Permissions'}</h2>
              <p className="text-muted-foreground leading-relaxed">
                {isAr 
                  ? 'نظام الصلاحيات في المنصة يتيح لمدير النظام (Admin) التحكم الدقيق فيما يمكن لكل موظف الاطلاع عليه. نحن كمزود خدمة لا نمتلك صلاحية الوصول إلى بياناتك المالية التفصيلية دون إذن صريح وموثق لأغراض الدعم الفني فقط.'
                  : 'The role-based access control allows the Admin to precisely manage what each employee can view. As a service provider, we do not have access to your detailed financial data without explicit, documented permission for technical support purposes only.'}
              </p>
            </section>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
