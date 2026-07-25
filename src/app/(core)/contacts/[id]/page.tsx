'use client';

import { useParams, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useAppStore } from '@/store/use-app-store';
import { Button } from '@/components/ui/button';
import { ArrowRight, ArrowLeft, Mail, Phone, MapPin, Building2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export default function ContactDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  const { data: contact, isLoading } = useQuery({
    queryKey: ['contact', id],
    queryFn: async () => {
      await new Promise(resolve => setTimeout(resolve, 300));
      return { 
        id, 
        name: 'شركة التقنية المتقدمة', 
        type: 'client', 
        email: 'info@tech.com', 
        phone: '+966500000001', 
        status: 'active',
        address: 'الرياض, طريق الملك فهد',
        taxId: '300000000000003',
        balance: 14500.50
      };
    }
  });

  if (isLoading || !contact) {
    return <div className="p-6 text-center">{isAr ? 'جاري التحميل...' : 'Loading...'}</div>;
  }

  const typeMap = {
    client: isAr ? 'عميل' : 'Client',
    supplier: isAr ? 'مورد' : 'Supplier',
    employee: isAr ? 'موظف' : 'Employee'
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => router.back()}>
          {isAr ? <ArrowRight className="w-5 h-5" /> : <ArrowLeft className="w-5 h-5" />}
        </Button>
        <h1 className="text-2xl font-bold text-foreground">{isAr ? 'تفاصيل الكيان' : 'Contact Details'}</h1>
      </div>

      <div className="bg-card border border-border rounded-lg shadow-sm p-6 space-y-6">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center text-primary border border-primary/20">
              <Building2 className="w-8 h-8" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-foreground">{contact.name}</h2>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm text-muted-foreground">{typeMap[contact.type as keyof typeof typeMap]}</span>
                <span className="text-muted-foreground">•</span>
                <Badge variant={contact.status === 'active' ? 'default' : 'secondary'} className={contact.status === 'active' ? 'bg-success hover:bg-success/90 text-primary-foreground' : 'bg-muted text-muted-foreground'}>
                  {contact.status === 'active' ? (isAr ? 'نشط' : 'Active') : (isAr ? 'غير نشط' : 'Inactive')}
                </Badge>
              </div>
            </div>
          </div>
          <div className="text-start sm:text-end">
            <p className="text-sm text-muted-foreground">{isAr ? 'الرصيد المالي' : 'Balance'}</p>
            <p className="text-2xl font-mono font-bold text-foreground" dir="ltr">
              {contact.balance.toLocaleString('en-US', { style: 'currency', currency: 'EGP' })}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-6 border-t border-border">
          <div className="flex items-start gap-3">
            <Mail className="w-5 h-5 text-muted-foreground mt-0.5" />
            <div>
              <p className="text-sm font-medium text-foreground">{isAr ? 'البريد الإلكتروني' : 'Email'}</p>
              <p className="text-sm text-muted-foreground mt-1" dir="ltr">{contact.email}</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Phone className="w-5 h-5 text-muted-foreground mt-0.5" />
            <div>
              <p className="text-sm font-medium text-foreground">{isAr ? 'رقم الهاتف' : 'Phone'}</p>
              <p className="text-sm text-muted-foreground mt-1 font-mono" dir="ltr">{contact.phone}</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MapPin className="w-5 h-5 text-muted-foreground mt-0.5" />
            <div>
              <p className="text-sm font-medium text-foreground">{isAr ? 'العنوان' : 'Address'}</p>
              <p className="text-sm text-muted-foreground mt-1">{contact.address}</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <FileTextIcon className="w-5 h-5 text-muted-foreground mt-0.5" />
            <div>
              <p className="text-sm font-medium text-foreground">{isAr ? 'الرقم الضريبي' : 'Tax ID'}</p>
              <p className="text-sm text-muted-foreground mt-1 font-mono" dir="ltr">{contact.taxId}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FileTextIcon(props: any) {
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
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}
