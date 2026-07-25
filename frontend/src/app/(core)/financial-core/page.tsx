'use client';

import { useState } from 'react';
import { useAppStore } from '@/store/use-app-store';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { 
  Plus, 
  FileUp, 
  Wallet, 
  ArrowUpRight, 
  ArrowDownLeft, 
  MoreVertical,
  Banknote,
  Upload,
  Download
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

const mockAccounts = [
  { id: '1000', name: 'الأصول', type: 'رئيسي', balance: 2450000.00, status: 'active', hasChildren: true },
  { id: '1100', name: 'الأصول المتداولة', type: 'رئيسي', balance: 890000.00, status: 'active', hasChildren: true },
  { id: '1110', name: 'النقد وما في حكمه', type: 'فرعي', balance: 450200.50, status: 'active', hasChildren: false },
  { id: '2000', name: 'الالتزامات', type: 'رئيسي', balance: 1120500.00, status: 'active', hasChildren: true },
  { id: '3000', name: 'حقوق الملكية', type: 'رئيسي', balance: 1329500.00, status: 'active', hasChildren: true },
  { id: '4000', name: 'الإيرادات', type: 'رئيسي', balance: 3400000.00, status: 'active', hasChildren: true },
];

const initialJournalEntries = [
  { id: 'JE-2024-089', date: '24/05/2024', description: 'سداد إيجار المكتب الرئيسي - الربع الثاني', amount: 45000.00, status: 'posted' },
  { id: 'JE-2024-090', date: '25/05/2024', description: 'فاتورة الكهرباء والمياه - شهر مايو', amount: 4230.15, status: 'pending' },
  { id: 'PV-2024-012', date: '26/05/2024', description: 'سند صرف: مشتريات أدوات مكتبية قرطاسية', amount: 1450.00, status: 'posted' },
];

export default function FinancialCorePage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  const [journalEntries, setJournalEntries] = useState(initialJournalEntries);
  const [isAddEntryOpen, setIsAddEntryOpen] = useState(false);
  const [newDesc, setNewDesc] = useState('');
  const [newAmount, setNewAmount] = useState('');
  
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [isTransferOpen, setIsTransferOpen] = useState(false);
  const [isReceiptOpen, setIsReceiptOpen] = useState(false);
  const [isPaymentOpen, setIsPaymentOpen] = useState(false);

  const handleAddEntry = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDesc || !newAmount) return;

    const newEntry = {
      id: `JE-2024-0${90 + journalEntries.length}`,
      date: new Date().toLocaleDateString('en-GB'),
      description: newDesc,
      amount: parseFloat(newAmount),
      status: 'pending'
    };

    setJournalEntries([newEntry, ...journalEntries]);
    setNewDesc('');
    setNewAmount('');
    setIsAddEntryOpen(false);
    toast.success(isAr ? 'تمت إضافة القيد المحاسبي بنجاح' : 'Journal entry added successfully');
  };

  const accountColumns: Column<typeof mockAccounts[0]>[] = [
    { 
      header: isAr ? 'رقم الحساب' : 'Account Number', 
      accessorKey: 'id',
      cell: (item) => <span className="font-mono font-bold" dir="ltr">{item.id}</span>
    },
    { 
      header: isAr ? 'اسم الحساب' : 'Account Name', 
      accessorKey: 'name',
      cell: (item) => (
        <div className="flex items-center gap-2">
          <span className={item.type === 'فرعي' ? 'ms-4 text-muted-foreground' : 'font-bold text-foreground'}>
            {item.name}
          </span>
        </div>
      )
    },
    { 
      header: isAr ? 'النوع' : 'Type', 
      accessorKey: 'type',
      cell: (item) => <span className="text-muted-foreground text-sm">{item.type}</span>
    },
    { 
      header: isAr ? 'الرصيد (EGP)' : 'Balance (EGP)', 
      accessorKey: 'balance',
      cell: (item) => (
        <span className="font-mono font-bold text-foreground" dir="ltr">
          {item.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}
        </span>
      )
    },
    { 
      header: isAr ? 'الحالة' : 'Status', 
      accessorKey: 'status',
      cell: (item) => (
        <Badge className="bg-success/20 text-success hover:bg-success/20 border-transparent shadow-none font-bold">
          {item.status === 'active' ? (isAr ? 'نشط' : 'Active') : (isAr ? 'متوقف' : 'Inactive')}
        </Badge>
      )
    },
  ];

  const journalColumns: Column<typeof journalEntries[0]>[] = [
    { 
      header: isAr ? 'رقم القيد' : 'Entry Number', 
      accessorKey: 'id',
      cell: (item) => <span className="font-mono font-bold" dir="ltr">{item.id}</span>
    },
    { 
      header: isAr ? 'التاريخ' : 'Date', 
      accessorKey: 'date',
      cell: (item) => <span className="font-mono text-muted-foreground" dir="ltr">{item.date}</span>
    },
    { 
      header: isAr ? 'البيان' : 'Description', 
      accessorKey: 'description',
      cell: (item) => <span className="text-foreground text-sm font-medium">{item.description}</span>
    },
    { 
      header: isAr ? 'المبلغ (EGP)' : 'Amount (EGP)', 
      accessorKey: 'amount',
      cell: (item) => (
        <span className="font-mono font-bold text-foreground" dir="ltr">
          {item.amount.toLocaleString('en-US', { minimumFractionDigits: 2 })}
        </span>
      )
    },
    { 
      header: isAr ? 'الحالة' : 'Status', 
      accessorKey: 'status',
      cell: (item) => (
        <Badge className={
          item.status === 'posted' 
            ? "bg-success/20 text-success hover:bg-success/20 border-transparent shadow-none font-bold"
            : "bg-warning/20 text-warning-foreground hover:bg-warning/20 border-transparent shadow-none font-bold"
        }>
          {item.status === 'posted' ? (isAr ? 'مرحل' : 'Posted') : (isAr ? 'قيد الانتظار' : 'Pending')}
        </Badge>
      )
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 text-muted-foreground text-sm mb-1">
            <span>{isAr ? 'الإدارة المالية' : 'Financial Management'}</span>
            <span>|</span>
            <span className="font-semibold text-foreground">{isAr ? 'الحسابات والمعاملات' : 'Accounts and Transactions'}</span>
          </div>
          <p className="text-sm text-muted-foreground">
            {isAr ? 'إدارة دليل الحسابات، القيود المحاسبية، والمراكز النقدية للمنشأة' : 'Manage chart of accounts, journal entries, and cash positions'}
          </p>
        </div>
        <div className="flex gap-3">
          <Dialog open={isImportOpen} onOpenChange={setIsImportOpen}>
            <DialogTrigger className={cn(buttonVariants({ variant: 'outline' }), "gap-2 h-11 border-border shadow-sm font-bold text-foreground hover:bg-muted transition-colors")}>
                <FileUp className="w-5 h-5" />
                {isAr ? 'استيراد بيانات' : 'Import Data'}
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{isAr ? 'استيراد قيود محاسبية' : 'Import Journal Entries'}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-4">
                <div 
                  className="flex flex-col items-center justify-center p-8 border-2 border-dashed border-border rounded-xl bg-muted/10 hover:bg-muted/20 transition-colors cursor-pointer text-center relative overflow-hidden"
                >
                  <input 
                    type="file" 
                    className="absolute inset-0 opacity-0 cursor-pointer" 
                    accept=".csv,.xlsx" 
                    onChange={(e) => {
                      if (e.target.files?.length) {
                        toast.success(isAr ? 'تم استيراد البيانات بنجاح' : 'Data imported successfully');
                        setIsImportOpen(false);
                      }
                    }} 
                  />
                  <FileUp className="w-12 h-12 text-muted-foreground mb-3 opacity-50" />
                  <p className="text-sm font-bold text-muted-foreground">{isAr ? 'اختر ملف CSV أو Excel' : 'Choose CSV or Excel file'}</p>
                </div>
              </div>
            </DialogContent>
          </Dialog>
          
          <Dialog open={isAddEntryOpen} onOpenChange={setIsAddEntryOpen}>
            <DialogTrigger className={cn(buttonVariants({ variant: 'default' }), "gap-2 h-11 px-6 font-bold shadow hover:bg-accent-hover transition-colors")}>
                <Plus className="w-5 h-5" />
                {isAr ? 'إضافة قيد محاسبي' : 'Add Journal Entry'}
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{isAr ? 'إضافة قيد محاسبي جديد' : 'Add New Journal Entry'}</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleAddEntry} className="space-y-4 pt-4">
                <div className="space-y-2">
                  <label className="text-sm font-bold">{isAr ? 'البيان' : 'Description'}</label>
                  <Input 
                    value={newDesc} 
                    onChange={e => setNewDesc(e.target.value)} 
                    placeholder={isAr ? 'أدخل وصف القيد' : 'Enter entry description'}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-bold">{isAr ? 'المبلغ' : 'Amount'}</label>
                  <Input 
                    type="number"
                    value={newAmount} 
                    onChange={e => setNewAmount(e.target.value)} 
                    placeholder="0.00"
                    dir="ltr"
                    required
                  />
                </div>
                <DialogFooter>
                  <Button type="submit" className="w-full font-bold">{isAr ? 'إضافة القيد' : 'Add Entry'}</Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>

        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        
        {/* Right side (Main content in RTL) */}
        <div className="flex-1 space-y-6 lg:order-1 order-2">
          
          <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border/50 flex items-center justify-between">
              <div className="flex items-center gap-2 text-primary font-bold">
                <Banknote className="w-5 h-5" />
                <h2>{isAr ? 'دليل الحسابات' : 'Chart of Accounts'}</h2>
              </div>
            </div>
            <div className="p-2">
              <DataTable 
                columns={accountColumns} 
                data={mockAccounts} 
                searchable={false}
              />
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
            <div className="p-4 border-b border-border/50 flex items-center justify-between">
              <div className="flex items-center gap-2 text-primary font-bold">
                <Banknote className="w-5 h-5" />
                <h2>{isAr ? 'أحدث القيود المحاسبية' : 'Latest Journal Entries'}</h2>
              </div>
              <a 
                className="text-sm font-bold text-primary hover:underline cursor-pointer"
                href="/transactions"
              >
                {isAr ? 'عرض الكل' : 'View All'}
              </a>
            </div>
            <div className="p-2">
              <DataTable 
                columns={journalColumns} 
                data={journalEntries} 
                searchable={false}
              />
            </div>
          </div>

        </div>

        {/* Left side (Side panel in RTL) */}
        <div className="w-full lg:w-[350px] flex-shrink-0 space-y-6 lg:order-2 order-1">
          
          <div className="bg-card border border-border rounded-xl shadow-sm p-5">
            <div className="flex items-center gap-2 text-primary font-bold mb-5">
              <Wallet className="w-5 h-5" />
              <h2>{isAr ? 'النقد والبنوك' : 'Cash and Banks'}</h2>
              <Badge variant="outline" className="ms-auto bg-warning/10 text-warning-foreground border-transparent text-[10px]">LIVE</Badge>
            </div>
            
            <div className="space-y-3">
              {[
                { name: isAr ? 'البنك التجاري الدولي (CIB)' : 'CIB Bank', acc: '1002', balance: '342,150.00', change: '+2.4%', up: true },
                { name: isAr ? 'البنك الأهلي المصري' : 'National Bank of Egypt', acc: '3044', balance: '88,050.50', change: '-1.1%', up: false },
                { name: isAr ? 'صندوق العهدة' : 'Petty Cash', acc: '0001', balance: '20,000.00', change: '0.0%', up: true }
              ].map((bank, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded-lg border border-border bg-background/50 hover:bg-muted transition-colors cursor-pointer">
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">
                      {bank.name} - <span className="font-mono">{bank.acc}</span>
                    </p>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-bold font-mono ${bank.change.startsWith('-') ? 'text-danger' : bank.change === '0.0%' ? 'text-muted-foreground' : 'text-success'}`} dir="ltr">
                        {bank.change}
                      </span>
                    </div>
                  </div>
                  <div className="font-mono font-bold text-foreground text-lg" dir="ltr">
                    {bank.balance}
                  </div>
                </div>
              ))}
            </div>
            
            <Dialog open={isTransferOpen} onOpenChange={setIsTransferOpen}>
              <DialogTrigger className={cn(buttonVariants({ variant: 'outline' }), "w-full mt-4 border-border font-bold text-foreground hover:bg-muted transition-colors")}>
                  {isAr ? 'تحويل بين الحسابات' : 'Transfer between accounts'}
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{isAr ? 'تحويل نقدي' : 'Cash Transfer'}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-4">
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'من حساب' : 'From Account'}</label>
                    <select className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50">
                      <option>{isAr ? 'البنك التجاري الدولي (رئيسي)' : 'CIB Bank (Main)'}</option>
                      <option>{isAr ? 'البنك الأهلي المصري' : 'National Bank of Egypt'}</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'إلى حساب' : 'To Account'}</label>
                    <select className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50">
                      <option>{isAr ? 'البنك الأهلي المصري' : 'National Bank of Egypt'}</option>
                      <option>{isAr ? 'البنك التجاري الدولي (رئيسي)' : 'CIB Bank (Main)'}</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'المبلغ' : 'Amount'}</label>
                    <Input type="number" placeholder="0.00" dir="ltr" />
                  </div>
                  <Button className="w-full font-bold h-11" onClick={() => {
                    toast.success(isAr ? 'تم التحويل بنجاح' : 'Transferred successfully');
                    setIsTransferOpen(false);
                  }}>
                    {isAr ? 'تنفيذ التحويل' : 'Execute Transfer'}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          <div className="bg-sidebar rounded-xl shadow-sm p-5 text-white">
            <p className="text-sidebar-subtitle text-sm mb-1">{isAr ? 'إجمالي السيولة المتاحة' : 'Total Available Liquidity'}</p>
            <div className="flex items-end gap-1 mb-6">
              <span className="text-xs text-sidebar-subtitle mb-1">EGP</span>
              <span className="text-3xl font-bold font-mono tracking-tight" dir="ltr">450,200.50</span>
            </div>
            
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-sidebar-subtitle">{isAr ? 'التدفقات الداخلة (شهرية)' : 'Inflows (Monthly)'}</span>
                  <span className="font-mono text-success font-bold" dir="ltr">+124,000.00</span>
                </div>
                <div className="h-1.5 w-full bg-sidebar-accent rounded-full overflow-hidden">
                  <div className="h-full bg-success w-[75%] rounded-full"></div>
                </div>
              </div>
              
              <div>
                <div className="flex justify-between text-xs mb-1.5">
                  <span className="text-sidebar-subtitle">{isAr ? 'المصروفات (شهرية)' : 'Outflows (Monthly)'}</span>
                  <span className="font-mono text-sidebar-primary-foreground" dir="ltr">-82,400.00</span>
                </div>
                <div className="h-1.5 w-full bg-sidebar-accent rounded-full overflow-hidden">
                  <div className="h-full bg-sidebar-primary-foreground w-[45%] rounded-full"></div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl shadow-sm p-5">
            <h2 className="font-bold text-foreground mb-4">{isAr ? 'إنشاء سند سريع' : 'Quick Voucher'}</h2>
            <div className="grid grid-cols-2 gap-3">
              <Dialog open={isReceiptOpen} onOpenChange={setIsReceiptOpen}>
                <DialogTrigger render={
                  <button className="flex flex-col items-center justify-center p-4 border border-border rounded-lg bg-background/50 hover:bg-muted transition-colors gap-2 group">
                    <div className="w-10 h-10 rounded-full bg-success/10 text-success flex items-center justify-center group-hover:scale-110 transition-transform">
                      <Download className="w-5 h-5" />
                    </div>
                    <span className="font-bold text-sm text-foreground">{isAr ? 'سند قبض' : 'Receipt'}</span>
                  </button>
                } />
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{isAr ? 'إنشاء سند قبض' : 'Create Receipt Voucher'}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 pt-4">
                    <div className="space-y-2">
                      <label className="text-sm font-bold">{isAr ? 'المبلغ' : 'Amount'}</label>
                      <Input type="number" placeholder="0.00" dir="ltr" />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-bold">{isAr ? 'البيان' : 'Description'}</label>
                      <Input placeholder={isAr ? 'سبب القبض' : 'Reason for receipt'} />
                    </div>
                    <Button className="w-full font-bold" onClick={() => {
                      toast.success(isAr ? 'تم حفظ السند' : 'Voucher saved');
                      setIsReceiptOpen(false);
                    }}>{isAr ? 'حفظ السند' : 'Save Voucher'}</Button>
                  </div>
                </DialogContent>
              </Dialog>

              <Dialog open={isPaymentOpen} onOpenChange={setIsPaymentOpen}>
                <DialogTrigger render={
                  <button className="flex flex-col items-center justify-center p-4 border border-border rounded-lg bg-background/50 hover:bg-muted transition-colors gap-2 group">
                    <div className="w-10 h-10 rounded-full bg-primary/10 text-primary flex items-center justify-center group-hover:scale-110 transition-transform">
                      <Upload className="w-5 h-5" />
                    </div>
                    <span className="font-bold text-sm text-foreground">{isAr ? 'سند صرف' : 'Payment'}</span>
                  </button>
                } />
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{isAr ? 'إنشاء سند صرف' : 'Create Payment Voucher'}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 pt-4">
                    <div className="space-y-2">
                      <label className="text-sm font-bold">{isAr ? 'المبلغ' : 'Amount'}</label>
                      <Input type="number" placeholder="0.00" dir="ltr" />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-bold">{isAr ? 'البيان' : 'Description'}</label>
                      <Input placeholder={isAr ? 'سبب الصرف' : 'Reason for payment'} />
                    </div>
                    <Button className="w-full font-bold" onClick={() => {
                      toast.success(isAr ? 'تم حفظ السند' : 'Voucher saved');
                      setIsPaymentOpen(false);
                    }}>{isAr ? 'حفظ السند' : 'Save Voucher'}</Button>
                  </div>
                </DialogContent>
              </Dialog>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
