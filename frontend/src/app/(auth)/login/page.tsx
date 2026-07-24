'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useAppStore } from '@/store/use-app-store';
import { Shield, User, Lock, Eye, LogIn, Globe } from 'lucide-react';
import Link from 'next/link';
import { Input } from '@/components/ui/input';

const loginSchema = z.object({
  identifier: z.string().min(3, { message: 'الرجاء إدخال البريد الإلكتروني أو رقم الهاتف' }),
  password: z.string().min(6, { message: 'كلمة المرور يجب أن تكون 6 أحرف على الأقل' }),
  remember: z.boolean().optional(),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const router = useRouter();
  const { language, setLanguage, setUser } = useAppStore();
  const [isLoading, setIsLoading] = useState(false);

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      identifier: '',
      password: '',
      remember: false,
    },
  });

  const onSubmit = async (data: LoginFormValues) => {
    setIsLoading(true);
    // Simulate API call
    setTimeout(() => {
      setUser({
        id: '1',
        name: 'أحمد منصور',
        email: data.identifier,
        role: 'admin',
      });
      router.push('/financial-core');
    }, 1000);
  };

  const toggleLanguage = () => {
    const newLang = language === 'ar' ? 'en' : 'ar';
    setLanguage(newLang);
    document.documentElement.lang = newLang;
    document.documentElement.dir = newLang === 'ar' ? 'rtl' : 'ltr';
  };

  const isAr = language === 'ar';

  return (
    <div className="min-h-screen bg-paper flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative">
      <div className="absolute top-6 end-6">
        <button 
          onClick={toggleLanguage}
          className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-border bg-card text-sm font-medium hover:bg-muted transition-colors shadow-sm"
        >
          <span>{isAr ? 'English' : 'عربي'}</span>
          <Globe className="w-4 h-4" />
        </button>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-card py-10 px-6 sm:px-10 border border-border rounded-xl shadow-lg relative z-10">
          
          <div className="flex flex-col items-center mb-8">
            <div className="w-16 h-16 rounded-xl bg-sidebar flex items-center justify-center mb-4 shadow-sm">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <h2 className="text-center text-2xl font-extrabold text-foreground tracking-tight">
              Trust Core
            </h2>
            <p className="mt-2 text-center text-sm text-muted-foreground">
              {isAr ? 'نظام تخطيط موارد المؤسسات المتقدم' : 'Advanced Enterprise Resource Planning System'}
            </p>
          </div>

          <form className="space-y-6" onSubmit={form.handleSubmit(onSubmit)}>
            <div className="space-y-1">
              <label className="block text-sm font-semibold text-foreground">
                {isAr ? 'البريد الإلكتروني أو رقم الهاتف' : 'Email or Phone Number'}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 end-0 pe-3 flex items-center pointer-events-none">
                  <User className="h-5 w-5 text-muted-foreground" />
                </div>
                <Input
                  {...form.register('identifier')}
                  className="block w-full rounded-md border-border bg-background pe-10 ps-3 h-11 focus-visible:ring-1 focus-visible:ring-primary shadow-sm"
                  placeholder={isAr ? 'أدخل بريدك الإلكتروني' : 'Enter your email'}
                  dir="rtl"
                />
              </div>
              {form.formState.errors.identifier && (
                <p className="mt-1 text-sm text-destructive">{form.formState.errors.identifier.message}</p>
              )}
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <label className="block text-sm font-semibold text-foreground">
                  {isAr ? 'كلمة المرور' : 'Password'}
                </label>
                <Link href="/forgot-password" className="text-sm font-medium text-primary hover:text-primary/90 transition-colors">
                  {isAr ? 'نسيت كلمة المرور؟' : 'Forgot Password?'}
                </Link>
              </div>
              <div className="relative">
                <div className="absolute inset-y-0 end-0 pe-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-muted-foreground" />
                </div>
                <Input
                  type="password"
                  {...form.register('password')}
                  className="block w-full rounded-md border-border bg-background pe-10 ps-10 h-11 focus-visible:ring-1 focus-visible:ring-primary shadow-sm"
                  placeholder="••••••••"
                  dir="ltr"
                />
                <button type="button" className="absolute inset-y-0 start-0 ps-3 flex items-center text-muted-foreground hover:text-foreground">
                  <Eye className="h-5 w-5" />
                </button>
              </div>
              {form.formState.errors.password && (
                <p className="mt-1 text-sm text-destructive">{form.formState.errors.password.message}</p>
              )}
            </div>

            <div className="flex items-center justify-end gap-2">
              <label htmlFor="remember" className="text-sm text-muted-foreground cursor-pointer">
                {isAr ? 'تذكرني على هذا الجهاز' : 'Remember me on this device'}
              </label>
              <input
                id="remember"
                type="checkbox"
                {...form.register('remember')}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary bg-background"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="group relative flex w-full justify-center items-center gap-2 rounded-md border border-transparent bg-primary px-4 py-3 text-base font-bold text-primary-foreground shadow hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 disabled:opacity-70 transition-colors"
            >
              {isLoading 
                ? (isAr ? 'جاري التحميل...' : 'Loading...') 
                : (isAr ? 'تسجيل الدخول' : 'Log In')}
              {!isLoading && <LogIn className="w-5 h-5 rtl:rotate-180" />}
            </button>
          </form>
        </div>

        <div className="mt-8 text-center flex flex-col gap-3">
          <p className="text-xs text-muted-foreground">
            {isAr ? '© 2024 Trust Core ERP. جميع الحقوق محفوظة.' : '© 2024 Trust Core ERP. All rights reserved.'}
          </p>
          <div className="flex items-center justify-center gap-6 text-xs text-muted-foreground font-medium">
            <Link href="/privacy" className="hover:text-foreground transition-colors">{isAr ? 'سياسة الخصوصية' : 'Privacy Policy'}</Link>
            <Link href="/terms" className="hover:text-foreground transition-colors">{isAr ? 'الشروط والأحكام' : 'Terms & Conditions'}</Link>
            <Link href="/support" className="hover:text-foreground transition-colors">{isAr ? 'الدعم الفني' : 'Technical Support'}</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
