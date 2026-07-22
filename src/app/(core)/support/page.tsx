'use client';

import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { 
  LifeBuoy, 
  MessageSquare, 
  PhoneCall, 
  Mail, 
  HelpCircle,
  FileText,
  Search,
  ChevronDown
} from 'lucide-react';
import { useState } from 'react';

export default function SupportPage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [ticketSubject, setTicketSubject] = useState('');
  const [ticketMessage, setTicketMessage] = useState('');

  const faqs = [
    {
      q: isAr ? 'كيف يمكنني إضافة مستخدم جديد للنظام؟' : 'How do I add a new user to the system?',
      a: isAr ? 'يمكنك إضافة مستخدم جديد من خلال الانتقال إلى شاشة "الإعدادات" ثم النقر على زر "إضافة مستخدم" في قسم المستخدمين والصلاحيات.' : 'You can add a new user by navigating to the "Settings" screen and clicking the "Add User" button in the Users and Roles section.'
    },
    {
      q: isAr ? 'هل يمكنني تغيير اللغة الافتراضية؟' : 'Can I change the default language?',
      a: isAr ? 'نعم، يمكنك التبديل بين اللغتين العربية والإنجليزية في أي وقت عبر القائمة العلوية بجوار ملفك الشخصي.' : 'Yes, you can toggle between Arabic and English at any time using the top navbar next to your profile.'
    },
    {
      q: isAr ? 'كيف أقوم بتصدير التقارير المالية؟' : 'How do I export financial reports?',
      a: isAr ? 'في قسم "التقارير"، اختر التقرير المطلوب (مثل الميزانية العمومية) واضغط على أيقونة التنزيل لتصديره كملف PDF أو CSV.' : 'In the "Reports" section, select the desired report (e.g., Balance Sheet) and click the download icon to export it as PDF or CSV.'
    },
    {
      q: isAr ? 'ماذا أفعل إذا نسيت كلمة المرور؟' : 'What should I do if I forget my password?',
      a: isAr ? 'في شاشة تسجيل الدخول، انقر على "نسيت كلمة المرور؟" واتبع التعليمات لاستعادة حسابك عبر بريدك الإلكتروني.' : 'On the login screen, click "Forgot Password?" and follow the instructions to recover your account via email.'
    }
  ];

  const handleSubmitTicket = (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketSubject || !ticketMessage) return;
    toast.success(isAr ? 'تم إرسال تذكرتك بنجاح. سيتواصل معك الدعم قريباً.' : 'Your ticket was submitted successfully. Support will contact you soon.');
    setTicketSubject('');
    setTicketMessage('');
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      <div className="text-center py-10 bg-card rounded-2xl border border-border shadow-sm mb-8">
        <div className="w-16 h-16 bg-primary/10 text-primary flex items-center justify-center rounded-full mx-auto mb-4">
          <LifeBuoy className="w-8 h-8" />
        </div>
        <h1 className="text-3xl font-bold text-foreground mb-3">
          {isAr ? 'كيف يمكننا مساعدتك اليوم؟' : 'How can we help you today?'}
        </h1>
        <p className="text-muted-foreground max-w-lg mx-auto mb-8">
          {isAr ? 'ابحث في قاعدة المعرفة، أو تواصل مع فريق الدعم الفني لحل أي مشكلة تواجهك.' : 'Search our knowledge base or contact our technical support team to resolve any issues.'}
        </p>
        
        <div className="max-w-md mx-auto relative px-4">
          <div className="absolute inset-y-0 start-0 flex items-center ps-7 pointer-events-none text-muted-foreground">
            <Search className="w-5 h-5" />
          </div>
          <Input 
            className="h-12 ps-12 rounded-full border-border shadow-sm bg-background"
            placeholder={isAr ? 'ابحث عن إجابات (مثال: طريقة إضافة فاتورة)' : 'Search for answers (e.g., how to add invoice)'}
          />
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-6 mb-12">
        <Card className="border-border shadow-sm text-center hover:shadow-md transition-shadow">
          <CardContent className="pt-6">
            <div className="w-12 h-12 bg-success/10 text-success rounded-full flex items-center justify-center mx-auto mb-4">
              <BookOpenIcon className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-lg mb-2">{isAr ? 'دليل المستخدم' : 'User Guide'}</h3>
            <p className="text-sm text-muted-foreground mb-4">{isAr ? 'تصفح الشروحات المفصلة لكل أجزاء النظام.' : 'Browse detailed tutorials for all system parts.'}</p>
            <Button variant="outline" className="w-full font-bold" onClick={() => window.open('#', '_blank')}>
              {isAr ? 'تصفح الدليل' : 'Browse Guide'}
            </Button>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm text-center hover:shadow-md transition-shadow">
          <CardContent className="pt-6">
            <div className="w-12 h-12 bg-warning/20 text-warning-foreground rounded-full flex items-center justify-center mx-auto mb-4">
              <PhoneCall className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-lg mb-2">{isAr ? 'اتصل بنا' : 'Call Us'}</h3>
            <p className="text-sm text-muted-foreground mb-4" dir="ltr">+966 9200 12345</p>
            <Button variant="outline" className="w-full font-bold" onClick={() => { window.location.href = "tel:+966500000000"; }}>
              {isAr ? 'اتصل الآن' : 'Call Now'}
            </Button>
          </CardContent>
        </Card>

        <Card className="border-border shadow-sm text-center hover:shadow-md transition-shadow">
          <CardContent className="pt-6">
            <div className="w-12 h-12 bg-primary/10 text-primary rounded-full flex items-center justify-center mx-auto mb-4">
              <Mail className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-lg mb-2">{isAr ? 'الدعم الفني' : 'Technical Support'}</h3>
            <p className="text-sm text-muted-foreground mb-4" dir="ltr">support@trustcore.com</p>
            <Button variant="outline" className="w-full font-bold" onClick={() => { window.location.href = "mailto:support@trustcore.com"; }}>
              {isAr ? 'إرسال بريد' : 'Send Email'}
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-8">
        <div>
          <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-primary" />
            {isAr ? 'الأسئلة الشائعة' : 'Frequently Asked Questions'}
          </h2>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div 
                key={i} 
                className={`border border-border rounded-lg overflow-hidden transition-colors ${openFaq === i ? 'bg-muted/30' : 'bg-card'}`}
              >
                <button 
                  className="w-full text-start p-4 flex justify-between items-center font-bold text-sm hover:text-primary transition-colors"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                >
                  {faq.q}
                  <ChevronDown className={`w-4 h-4 transition-transform ${openFaq === i ? 'rotate-180 text-primary' : 'text-muted-foreground'}`} />
                </button>
                {openFaq === i && (
                  <div className="p-4 pt-0 text-sm text-muted-foreground leading-relaxed border-t border-border/50 mt-2">
                    {faq.a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-primary" />
            {isAr ? 'إرسال تذكرة دعم' : 'Submit a Support Ticket'}
          </h2>
          <Card className="border-border shadow-sm">
            <CardContent className="p-6">
              <form onSubmit={handleSubmitTicket} className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-bold text-foreground">{isAr ? 'الموضوع' : 'Subject'}</label>
                  <Input 
                    value={ticketSubject}
                    onChange={(e) => setTicketSubject(e.target.value)}
                    placeholder={isAr ? 'ملخص المشكلة...' : 'Brief issue summary...'} 
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-bold text-foreground">{isAr ? 'التفاصيل' : 'Details'}</label>
                  <textarea 
                    value={ticketMessage}
                    onChange={(e) => setTicketMessage(e.target.value)}
                    className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                    placeholder={isAr ? 'اشرح المشكلة بالتفصيل...' : 'Explain the issue in detail...'}
                    required
                  />
                </div>
                <Button type="submit" className="w-full font-bold h-11">
                  {isAr ? 'إرسال التذكرة' : 'Submit Ticket'}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function BookOpenIcon(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
      <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </svg>
  )
}
