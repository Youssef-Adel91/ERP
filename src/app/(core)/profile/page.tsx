'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { UserCircle, Camera, Lock, Mail, Phone, User as UserIcon, Briefcase } from 'lucide-react';

const profileSchema = z.object({
  name: z.string().min(2, { message: 'الاسم يجب أن يكون أكثر من حرفين' }),
  email: z.string().email({ message: 'بريد إلكتروني غير صالح' }),
  phone: z.string().min(8, { message: 'رقم الهاتف قصير جداً' }),
});

const passwordSchema = z.object({
  currentPassword: z.string().min(6, { message: 'كلمة المرور الحالية مطلوبة' }),
  newPassword: z.string().min(6, { message: 'كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل' }),
  confirmPassword: z.string()
}).refine((data) => data.newPassword === data.confirmPassword, {
  message: "كلمات المرور لا تتطابق",
  path: ["confirmPassword"],
});

type ProfileFormValues = z.infer<typeof profileSchema>;
type PasswordFormValues = z.infer<typeof passwordSchema>;

export default function ProfilePage() {
  const { language, user, setUser } = useAppStore();
  const isAr = language === 'ar';

  const [avatarPreview, setAvatarPreview] = useState<string>(user?.avatar || "https://ui-avatars.com/api/?name=Ahmed+Mansour&background=random");

  const {
    register: registerProfile,
    handleSubmit: handleProfileSubmit,
    formState: { errors: profileErrors, isSubmitting: isProfileSubmitting }
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      name: user?.name || '',
      email: user?.email || '',
      phone: user?.phone || '',
    }
  });

  const {
    register: registerPassword,
    handleSubmit: handlePasswordSubmit,
    formState: { errors: passwordErrors, isSubmitting: isPasswordSubmitting },
    reset: resetPassword
  } = useForm<PasswordFormValues>({
    resolver: zodResolver(passwordSchema)
  });

  const onProfileSubmit = (data: ProfileFormValues) => {
    if (user) {
      setUser({
        ...user,
        name: data.name,
        email: data.email,
        phone: data.phone,
        avatar: avatarPreview
      });
      toast.success(isAr ? 'تم تحديث الملف الشخصي بنجاح' : 'Profile updated successfully');
    }
  };

  const onPasswordSubmit = (data: PasswordFormValues) => {
    toast.success(isAr ? 'تم تغيير كلمة المرور بنجاح' : 'Password changed successfully');
    resetPassword();
  };

  const handleAvatarUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setAvatarPreview(reader.result as string);
        toast.info(isAr ? 'تم تغيير الصورة، يرجى حفظ التغييرات' : 'Avatar changed, please save changes');
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto pb-24">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground flex items-center gap-3">
            <UserCircle className="w-8 h-8 text-primary" />
            {isAr ? 'الملف الشخصي' : 'Profile'}
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            {isAr ? 'إدارة معلومات حسابك الشخصي وإعدادات الأمان' : 'Manage your personal account information and security settings'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left Column: Avatar & Quick Info */}
        <div className="md:col-span-1 space-y-6">
          <Card className="border-border shadow-sm">
            <CardContent className="p-6 flex flex-col items-center text-center">
              <div className="relative group mb-4">
                <div className="w-32 h-32 rounded-full overflow-hidden border-4 border-muted relative bg-muted">
                  <img src={avatarPreview} alt="Profile" className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
                    <Camera className="w-8 h-8 text-white" />
                  </div>
                </div>
                <input 
                  type="file" 
                  accept="image/*" 
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" 
                  onChange={handleAvatarUpload}
                />
              </div>
              <h2 className="text-xl font-bold text-foreground mb-1">{user?.name || 'أحمد منصور'}</h2>
              <p className="text-sm text-primary font-medium mb-3">{user?.role || 'مدير الحسابات'}</p>
              <div className="w-full h-px bg-border my-4"></div>
              <div className="w-full space-y-3 text-start">
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Mail className="w-4 h-4 text-primary" />
                  <span className="truncate" dir="ltr">{user?.email || 'ahmed@trustcore.com'}</span>
                </div>
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Phone className="w-4 h-4 text-primary" />
                  <span dir="ltr">{user?.phone || '+20 10 1234 5678'}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Forms */}
        <div className="md:col-span-2 space-y-6">
          <Card className="border-border shadow-sm">
            <CardHeader className="border-b border-border/50 pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <UserIcon className="w-5 h-5 text-primary" />
                {isAr ? 'المعلومات الأساسية' : 'Basic Information'}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <form onSubmit={handleProfileSubmit(onProfileSubmit)} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'الاسم الكامل' : 'Full Name'}</label>
                    <Input {...registerProfile('name')} className={profileErrors.name ? 'border-danger focus-visible:ring-danger' : ''} />
                    {profileErrors.name && <p className="text-xs text-danger">{profileErrors.name.message}</p>}
                  </div>
                  
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'المسمى الوظيفي' : 'Job Title'}</label>
                    <div className="relative">
                      <Briefcase className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                      <Input value={user?.role || ''} disabled className="ps-9 bg-muted/50 cursor-not-allowed text-muted-foreground" />
                    </div>
                    <p className="text-[10px] text-muted-foreground">{isAr ? 'المنصب يدار بواسطة مسؤول النظام' : 'Role is managed by system administrator'}</p>
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'البريد الإلكتروني' : 'Email Address'}</label>
                    <Input dir="ltr" {...registerProfile('email')} className={`text-start ${profileErrors.email ? 'border-danger focus-visible:ring-danger' : ''}`} />
                    {profileErrors.email && <p className="text-xs text-danger text-end">{profileErrors.email.message}</p>}
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'رقم الهاتف' : 'Phone Number'}</label>
                    <Input dir="ltr" {...registerProfile('phone')} className={`text-start ${profileErrors.phone ? 'border-danger focus-visible:ring-danger' : ''}`} />
                    {profileErrors.phone && <p className="text-xs text-danger text-end">{profileErrors.phone.message}</p>}
                  </div>
                </div>

                <div className="pt-4 flex justify-end">
                  <Button type="submit" disabled={isProfileSubmitting} className="font-bold px-8 shadow-sm">
                    {isAr ? 'حفظ التغييرات' : 'Save Changes'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          <Card className="border-border shadow-sm">
            <CardHeader className="border-b border-border/50 pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <Lock className="w-5 h-5 text-warning-foreground" />
                {isAr ? 'تغيير كلمة المرور' : 'Change Password'}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              <form onSubmit={handlePasswordSubmit(onPasswordSubmit)} className="space-y-4">
                <div className="space-y-2 max-w-md">
                  <label className="text-sm font-bold">{isAr ? 'كلمة المرور الحالية' : 'Current Password'}</label>
                  <Input type="password" {...registerPassword('currentPassword')} className={passwordErrors.currentPassword ? 'border-danger focus-visible:ring-danger' : ''} />
                  {passwordErrors.currentPassword && <p className="text-xs text-danger">{passwordErrors.currentPassword.message}</p>}
                </div>
                <div className="w-full h-px bg-border/50 my-4 max-w-md"></div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'كلمة المرور الجديدة' : 'New Password'}</label>
                    <Input type="password" {...registerPassword('newPassword')} className={passwordErrors.newPassword ? 'border-danger focus-visible:ring-danger' : ''} />
                    {passwordErrors.newPassword && <p className="text-xs text-danger">{passwordErrors.newPassword.message}</p>}
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-bold">{isAr ? 'تأكيد كلمة المرور' : 'Confirm Password'}</label>
                    <Input type="password" {...registerPassword('confirmPassword')} className={passwordErrors.confirmPassword ? 'border-danger focus-visible:ring-danger' : ''} />
                    {passwordErrors.confirmPassword && <p className="text-xs text-danger">{passwordErrors.confirmPassword.message}</p>}
                  </div>
                </div>

                <div className="pt-4 flex justify-end max-w-2xl">
                  <Button type="submit" variant="outline" disabled={isPasswordSubmitting} className="font-bold px-8 border-warning text-warning-foreground hover:bg-warning/10 shadow-sm">
                    {isAr ? 'تحديث كلمة المرور' : 'Update Password'}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
