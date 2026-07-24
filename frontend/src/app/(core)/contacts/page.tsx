'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAppStore } from '@/store/use-app-store';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { 
  Plus, 
  Search, 
  Filter, 
  Download, 
  MoreVertical, 
  ArrowUpRight, 
  ArrowDownLeft, 
  Users, 
  TrendingUp,
  Edit,
  Trash,
  Eye
} from 'lucide-react';
import { DataTable, type Column } from '@/components/shared/DataTable';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const initialContacts = [
  { 
    id: '1', 
    name: 'مؤسسة الرمال الذهبية', 
    location: 'الرياض، المملكة العربية السعودية',
    initials: 'م.ر',
    type: 'عميل', 
    phone: '+966 50 123 4567',
    taxId: '300123456700003',
    balance: 12450.00,
    status: 'active' 
  },
  { 
    id: '2', 
    name: 'شركة الخليج للتوريدات', 
    location: 'جدة، المملكة العربية السعودية',
    initials: 'ش.خ',
    type: 'مورد', 
    phone: '+966 55 987 6543',
    taxId: '310987654300003',
    balance: -5200.00,
    status: 'review' 
  },
  { 
    id: '3', 
    name: 'سالم علي الشهري', 
    location: 'الدمام، المملكة العربية السعودية',
    initials: 'س.ع',
    type: 'عميل', 
    phone: '+966 54 555 1234',
    taxId: '--',
    balance: 0.00,
    status: 'suspended' 
  },
  { 
    id: '4', 
    name: 'مصنع التقنية الحديثة', 
    location: 'الجبيل، المملكة العربية السعودية',
    initials: 'م.ت',
    type: 'عميل', 
    phone: '+966 50 333 4444',
    taxId: '305555444400003',
    balance: 85200.00,
    status: 'active' 
  }
];

export default function ContactsPage() {
  const router = useRouter();
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';
  
  const [newName, setNewName] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newTaxId, setNewTaxId] = useState('');
  const [newType, setNewType] = useState('عميل');
  const [contacts, setContacts] = useState(initialContacts);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('الكل');

  const handleExportData = () => {
    const csvContent = "data:text/csv;charset=utf-8,ID,Name,Type,Balance,Status\n" + 
      (contacts || []).map(c => `${c.id},${c.name},${c.type},${c.balance},${c.status}`).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "contacts_export.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success(isAr ? 'تم تصدير القائمة بنجاح' : 'List exported successfully');
  };

  const { data = [], isLoading } = useQuery({
    queryKey: ['contacts', contacts],
    queryFn: async () => {
      await new Promise(resolve => setTimeout(resolve, 500));
      return contacts;
    }
  });

  const handleAddContact = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName || !newPhone) return;

    const initials = newName.substring(0, 2).toUpperCase();
    const newContact = {
      id: Date.now().toString(),
      name: newName,
      location: isAr ? 'السعودية' : 'Saudi Arabia',
      initials,
      type: newType,
      phone: newPhone,
      taxId: newTaxId || '--',
      balance: 0.00,
      status: 'active'
    };

    setContacts([newContact, ...contacts]);
    setNewName('');
    setNewPhone('');
    setNewTaxId('');
    setIsAddOpen(false);
    toast.success(isAr ? 'تمت إضافة جهة الاتصال بنجاح' : 'Contact added successfully');
  };

  const columns: Column<typeof contacts[0]>[] = [
    { 
      header: isAr ? 'الاسم' : 'Name', 
      accessorKey: 'name',
      cell: (item) => (
        <div className="flex items-center gap-3 cursor-pointer" onClick={() => router.push(`/contacts/${item.id}`)}>
          <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm
            ${item.status === 'active' ? 'bg-primary/20 text-primary' : 
              item.status === 'review' ? 'bg-warning/20 text-warning-foreground' : 
              'bg-sidebar text-white'}`}
          >
            {item.initials}
          </div>
          <div>
            <p className="font-bold text-foreground hover:text-primary transition-colors">{item.name}</p>
            <p className="text-xs text-muted-foreground">{item.location}</p>
          </div>
        </div>
      )
    },
    { 
      header: isAr ? 'رقم الهاتف' : 'Phone', 
      accessorKey: 'phone',
      cell: (item) => <span className="font-mono text-sm block max-w-[120px] leading-tight" dir="ltr">{item.phone}</span>
    },
    { 
      header: isAr ? 'الرقم الضريبي' : 'Tax ID', 
      accessorKey: 'taxId',
      cell: (item) => <span className="font-mono text-sm" dir="ltr">{item.taxId}</span>
    },
    { 
      header: isAr ? 'الرصيد الحالي' : 'Current Balance', 
      accessorKey: 'balance',
      cell: (item) => (
        <span className={`font-mono text-sm font-bold ${item.balance < 0 ? 'text-danger' : 'text-foreground'}`} dir="ltr">
          {item.balance < 0 ? `(${Math.abs(item.balance).toLocaleString('en-US', { minimumFractionDigits: 2 })}-)` : item.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          <span className="ms-1 font-sans font-normal text-muted-foreground text-xs">EGP</span>
        </span>
      )
    },
    { 
      header: isAr ? 'النوع' : 'Type', 
      accessorKey: 'type',
      cell: (item) => (
        <Badge variant="secondary" className="bg-muted text-muted-foreground hover:bg-muted font-normal text-xs rounded-full px-3 shadow-none">
          {item.type}
        </Badge>
      )
    },
    { 
      header: isAr ? 'الحالة' : 'Status', 
      accessorKey: 'status',
      cell: (item) => {
        let bg = '';
        let text = '';
        let label = '';
        
        if (item.status === 'active') {
          bg = 'bg-success/20';
          text = 'text-success';
          label = isAr ? 'نشط' : 'Active';
        } else if (item.status === 'review') {
          bg = 'bg-warning/20';
          text = 'text-warning-foreground';
          label = isAr ? 'قيد المراجعة' : 'Under Review';
        } else {
          bg = 'bg-danger/10';
          text = 'text-danger';
          label = isAr ? 'متوقف' : 'Suspended';
        }
        
        return (
          <Badge className={`${bg} ${text} hover:${bg} border-transparent font-bold text-xs rounded-full px-3 py-1 shadow-none`}>
            {label}
          </Badge>
        );
      }
    },
    {
      header: isAr ? 'الإجراء' : 'Action',
      cell: (item) => (
        <Dialog>
        <DropdownMenu>
          <DropdownMenuTrigger render={
            <button className="p-2 text-muted-foreground hover:text-foreground rounded-full hover:bg-muted transition-colors">
              <MoreVertical className="w-5 h-5" />
            </button>
          } />
            <DialogTrigger render={
              <DropdownMenuItem className="gap-2 cursor-pointer font-bold">
                <Eye className="w-4 h-4 text-primary" /> {isAr ? 'عرض التفاصيل' : 'View Details'}
              </DropdownMenuItem>
            } />
            <DialogTrigger render={
              <DropdownMenuItem className="gap-2 cursor-pointer font-bold">
                <Edit className="w-4 h-4 text-warning-foreground" /> {isAr ? 'تعديل السجل' : 'Edit Record'}
              </DropdownMenuItem>
            } />
            <DropdownMenuItem className="gap-2 cursor-pointer font-bold text-danger focus:text-danger" onClick={() => toast.success(isAr ? 'تم حذف السجل' : 'Record deleted')}>
              <Trash className="w-4 h-4" /> {isAr ? 'حذف السجل' : 'Delete Record'}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{isAr ? 'تفاصيل السجل' : 'Record Details'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-4">
            <div className="space-y-2">
              <label className="text-sm font-bold">{isAr ? 'الاسم' : 'Name'}</label>
              <Input defaultValue={item.name} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold">{isAr ? 'الرصيد' : 'Balance'}</label>
              <Input defaultValue={item.balance} />
            </div>
            <Button className="w-full font-bold" onClick={() => toast.success(isAr ? 'تم حفظ التعديلات' : 'Changes saved')}>
              {isAr ? 'حفظ' : 'Save'}
            </Button>
          </div>
        </DialogContent>
        </Dialog>
      )
    }
  ];

  const metrics = [
    {
      title: isAr ? 'المستحقات للموردين' : 'Supplier Dues',
      value: '115,200',
      icon: ArrowUpRight,
      iconBg: 'bg-danger/10',
      iconColor: 'text-danger'
    },
    {
      title: isAr ? 'المستحقات للشركة' : 'Company Dues',
      value: '420,500',
      icon: ArrowDownLeft,
      iconBg: 'bg-warning/20',
      iconColor: 'text-warning-foreground'
    },
    {
      title: isAr ? 'العملاء النشطين' : 'Active Clients',
      value: '842',
      icon: TrendingUp,
      iconBg: 'bg-success/20',
      iconColor: 'text-success'
    },
    {
      title: isAr ? 'إجمالي الجهات' : 'Total Contacts',
      value: '1,284',
      icon: Users,
      iconBg: 'bg-muted',
      iconColor: 'text-muted-foreground'
    }
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground">
            {isAr ? 'دليل جهات الاتصال' : 'Contacts Directory'}
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            {isAr ? 'إدارة وتتبع بيانات العملاء والموردين والمعاملات المالية' : 'Manage and track clients, suppliers, and financial transactions'}
          </p>
        </div>
        
        <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
          <DialogTrigger render={
            <Button className="gap-2 font-bold h-11 px-6 text-primary-foreground shadow hover:bg-accent-hover transition-colors">
              <Plus className="w-5 h-5" />
              {isAr ? 'إضافة جهة اتصال' : 'Add Contact'}
            </Button>
          } />
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{isAr ? 'إضافة جهة اتصال جديدة' : 'Add New Contact'}</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleAddContact} className="space-y-4 pt-4">
              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'الاسم' : 'Name'}</label>
                <Input 
                  value={newName} 
                  onChange={e => setNewName(e.target.value)} 
                  placeholder={isAr ? 'أدخل اسم الجهة' : 'Enter name'}
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'النوع' : 'Type'}</label>
                <select 
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary"
                  value={newType}
                  onChange={e => setNewType(e.target.value)}
                >
                  <option value="عميل">{isAr ? 'عميل' : 'Client'}</option>
                  <option value="مورد">{isAr ? 'مورد' : 'Supplier'}</option>
                  <option value="جهة حكومية">{isAr ? 'جهة حكومية' : 'Government'}</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'رقم الهاتف' : 'Phone Number'}</label>
                <Input 
                  value={newPhone} 
                  onChange={e => setNewPhone(e.target.value)} 
                  placeholder="+966 50 000 0000"
                  dir="ltr"
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'الرقم الضريبي' : 'Tax ID'}</label>
                <Input 
                  value={newTaxId} 
                  onChange={e => setNewTaxId(e.target.value)} 
                  placeholder="300..."
                  dir="ltr"
                />
              </div>
              <DialogFooter>
                <Button type="submit" className="w-full font-bold">{isAr ? 'إضافة' : 'Add'}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric, index) => (
          <Card key={index} className="border-border shadow-sm">
            <CardContent className="p-6 flex items-center justify-between">
              <div className={`w-12 h-12 rounded-lg ${metric.iconBg} flex items-center justify-center flex-shrink-0`}>
                <metric.icon className={`w-6 h-6 ${metric.iconColor}`} />
              </div>
              <div className="text-end">
                <p className="text-sm font-medium text-muted-foreground mb-1">{metric.title}</p>
                <div className="flex items-end justify-end gap-1">
                  <span className="text-2xl font-bold font-mono text-foreground leading-none">{metric.value}</span>
                  {metric.title.includes('المستحقات') && <span className="text-xs text-muted-foreground mb-1">EGP</span>}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="bg-card border border-border rounded-xl shadow-sm p-2">
        <div className="flex flex-col sm:flex-row justify-between items-center gap-4 p-4 border-b border-border/50">
          <div className="flex gap-2 w-full sm:w-auto overflow-x-auto pb-2 sm:pb-0 hide-scrollbar">
            {['الكل', 'عملاء', 'موردين', 'جهات أخرى'].map((tab, idx) => {
              const tabId = ['all', 'clients', 'suppliers', 'others'][idx];
              const isActive = activeTab === tabId;
              return (
                <button
                  key={tabId}
                  onClick={() => setActiveTab(tabId)}
                  className={`px-6 py-2 rounded-full text-sm font-bold transition-all whitespace-nowrap
                    ${isActive ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
                >
                  {isAr ? tab : ['All', 'Clients', 'Suppliers', 'Others'][idx]}
                </button>
              );
            })}
          </div>
          <div className="flex gap-3 w-full sm:w-auto">
            <Dialog open={isFilterOpen} onOpenChange={setIsFilterOpen}>
              <DialogTrigger render={
                <Button variant="outline" className="gap-2 w-full sm:w-auto h-10 border-border text-foreground">
                  <Filter className="w-4 h-4" />
                  {isAr ? 'تصفية متقدمة' : 'Advanced Filter'}
                </Button>
              } />
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{isAr ? 'خيارات التصفية المتقدمة' : 'Advanced Filter Options'}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-4">
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'نطاق الرصيد' : 'Balance Range'}</label>
                    <div className="flex gap-2">
                      <Input placeholder={isAr ? 'من' : 'Min'} type="number" />
                      <Input placeholder={isAr ? 'إلى' : 'Max'} type="number" />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'المدينة' : 'City'}</label>
                    <Input placeholder={isAr ? 'أدخل اسم المدينة' : 'Enter city name'} />
                  </div>
                  <Button className="w-full font-bold" onClick={() => {
                    setIsFilterOpen(false);
                    toast.success(isAr ? 'تم تطبيق التصفية' : 'Filters applied');
                  }}>
                    {isAr ? 'تطبيق' : 'Apply'}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
            <Button 
              variant="outline" 
              className="gap-2 w-full sm:w-auto h-10 border-border text-foreground"
              onClick={handleExportData}
            >
              <Download className="w-4 h-4" />
              {isAr ? 'تصدير البيانات' : 'Export Data'}
            </Button>
          </div>
        </div>
        
        <div className="p-2">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">{isAr ? 'جاري التحميل...' : 'Loading...'}</div>
          ) : (
            <DataTable 
              columns={columns} 
              data={activeTab === 'all' ? data : data.filter(c => 
                (activeTab === 'clients' && c.type === 'عميل') ||
                (activeTab === 'suppliers' && c.type === 'مورد') ||
                (activeTab === 'others' && c.type !== 'عميل' && c.type !== 'مورد')
              )} 
              searchable={false}
            />
          )}
        </div>
      </div>
    </div>
  );
}
