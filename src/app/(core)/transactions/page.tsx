'use client';

import { useAppStore } from '@/store/use-app-store';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { useState } from 'react';
import { 
  FileOutput, 
  Filter,
  Eye,
  Download,
  MoreVertical
} from 'lucide-react';
import { DataTable, type Column } from '@/components/shared/DataTable';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const mockTransactions = [
  { id: 'TRX-99201', date: '2024/05/12', type: 'فاتورة مبيعات', description: 'توريد معدات مكتبية - فرع الرياض', party: 'شركة الحلول المتقدمة', amount: 45200.00, isPositive: true },
  { id: 'TRX-99198', date: '2024/05/12', type: 'سند صرف', description: 'صيانة دورية للمكيفات والكهرباء', party: 'مؤسسة الأمان للصيانة', amount: -8450.00, isPositive: false },
  { id: 'TRX-99185', date: '2024/05/11', type: 'سند قبض', description: 'دفعة مقدمة - مشروع تطوير الموقع', party: 'مجموعة النايف للتقنية', amount: 12000.00, isPositive: true },
  { id: 'TRX-99172', date: '2024/05/10', type: 'تحويل بنكي', description: 'تحويل رواتب الموظفين - مايو', party: 'البنك التجاري الدولي (CIB)', amount: -156000.00, isPositive: false },
  { id: 'TRX-99168', date: '2024/05/10', type: 'فاتورة مشتريات', description: 'أدوات مكتبية وقرطاسية', party: 'مكتبة جرير', amount: -3200.00, isPositive: false },
];

export default function TransactionsPage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';
  
  const [selectedTx, setSelectedTx] = useState<typeof mockTransactions[0] | null>(null);

  const handleExportData = () => {
    const csvContent = "data:text/csv;charset=utf-8,ID,Date,Type,Description,Party,Amount\n" + 
      mockTransactions.map(t => `${t.id},${t.date},${t.type},${t.description},${t.party},${t.amount}`).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "transactions_export.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success(isAr ? 'تم تصدير البيانات بنجاح' : 'Data exported successfully');
  };

  const columns: Column<typeof mockTransactions[0]>[] = [
    { 
      header: isAr ? 'التاريخ' : 'Date', 
      accessorKey: 'date',
      cell: (item) => <span className="font-mono font-bold text-foreground" dir="ltr">{item.date}</span>
    },
    { 
      header: isAr ? 'رقم المعاملة' : 'Transaction No', 
      accessorKey: 'id',
      cell: (item) => <span className="font-mono font-bold text-foreground" dir="ltr">{item.id}</span>
    },
    { 
      header: isAr ? 'النوع' : 'Type', 
      accessorKey: 'type',
      cell: (item) => (
        <Badge variant="secondary" className="bg-muted text-muted-foreground hover:bg-muted border-transparent font-medium rounded-full px-4">
          {item.type}
        </Badge>
      )
    },
    { 
      header: isAr ? 'الوصف' : 'Description', 
      accessorKey: 'description',
      cell: (item) => <span className="text-muted-foreground text-sm">{item.description}</span>
    },
    { 
      header: isAr ? 'الجهة المرتبطة' : 'Related Party', 
      accessorKey: 'party',
      cell: (item) => <span className="text-muted-foreground text-sm">{item.party}</span>
    },
    { 
      header: isAr ? 'المبلغ' : 'Amount', 
      accessorKey: 'amount',
      cell: (item) => (
        <span className={`font-mono font-bold text-sm ${item.isPositive ? 'text-success' : 'text-danger'}`} dir="ltr">
          {item.isPositive ? '' : '-'}{Math.abs(item.amount).toLocaleString('en-US', { minimumFractionDigits: 2 })} {isAr ? 'ج.م' : 'EGP'}
        </span>
      )
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
            <DropdownMenuContent align="end" className="w-48">
              <DialogTrigger render={
                <DropdownMenuItem className="gap-2 cursor-pointer font-bold" onClick={() => setSelectedTx(item)}>
                  <Eye className="w-4 h-4 text-primary" /> {isAr ? 'عرض التفاصيل' : 'View Details'}
                </DropdownMenuItem>
              } />
              <DropdownMenuItem className="gap-2 cursor-pointer font-bold" onClick={handleExportData}>
                <Download className="w-4 h-4 text-muted-foreground" /> {isAr ? 'تحميل الإيصال' : 'Download Receipt'}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <DialogContent>
            <DialogHeader>
              <DialogTitle>{isAr ? 'تفاصيل المعاملة' : 'Transaction Details'}</DialogTitle>
            </DialogHeader>
            {selectedTx && (
              <div className="space-y-4 pt-4 text-sm">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-muted-foreground block mb-1">{isAr ? 'رقم المعاملة' : 'Tx No'}</span>
                    <span className="font-mono font-bold" dir="ltr">{selectedTx.id}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground block mb-1">{isAr ? 'التاريخ' : 'Date'}</span>
                    <span className="font-mono font-bold" dir="ltr">{selectedTx.date}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-muted-foreground block mb-1">{isAr ? 'النوع' : 'Type'}</span>
                    <Badge variant="outline">{selectedTx.type}</Badge>
                  </div>
                  <div className="col-span-2">
                    <span className="text-muted-foreground block mb-1">{isAr ? 'الجهة' : 'Party'}</span>
                    <span className="font-bold">{selectedTx.party}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-muted-foreground block mb-1">{isAr ? 'الوصف' : 'Description'}</span>
                    <span>{selectedTx.description}</span>
                  </div>
                  <div className="col-span-2 mt-2 pt-4 border-t border-border">
                    <span className="text-muted-foreground block mb-1">{isAr ? 'المبلغ الإجمالي' : 'Total Amount'}</span>
                    <span className={`text-2xl font-mono font-bold ${selectedTx.isPositive ? 'text-success' : 'text-danger'}`} dir="ltr">
                      {selectedTx.isPositive ? '' : '-'}{Math.abs(selectedTx.amount).toLocaleString()} {isAr ? 'ج.م' : 'EGP'}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </DialogContent>
        </Dialog>
      )
    }
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            {isAr ? 'دفتر المعاملات المالية' : 'Financial Transactions Ledger'}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {isAr ? 'إدارة ومراقبة كافة الحركات المالية والمحاسبية للنظام' : 'Manage and monitor all financial and accounting movements'}
          </p>
        </div>
        <Button 
          className="gap-2 font-bold h-11 px-6 shadow hover:bg-accent-hover transition-colors"
          onClick={handleExportData}
        >
          <FileOutput className="w-5 h-5" />
          {isAr ? 'تصدير البيانات' : 'Export Data'}
        </Button>
      </div>

      <Card className="border-border shadow-sm">
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div className="space-y-2">
              <label className="text-sm font-bold text-foreground">{isAr ? 'النطاق الزمني' : 'Time Range'}</label>
              <select className="flex h-11 w-full rounded-md border border-border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50">
                <option>{isAr ? 'آخر 30 يوم' : 'Last 30 days'}</option>
                <option>{isAr ? 'هذا الشهر' : 'This Month'}</option>
                <option>{isAr ? 'هذا العام' : 'This Year'}</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-foreground">{isAr ? 'نوع المعاملة' : 'Transaction Type'}</label>
              <select className="flex h-11 w-full rounded-md border border-border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50">
                <option>{isAr ? 'الكل' : 'All'}</option>
                <option>{isAr ? 'إيرادات' : 'Income'}</option>
                <option>{isAr ? 'مصروفات' : 'Expenses'}</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-bold text-foreground">{isAr ? 'الحالة' : 'Status'}</label>
              <select className="flex h-11 w-full rounded-md border border-border bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50">
                <option>{isAr ? 'الكل' : 'All'}</option>
                <option>{isAr ? 'مكتمل' : 'Completed'}</option>
                <option>{isAr ? 'معلق' : 'Pending'}</option>
              </select>
            </div>
            <Button 
              variant="outline" 
              className="h-11 gap-2 font-bold border-foreground text-foreground hover:bg-muted"
              onClick={() => toast.success(isAr ? 'تم تطبيق التصفية بنجاح' : 'Filters applied successfully')}
            >
              <Filter className="w-4 h-4" />
              {isAr ? 'تطبيق التصفية' : 'Apply Filter'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border shadow-sm overflow-hidden">
        <div className="p-2">
          <DataTable 
            columns={columns} 
            data={mockTransactions} 
            searchable={false}
          />
        </div>
      </Card>
    </div>
  );
}
