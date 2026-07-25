'use client';

import { useAppStore } from '@/store/use-app-store';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { toast } from 'sonner';
import { Shield, ShieldCheck, AlertTriangle, FileText, CheckCircle2, MoreVertical, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export default function CompliancePage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  const requirements = [
    { id: 1, name: 'نظام الفوترة الإلكترونية (ZATCA)', category: 'الضرائب', updated: '2024/05/12', status: 'compliant' },
    { id: 2, name: 'تشفير البيانات الشخصية (GDPR)', category: 'الخصوصية', updated: '2024/05/10', status: 'review' },
    { id: 3, name: 'سجل المعاملات النقدية الكبيرة', category: 'الرقابة المالية', updated: '2024/05/01', status: 'compliant' },
    { id: 4, name: 'تحديث بيانات السجل التجاري', category: 'قانوني', updated: '2024/04/20', status: 'non-compliant' },
  ];

  const activities = [
    { id: 1, action: 'تم تحديث السجل الضريبي', by: 'أحمد منصور', time: 'منذ ساعتين', details: 'تمت مطابقة 1,240 فاتورة مع متطلبات المرحلة الثانية من الربط الإلكتروني.', color: 'text-primary', bg: 'bg-primary' },
    { id: 2, action: 'بدء تدقيق داخلي مجدول', by: 'نظام آلي', time: 'منذ 5 ساعات', color: 'text-foreground', bg: 'bg-foreground' },
    { id: 3, action: 'تعديل صلاحيات الوصول', by: 'النظام', time: 'أمس، 04:30 م', color: 'text-muted-foreground', bg: 'bg-muted-foreground' },
    { id: 4, action: 'محاولة وصول فاشلة', by: 'IP: 192.168.1.45', time: '11:20 أمس، ص', color: 'text-danger', bg: 'bg-danger' },
  ];

  const [isPoliciesOpen, setIsPoliciesOpen] = useState(false);
  const [isLogOpen, setIsLogOpen] = useState(false);
  const [selectedReq, setSelectedReq] = useState<typeof requirements[0] | null>(null);

  const handleDownloadCert = () => {
    // Simulate PDF download
    const link = document.createElement("a");
    link.href = "data:application/pdf;base64,JVBERi0xLjQKJ...";
    link.download = "Compliance_Certificate.pdf";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success(isAr ? 'تم تحميل الشهادة بنجاح' : 'Certificate downloaded successfully');
  };

  return (
    <div className="space-y-6">
      
      {/* Top Banner */}
      <div className="bg-sidebar rounded-xl p-8 relative overflow-hidden shadow-md">
        {/* Large watermark shield */}
        <Shield className="absolute -end-12 -top-12 w-64 h-64 text-primary/10 rotate-12" />
        
        <div className="relative z-10 flex flex-col md:flex-row gap-8 justify-between items-start md:items-center">
          <div className="max-w-2xl">
            <h1 className="text-2xl font-bold text-white mb-2">
              {isAr ? 'تأمين الوصول وحماية البيانات' : 'Access Security & Data Protection'}
            </h1>
            <p className="text-sidebar-subtitle leading-relaxed text-sm">
              {isAr 
                ? 'نظام الامتثال النشط يراقب حالياً كافة المعاملات المالية لضمان التوافق مع المعايير الضريبية والقانونية. تم تحديث البروتوكولات الأمنية لضمان أقصى درجات حماية البيانات والخصوصية.' 
                : 'The active compliance system is currently monitoring all financial transactions to ensure compliance with tax and legal standards. Security protocols updated.'}
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <Dialog open={isPoliciesOpen} onOpenChange={setIsPoliciesOpen}>
              <DialogTrigger render={
                <Button variant="outline" className="border-sidebar-text text-white hover:bg-sidebar-accent hover:text-white bg-transparent h-11 font-bold">
                  {isAr ? 'مراجعة السياسات' : 'Review Policies'}
                </Button>
              } />
              <DialogContent className="max-w-3xl">
                <DialogHeader>
                  <DialogTitle>{isAr ? 'سياسات الأمان والامتثال التنظيمي' : 'Security & Compliance Policies'}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-4 max-h-96 overflow-y-auto prose dark:prose-invert">
                  <h3 className="font-bold text-foreground">{isAr ? 'بروتوكول التعامل مع البيانات الضريبية' : 'Tax Data Handling Protocol'}</h3>
                  <p className="text-muted-foreground">{isAr ? 'يتم الاحتفاظ بجميع الفواتير الإلكترونية لمدة 5 سنوات كحد أدنى.' : 'All e-invoices are kept for a minimum of 5 years.'}</p>
                  <h3 className="font-bold text-foreground mt-4">{isAr ? 'ضوابط الوصول للمنصة' : 'Platform Access Controls'}</h3>
                  <p className="text-muted-foreground">{isAr ? 'المصادقة الثنائية إلزامية لجميع المستخدمين بصلاحية التعديل.' : '2FA is mandatory for all users with write access.'}</p>
                </div>
              </DialogContent>
            </Dialog>

            <Button className="h-11 font-bold gap-2 shadow-lg" onClick={handleDownloadCert}>
              <ShieldCheck className="w-5 h-5" />
              {isAr ? 'تحميل شهادة الامتثال' : 'Download Compliance Certificate'}
            </Button>
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="border-border shadow-sm relative overflow-hidden">
          <CardContent className="p-6">
            <div className="flex justify-between items-start mb-4">
              <p className="text-sm font-medium text-foreground">{isAr ? 'مؤشر الامتثال العام' : 'Overall Compliance Index'}</p>
              <FileText className="w-5 h-5 text-muted-foreground" />
            </div>
            <div className="flex items-end gap-3">
              <h3 className="text-4xl font-bold text-foreground font-mono" dir="ltr">98.2%</h3>
              <Badge className="bg-success/20 text-success hover:bg-success/20 border-transparent mb-1 rounded-sm">+2.4%</Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-2">{isAr ? 'درجة الأمان' : 'Security Score'}</p>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm">
          <CardContent className="p-6">
            <div className="flex justify-between items-start mb-4">
              <p className="text-sm font-medium text-foreground">{isAr ? 'عمليات التدقيق النشطة' : 'Active Audits'}</p>
              <CheckCircle2 className="w-5 h-5 text-primary" />
            </div>
            <h3 className="text-4xl font-bold text-foreground font-mono" dir="ltr">12</h3>
            <p className="text-sm font-medium text-muted-foreground mt-2">{isAr ? 'سجل قيد المراجعة' : 'Under review log'}</p>
            <p className="text-xs text-muted-foreground mt-1">{isAr ? 'آخر تدقيق شامل قبل 3 أيام' : 'Last full audit 3 days ago'}</p>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm border-t-4 border-t-danger">
          <CardContent className="p-6">
            <div className="flex justify-between items-start mb-4">
              <p className="text-sm font-medium text-foreground">{isAr ? 'مستوى المخاطر' : 'Risk Level'}</p>
              <ShieldAlert className="w-5 h-5 text-danger" />
            </div>
            <h3 className="text-4xl font-bold text-foreground">{isAr ? 'منخفض' : 'Low'}</h3>
            <p className="text-xs text-muted-foreground mt-3">{isAr ? 'لا توجد ثغرات أمنية مكتشفة' : 'No discovered security vulnerabilities'}</p>
          </CardContent>
        </Card>
      </div>

      {/* Split Layout */}
      <div className="flex flex-col lg:flex-row gap-6">
        
        {/* Right side (Main content in RTL) */}
        <div className="flex-1 lg:order-1 order-2">
          <Card className="border-border shadow-sm h-full">
            <div className="p-6 border-b border-border/50">
              <h2 className="text-lg font-bold text-foreground">{isAr ? 'متطلبات الامتثال التنظيمي' : 'Regulatory Compliance Requirements'}</h2>
            </div>
            <div className="p-0">
              <table className="w-full text-start">
                <thead className="bg-muted/30">
                  <tr className="border-b border-border/50">
                    <th className="p-4 text-start text-sm font-bold text-muted-foreground w-1/2">{isAr ? 'المتطلب التنظيمي' : 'Regulatory Requirement'}</th>
                    <th className="p-4 text-start text-sm font-bold text-muted-foreground">{isAr ? 'الفئة' : 'Category'}</th>
                    <th className="p-4 text-start text-sm font-bold text-muted-foreground">{isAr ? 'آخر تحديث' : 'Last Updated'}</th>
                    <th className="p-4 text-start text-sm font-bold text-muted-foreground text-center">{isAr ? 'الحالة' : 'Status'}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {requirements.map((req) => (
                    <tr key={req.id} className="hover:bg-muted/30 transition-colors">
                      <td className="p-4 text-sm font-bold text-foreground">{req.name}</td>
                      <td className="p-4 text-sm text-muted-foreground">{req.category}</td>
                      <td className="p-4 text-sm text-muted-foreground font-mono" dir="ltr">{req.updated}</td>
                      <td className="p-4 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <Badge className={
                            req.status === 'compliant' ? 'bg-success/20 text-success hover:bg-success/20 shadow-none border-transparent font-bold rounded-full' :
                            req.status === 'review' ? 'bg-warning/20 text-warning-foreground hover:bg-warning/20 shadow-none border-transparent font-bold rounded-full' :
                            'bg-danger/10 text-danger hover:bg-danger/10 shadow-none border-transparent font-bold rounded-full'
                          }>
                            {req.status === 'compliant' ? (isAr ? 'متوافق' : 'Compliant') : 
                             req.status === 'review' ? (isAr ? 'قيد المراجعة' : 'Under Review') : 
                             (isAr ? 'غير متوافق' : 'Non-compliant')}
                          </Badge>
                          <Dialog>
                            <DialogTrigger render={
                              <button className="text-muted-foreground hover:text-foreground" onClick={() => setSelectedReq(req)}>
                                <MoreVertical className="w-4 h-4" />
                              </button>
                            } />
                            <DialogContent>
                              <DialogHeader>
                                <DialogTitle>{isAr ? 'تفاصيل المتطلب' : 'Requirement Details'}</DialogTitle>
                              </DialogHeader>
                              {selectedReq && (
                                <div className="space-y-4 pt-4">
                                  <div className="space-y-1">
                                    <span className="text-sm font-bold block">{isAr ? 'اسم المتطلب' : 'Requirement Name'}</span>
                                    <span className="text-muted-foreground">{selectedReq.name}</span>
                                  </div>
                                  <div className="space-y-1">
                                    <span className="text-sm font-bold block">{isAr ? 'الفئة' : 'Category'}</span>
                                    <span className="text-muted-foreground">{selectedReq.category}</span>
                                  </div>
                                  <div className="p-4 bg-muted/30 rounded-lg">
                                    <p className="text-sm text-foreground">
                                      {isAr 
                                        ? 'هذا المتطلب قيد المراقبة المستمرة. يرجى التأكد من استكمال كافة الوثائق المطلوبة عبر شاشة الإعدادات.' 
                                        : 'This requirement is continuously monitored. Ensure all required docs are submitted via Settings.'}
                                    </p>
                                  </div>
                                </div>
                              )}
                            </DialogContent>
                          </Dialog>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {/* Left side (Timeline in RTL) */}
        <div className="w-full lg:w-[350px] lg:order-2 order-1 flex-shrink-0">
          <Card className="border-border shadow-sm h-full">
            <div className="p-6 border-b border-border/50">
              <h2 className="text-lg font-bold text-foreground">{isAr ? 'سجل النشاط الأخير' : 'Recent Activity Log'}</h2>
            </div>
            <div className="p-6">
              <div className="relative border-s-2 border-muted/50 ms-3 space-y-8">
                {activities.map((activity, index) => (
                  <div key={activity.id} className="relative ps-6">
                    <div className={`absolute -start-[9px] top-1.5 w-4 h-4 rounded-full border-4 border-card ${activity.bg}`}></div>
                    <div className="space-y-1">
                      <h3 className="font-bold text-foreground text-sm">{activity.action}</h3>
                      <p className="text-xs text-muted-foreground">
                        {isAr ? 'بواسطة:' : 'By:'} {activity.by} • {activity.time}
                      </p>
                      {activity.details && (
                        <div className="mt-2 p-3 bg-muted/30 rounded-md text-xs text-muted-foreground leading-relaxed">
                          {activity.details}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <Dialog open={isLogOpen} onOpenChange={setIsLogOpen}>
                <DialogTrigger render={
                  <Button variant="outline" className="w-full mt-8 font-bold border-foreground text-foreground hover:bg-muted transition-colors">
                    {isAr ? 'عرض السجل الكامل' : 'View Full Log'}
                  </Button>
                } />
                <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>{isAr ? 'سجل نشاط الامتثال' : 'Compliance Activity Log'}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-6 pt-4 relative border-s-2 border-muted/50 ms-3">
                    {activities.map((activity) => (
                      <div key={`full-${activity.id}`} className="relative ps-6">
                        <div className={`absolute -start-[9px] top-1.5 w-4 h-4 rounded-full border-4 border-card ${activity.bg}`}></div>
                        <div className="space-y-1">
                          <h3 className="font-bold text-foreground text-sm">{activity.action}</h3>
                          <p className="text-xs text-muted-foreground">
                            {isAr ? 'بواسطة:' : 'By:'} {activity.by} • {activity.time}
                          </p>
                        </div>
                      </div>
                    ))}
                    {[5,6,7].map((id) => (
                      <div key={`full-${id}`} className="relative ps-6 opacity-50">
                        <div className={`absolute -start-[9px] top-1.5 w-4 h-4 rounded-full border-4 border-card bg-muted-foreground`}></div>
                        <div className="space-y-1">
                          <h3 className="font-bold text-foreground text-sm">{isAr ? 'أرشفة نظام سابقة' : 'Previous system archive'}</h3>
                          <p className="text-xs text-muted-foreground">
                            {isAr ? 'بواسطة:' : 'By:'} {isAr ? 'النظام' : 'System'} • {isAr ? 'الأسبوع الماضي' : 'Last Week'}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </DialogContent>
              </Dialog>
            </div>
          </Card>
        </div>

      </div>
    </div>
  );
}
