'use client';

import { useState } from 'react';
import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { 
  Building2, 
  Users, 
  ShieldAlert,
  MoreVertical,
  ImageIcon,
  Plus
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter
} from "@/components/ui/dialog";

const initialUsers = [
  { id: 1, name: 'سارة أحمد', email: 'sara.a@trustcore.com', initials: 'SA', role: 'محاسب أول', roleBg: 'bg-success/20 text-success', status: 'نشط', statusDot: 'bg-success', active: true },
  { id: 2, name: 'محمد حسن', email: 'm.hassan@trustcore.com', initials: 'MH', role: 'مدير مشتريات', roleBg: 'bg-warning/20 text-warning-foreground', status: 'قيد الانتظار', statusDot: 'bg-warning', active: false },
  { id: 3, name: 'خالد فيصل', email: 'k.faisal@trustcore.com', initials: 'KF', role: 'مدقق مالي', roleBg: 'bg-danger/20 text-danger', status: 'غير نشط', statusDot: 'bg-danger', active: false },
];

export default function SettingsPage() {
  const { language } = useAppStore();
  const isAr = language === 'ar';

  const [users, setUsers] = useState(initialUsers);
  const [isAddUserOpen, setIsAddUserOpen] = useState(false);
  const [newUserName, setNewUserName] = useState('');
  const [newUserEmail, setNewUserEmail] = useState('');
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [isLogsOpen, setIsLogsOpen] = useState(false);
  const [isSecurityOpen, setIsSecurityOpen] = useState(false);

  const handleExportData = () => {
    const csvContent = "data:text/csv;charset=utf-8,ID,Name,Email,Role,Status\n" + 
      users.map(u => `${u.id},${u.name},${u.email},${u.role},${u.status}`).join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "users_export.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success(isAr ? 'تم تصدير البيانات بنجاح' : 'Data exported successfully');
  };

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => setLogoPreview(reader.result as string);
      reader.readAsDataURL(file);
      toast.success(isAr ? 'تم تحديث الشعار مؤقتاً' : 'Logo updated temporarily');
    }
  };

  const toggleUserActive = (id: number) => {
    setUsers(users.map(u => u.id === id ? { ...u, active: !u.active, status: !u.active ? 'نشط' : 'غير نشط', statusDot: !u.active ? 'bg-success' : 'bg-danger' } : u));
    toast.success(isAr ? 'تم تحديث حالة المستخدم بنجاح' : 'User status updated successfully');
  };

  const handleAddUser = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUserName || !newUserEmail) return;

    const initials = newUserName.substring(0, 2).toUpperCase();
    const newUser = {
      id: Date.now(),
      name: newUserName,
      email: newUserEmail,
      initials,
      role: 'مستخدم جديد',
      roleBg: 'bg-muted text-muted-foreground',
      status: 'نشط',
      statusDot: 'bg-success',
      active: true
    };

    setUsers([...users, newUser]);
    setNewUserName('');
    setNewUserEmail('');
    setIsAddUserOpen(false);
    toast.success(isAr ? 'تمت إضافة المستخدم بنجاح' : 'User added successfully');
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground">
            {isAr ? 'إعدادات النظام' : 'System Settings'}
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            {isAr ? 'إدارة معلومات الشركة والصلاحيات والمستخدمين' : 'Manage company information, roles, and users'}
          </p>
        </div>
        <div className="flex gap-3">
          <Button 
            variant="outline" 
            className="gap-2 h-11 border-border shadow-sm font-bold text-foreground hover:bg-muted transition-colors"
            onClick={handleExportData}
          >
            {isAr ? 'تصدير البيانات' : 'Export Data'}
          </Button>
          <Button 
            className="h-11 px-8 font-bold shadow hover:bg-accent-hover transition-colors"
            onClick={() => toast.success(isAr ? 'تم حفظ التغييرات بنجاح' : 'Changes saved successfully')}
          >
            {isAr ? 'حفظ التغييرات' : 'Save Changes'}
          </Button>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        
        {/* Right side (Main Form in RTL) */}
        <div className="w-full lg:w-[400px] flex-shrink-0 lg:order-1 order-2">
          <Card className="border-border shadow-sm h-full">
            <div className="p-5 border-b border-border/50 flex items-center gap-2 text-primary font-bold">
              <Building2 className="w-5 h-5" />
              <h2>{isAr ? 'ملف الشركة' : 'Company Profile'}</h2>
            </div>
            <CardContent className="p-6 space-y-6">
              <label 
                className="flex flex-col items-center justify-center p-8 border-2 border-dashed border-border rounded-xl bg-muted/10 hover:bg-muted/20 transition-colors cursor-pointer text-center relative overflow-hidden"
              >
                <input type="file" className="hidden" accept="image/*" onChange={handleLogoUpload} />
                {logoPreview ? (
                  <img src={logoPreview} alt="Logo" className="absolute inset-0 w-full h-full object-contain p-4" />
                ) : (
                  <>
                    <ImageIcon className="w-12 h-12 text-muted-foreground mb-3 opacity-50" />
                    <p className="text-sm font-bold text-muted-foreground">{isAr ? 'رفع شعار الشركة (بحد أقصى 5 ميجابايت)' : 'Upload company logo (Max 5MB)'}</p>
                  </>
                )}
              </label>

              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-bold text-foreground">{isAr ? 'اسم المؤسسة' : 'Enterprise Name'}</label>
                  <Input defaultValue={isAr ? "تراست كور للحلول التقنية" : "Trust Core Tech Solutions"} className="h-11" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-bold text-foreground">{isAr ? 'الرقم الضريبي (VAT)' : 'Tax ID (VAT)'}</label>
                  <Input defaultValue="300012345600003" dir="ltr" className="h-11 text-start" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-bold text-foreground">{isAr ? 'عنوان المقر الرئيسي' : 'HQ Address'}</label>
                  <textarea 
                    className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
                    defaultValue={isAr ? "الرياض، حي العليا، برج المملكة، الطابق 12، مكتب 1204" : "Riyadh, Olaya District, Kingdom Tower, Floor 12, Office 1204"}
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Left side (Users in RTL) */}
        <div className="flex-1 lg:order-2 order-1">
          <Card className="border-border shadow-sm h-full">
            <div className="p-5 border-b border-border/50 flex items-center justify-between">
              <div className="flex items-center gap-2 text-primary font-bold">
                <Users className="w-5 h-5" />
                <h2>{isAr ? 'المستخدمون والصلاحيات' : 'Users and Roles'}</h2>
              </div>
              <Dialog open={isAddUserOpen} onOpenChange={setIsAddUserOpen}>
                <DialogTrigger render={
                  <Button className="gap-2 h-9 text-xs shadow bg-sidebar text-sidebar-primary-foreground hover:bg-sidebar/90 font-bold">
                    <Plus className="w-4 h-4" />
                    {isAr ? 'إضافة مستخدم' : 'Add User'}
                  </Button>
                } />
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{isAr ? 'إضافة مستخدم جديد' : 'Add New User'}</DialogTitle>
                  </DialogHeader>
                  <form onSubmit={handleAddUser} className="space-y-4 pt-4">
                    <div className="space-y-2">
                      <label className="text-sm font-bold">{isAr ? 'الاسم الكامل' : 'Full Name'}</label>
                      <Input 
                        value={newUserName} 
                        onChange={e => setNewUserName(e.target.value)} 
                        placeholder={isAr ? 'أدخل اسم المستخدم' : 'Enter user name'}
                        required
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="text-sm font-bold">{isAr ? 'البريد الإلكتروني' : 'Email'}</label>
                      <Input 
                        type="email"
                        value={newUserEmail} 
                        onChange={e => setNewUserEmail(e.target.value)} 
                        placeholder={isAr ? 'أدخل البريد الإلكتروني' : 'Enter email address'}
                        dir="ltr"
                        required
                      />
                    </div>
                    <DialogFooter>
                      <Button type="submit" className="w-full font-bold">{isAr ? 'حفظ وإضافة' : 'Save & Add'}</Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
            <div className="p-0">
              <table className="w-full text-start">
                <thead className="bg-muted/30">
                  <tr className="border-b border-border/50">
                    <th className="p-4 py-5 text-start text-sm font-bold text-muted-foreground">{isAr ? 'الموظف' : 'Employee'}</th>
                    <th className="p-4 py-5 text-start text-sm font-bold text-muted-foreground">{isAr ? 'الدور الوظيفي' : 'Role'}</th>
                    <th className="p-4 py-5 text-start text-sm font-bold text-muted-foreground">{isAr ? 'الحالة' : 'Status'}</th>
                    <th className="p-4 py-5 text-center text-sm font-bold text-muted-foreground">{isAr ? 'صلاحية الوصول' : 'Access Rights'}</th>
                    <th className="p-4 py-5"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {users.map((user) => (
                    <tr key={user.id} className="hover:bg-muted/10 transition-colors">
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm bg-primary/20 text-primary`}>
                            {user.initials}
                          </div>
                          <div>
                            <p className="font-bold text-foreground">{user.name}</p>
                            <p className="text-xs text-muted-foreground font-mono" dir="ltr">{user.email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <Badge variant="secondary" className={`border-transparent rounded-full px-3 py-1 text-xs font-bold ${user.roleBg} shadow-none`}>
                          {user.role}
                        </Badge>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${user.statusDot}`}></span>
                          <span className="text-sm font-medium">{user.status}</span>
                        </div>
                      </td>
                      <td className="p-4 text-center">
                        <Switch 
                          checked={user.active} 
                          onCheckedChange={() => toggleUserActive(user.id)}
                        />
                      </td>
                      <td className="p-4 text-center">
                        <button className="text-muted-foreground hover:text-foreground">
                          <MoreVertical className="w-5 h-5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="p-4 border-t border-border/50 text-sm text-muted-foreground">
                {isAr ? `عرض 1-${users.length} من أصل ${users.length} مستخدم` : `Showing 1-${users.length} of ${users.length} users`}
              </div>
            </div>
          </Card>
        </div>

      </div>

      <div className="bg-sidebar rounded-xl p-6 flex flex-col md:flex-row items-center justify-between gap-6 shadow-md overflow-hidden relative">
        <div className="relative z-10 flex items-center gap-4">
          <div className="w-14 h-14 bg-accent rounded-xl flex items-center justify-center flex-shrink-0">
            <ShieldAlert className="w-7 h-7 text-accent-foreground" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white mb-1">{isAr ? 'تأمين الوصول وحماية البيانات' : 'Access Security & Data Protection'}</h2>
            <p className="text-sidebar-subtitle text-sm">
              {isAr ? 'تم تفعيل بروتوكول التشفير المتقدم ونظام المصادقة الثنائية لجميع المستخدمين ذوي الصلاحيات الحساسة.' : 'Advanced encryption protocol and 2FA enabled for all users with sensitive access rights.'}
            </p>
          </div>
        </div>
        <div className="relative z-10 flex gap-3 flex-shrink-0">
          <Dialog open={isLogsOpen} onOpenChange={setIsLogsOpen}>
            <DialogTrigger render={
              <Button variant="outline" className="h-11 px-6 font-bold bg-transparent text-white border-sidebar-text hover:bg-sidebar-accent hover:text-white">
                {isAr ? 'عرض السجلات' : 'View Logs'}
              </Button>
            } />
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>{isAr ? 'سجلات النظام (آخر 24 ساعة)' : 'System Logs (Last 24h)'}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-4 max-h-80 overflow-y-auto">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="flex justify-between items-center p-3 bg-muted/30 rounded-lg border border-border/50">
                    <div>
                      <p className="font-bold text-sm text-foreground">{isAr ? `تحديث حالة المستخدم #${i}` : `User status updated #${i}`}</p>
                      <p className="text-xs text-muted-foreground font-mono">ID: {Math.random().toString(36).substring(7).toUpperCase()}</p>
                    </div>
                    <span className="text-xs text-muted-foreground">10:45 AM</span>
                  </div>
                ))}
              </div>
            </DialogContent>
          </Dialog>

          <Dialog open={isSecurityOpen} onOpenChange={setIsSecurityOpen}>
            <DialogTrigger render={
              <Button variant="outline" className="h-11 px-6 font-bold bg-transparent text-white border-sidebar-text hover:bg-sidebar-accent hover:text-white">
                {isAr ? 'إعدادات الأمان' : 'Security Settings'}
              </Button>
            } />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{isAr ? 'إعدادات الأمان المتقدمة' : 'Advanced Security Settings'}</DialogTitle>
              </DialogHeader>
              <div className="space-y-6 pt-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-bold text-sm">{isAr ? 'المصادقة الثنائية (2FA)' : 'Two-Factor Authentication'}</h4>
                    <p className="text-xs text-muted-foreground">{isAr ? 'تطبيق إلزامي على جميع المدراء' : 'Mandatory for all admins'}</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="font-bold text-sm">{isAr ? 'صلاحية الجلسة' : 'Session Timeout'}</h4>
                    <p className="text-xs text-muted-foreground">{isAr ? 'تسجيل الخروج التلقائي بعد 30 دقيقة' : 'Auto logout after 30 mins'}</p>
                  </div>
                  <Switch defaultChecked />
                </div>
                <Button className="w-full font-bold h-11" onClick={() => setIsSecurityOpen(false)}>
                  {isAr ? 'حفظ التغييرات' : 'Save Changes'}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </div>
  );
}
