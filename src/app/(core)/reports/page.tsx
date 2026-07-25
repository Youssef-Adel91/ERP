'use client';

import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { 
  FileText, 
  Download, 
  Filter, 
  TrendingUp, 
  PieChart, 
  BarChart3, 
  CalendarDays,
  Plus
} from 'lucide-react';
import { useState } from 'react';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const mockReports = [
  { id: 1, title: 'الميزانية العمومية', titleEn: 'Balance Sheet', type: 'مالي', typeEn: 'Financial', date: 'تلقائي (يومي)', dateEn: 'Auto (Daily)', icon: PieChart, color: 'text-primary', bg: 'bg-primary/20' },
  { id: 2, title: 'قائمة الدخل', titleEn: 'Income Statement', type: 'مالي', typeEn: 'Financial', date: 'الربع الأول 2024', dateEn: 'Q1 2024', icon: TrendingUp, color: 'text-success', bg: 'bg-success/20' },
  { id: 3, title: 'التدفقات النقدية', titleEn: 'Cash Flows', type: 'مالي', typeEn: 'Financial', date: 'مايو 2024', dateEn: 'May 2024', icon: BarChart3, color: 'text-warning-foreground', bg: 'bg-warning/20' },
  { id: 4, title: 'أعمار الديون', titleEn: 'Aging of Debts', type: 'عملاء', typeEn: 'Clients', date: 'تلقائي (أسبوعي)', dateEn: 'Auto (Weekly)', icon: Filter, color: 'text-danger', bg: 'bg-danger/20' },
  { id: 5, title: 'كشف حساب ضريبي', titleEn: 'Tax Statement', type: 'ضريبي', typeEn: 'Tax', date: 'تلقائي (شهري)', dateEn: 'Auto (Monthly)', icon: FileText, color: 'text-sidebar-text', bg: 'bg-sidebar' },
];

export default function ReportsPage() {
  const language = useAppStore((state) => state.language);
  const isAr = language === 'ar';

  const [reportsList, setReportsList] = useState(mockReports);
  const [isDateOpen, setIsDateOpen] = useState(false);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [previewReport, setPreviewReport] = useState<typeof mockReports[0] | null>(null);
  
  const [newTitle, setNewTitle] = useState('');
  const [newType, setNewType] = useState('مالي');

  const handleDownloadReport = (title: string) => {
    const link = document.createElement("a");
    link.href = "data:application/pdf;base64,JVBERi0xLjQKJ...";
    link.download = `Report_${title}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success(isAr ? `تم تحميل تقرير ${title} بنجاح` : `${title} downloaded successfully`);
  };

  const handleAddReport = () => {
    if(!newTitle) return;
    setReportsList([...reportsList, {
      id: Date.now(),
      title: newTitle,
      titleEn: newTitle,
      type: newType,
      typeEn: newType,
      date: 'اليوم',
      dateEn: 'Today',
      icon: PieChart,
      color: 'text-primary',
      bg: 'bg-primary/20'
    }]);
    setIsAddOpen(false);
    setNewTitle('');
    toast.success(isAr ? 'تم إضافة التقرير المخصص بنجاح' : 'Custom report added successfully');
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground">
            {isAr ? 'مركز التقارير' : 'Reports Center'}
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            {isAr ? 'استعراض وتصدير كافة التقارير المالية والإدارية' : 'View and export all financial and administrative reports'}
          </p>
        </div>
        
        <div className="flex flex-col sm:flex-row items-center gap-4 bg-card border border-border p-2 rounded-xl shadow-sm">
          <div className="flex items-center gap-3 px-3">
            <CalendarDays className="w-5 h-5 text-muted-foreground" />
            <span className="text-sm font-bold">{isAr ? 'مايو 2024' : 'May 2024'}</span>
            <div className="w-px h-4 bg-border mx-3"></div>
            <span className="text-xs text-muted-foreground">{isAr ? 'الفترة الزمنية' : 'Time Period'}</span>
          </div>
          <div className="flex gap-3 mt-4 sm:mt-0">
            <Dialog open={isDateOpen} onOpenChange={setIsDateOpen}>
              <DialogTrigger render={
                <Button variant="outline" className="h-11 font-bold border-border shadow-sm text-foreground hover:bg-muted">
                  {isAr ? 'تغيير التاريخ' : 'Change Date'}
                </Button>
              } />
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{isAr ? 'تحديد الفترة الزمنية' : 'Select Time Period'}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 pt-4">
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'من تاريخ' : 'Start Date'}</label>
                    <Input type="date" />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'إلى تاريخ' : 'End Date'}</label>
                    <Input type="date" />
                  </div>
                  <Button className="w-full font-bold" onClick={() => {
                    setIsDateOpen(false);
                    toast.success(isAr ? 'تم تحديث فترة التقارير' : 'Report period updated');
                  }}>
                    {isAr ? 'تطبيق' : 'Apply'}
                  </Button>
                </div>
              </DialogContent>
            </Dialog>
            <Button 
              className="h-11 px-6 font-bold bg-sidebar text-sidebar-primary-foreground hover:bg-sidebar/90 shadow-sm"
              onClick={() => toast.success(isAr ? 'تم تحديث بيانات التقارير' : 'Report data refreshed')}
            >
              {isAr ? 'تحديث البيانات' : 'Update Data'}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {reportsList.map((report) => (
          <Card key={report.id} className="border-border shadow-sm hover:shadow-md transition-shadow group">
            <CardContent className="p-6">
              <div className="flex justify-between items-start mb-6">
                <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${report.bg}`}>
                  <report.icon className={`w-7 h-7 ${report.color}`} />
                </div>
                <Badge variant="secondary" className="bg-muted text-muted-foreground border-transparent shadow-none font-bold">
                  {isAr ? report.type : report.typeEn}
                </Badge>
              </div>
              
              <h3 className="font-bold text-foreground text-xl mb-2">{isAr ? report.title : report.titleEn}</h3>
              <p className="text-sm text-muted-foreground font-mono" dir="ltr">
                <span className="font-sans ms-1 text-xs">{isAr ? 'تحديث:' : 'Updated:'}</span> {isAr ? report.date : report.dateEn}
              </p>
              
              <div className="flex gap-2 mt-6 pt-4 border-t border-border/50">
                <Button 
                  variant="outline" 
                  size="icon" 
                  className="h-11 w-11 flex-shrink-0 border-primary text-primary hover:bg-primary hover:text-primary-foreground transition-colors"
                  onClick={() => handleDownloadReport(isAr ? report.title : report.titleEn)}
                >
                  <Download className="w-5 h-5" />
                </Button>
                <Dialog>
                  <DialogTrigger render={
                    <Button className="h-11 flex-1 font-bold shadow-sm" onClick={() => setPreviewReport(report)}>
                      {isAr ? 'عرض التقرير' : 'View Report'}
                    </Button>
                  } />
                  <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
                    <DialogHeader>
                      <DialogTitle className="flex items-center gap-2">
                        <report.icon className={`w-5 h-5 ${report.color}`} />
                        {isAr ? report.title : report.titleEn}
                      </DialogTitle>
                    </DialogHeader>
                    <div className="flex-1 overflow-auto p-4 bg-muted/10 border border-border mt-4 rounded-lg flex items-center justify-center">
                      <div className="text-center text-muted-foreground space-y-4">
                        <BarChart3 className="w-16 h-16 mx-auto opacity-20" />
                        <p className="font-bold text-lg">{isAr ? 'معاينة التقرير' : 'Report Preview'}</p>
                        <p className="text-sm">{isAr ? 'يتم عرض البيانات في هذه المساحة' : 'Data is displayed in this area'}</p>
                      </div>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>
            </CardContent>
          </Card>
        ))}

        <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
          <DialogTrigger render={
            <Card className="border-border border-dashed shadow-none bg-muted/10 hover:bg-muted/30 transition-colors cursor-pointer h-full min-h-[300px]">
              <CardContent className="p-6 flex flex-col items-center justify-center h-full text-center">
                <div className="w-16 h-16 rounded-xl bg-muted border border-border flex items-center justify-center mb-4 text-foreground shadow-sm">
                  <Plus className="w-8 h-8" />
                </div>
                <h3 className="font-bold text-foreground text-lg">{isAr ? 'إضافة تقرير مخصص' : 'Add Custom Report'}</h3>
              </CardContent>
            </Card>
          } />
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{isAr ? 'منشئ التقارير المخصصة' : 'Custom Report Builder'}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-4">
              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'اسم التقرير' : 'Report Name'}</label>
                <Input value={newTitle} onChange={e => setNewTitle(e.target.value)} placeholder={isAr ? 'أدخل اسم التقرير...' : 'Enter report name...'} />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-bold">{isAr ? 'نوع البيانات' : 'Data Type'}</label>
                <select 
                  className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={newType}
                  onChange={(e) => setNewType(e.target.value)}
                >
                  <option value={isAr ? 'مالي' : 'Financial'}>{isAr ? 'مالي' : 'Financial'}</option>
                  <option value={isAr ? 'ضريبي' : 'Tax'}>{isAr ? 'ضريبي' : 'Tax'}</option>
                  <option value={isAr ? 'عملاء' : 'Clients'}>{isAr ? 'عملاء' : 'Clients'}</option>
                </select>
              </div>
              <Button className="w-full font-bold" onClick={handleAddReport}>
                {isAr ? 'حفظ وإنشاء' : 'Save & Create'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
