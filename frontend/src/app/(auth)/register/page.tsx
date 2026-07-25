'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod/v4';
import Link from 'next/link';
import { Mail, Lock, Eye, EyeOff, ArrowLeft, Loader2, Building2, User } from 'lucide-react';
import { toast } from 'sonner';
import { useAppStore } from '@/store/use-app-store';
import { apiClient, saveSession } from '@/lib/api-client';

// ── Schema ────────────────────────────────────────────────────────────────────

const registerSchema = z.object({
  company_name: z.string().min(2, 'اسم الشركة/المؤسسة مطلوب (حرفين على الأقل)'),
  full_name: z.string().min(2, 'الاسم بالكامل مطلوب'),
  email: z.email('بريد إلكتروني غير صحيح'),
  password: z
    .string()
    .min(8, 'كلمة المرور يجب أن تكون 8 أحرف على الأقل')
    .regex(/\d/, 'يجب أن تحتوي على رقم واحد على الأقل')
    .regex(/[A-Z]/, 'يجب أن تحتوي على حرف كبير واحد على الأقل'),
});

type RegisterForm = z.infer<typeof registerSchema>;

// ── Backend response ──────────────────────────────────────────────────────────

interface RegisterResponse {
  tenant_id: string;
  tenant_name: string;
  schema_name: string;
  user_id: string;
  email: string;
  access_token: string;
  refresh_token: string;
  token_type: string;
  message: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function RegisterPage() {
  const router = useRouter();
  const { setUser } = useAppStore();
  const [showPw, setShowPw] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: { company_name: '', full_name: '', email: '', password: '' },
  });

  const onSubmit = async (data: RegisterForm) => {
    setIsLoading(true);
    try {
      // 1. Register tenant and user
      const response = await apiClient.post<RegisterResponse>('/auth/register', data);

      // 2. Persist full session
      saveSession(response.access_token, response.tenant_id);
      if (response.refresh_token) {
        localStorage.setItem('refresh_token', response.refresh_token);
      }

      // 3. Update Zustand Store with basic info from register response
      setUser({
        id: response.user_id,
        tenantId: response.tenant_id,
        name: data.full_name,
        email: response.email,
        role: 'OWNER',
        avatar: `https://ui-avatars.com/api/?name=${encodeURIComponent(data.full_name)}&background=FF9800&color=fff`,
      });

      toast.success('تم إنشاء حساب شركتك بنجاح!');
      router.push('/dashboard');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'حدث خطأ أثناء إنشاء الحساب.';
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-[420px] mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-[26px] font-bold text-[#040D1B] leading-tight mb-2">
          أنشئ مساحة عملك
        </h1>
        <p className="text-[#75777D] text-[14px]">
          ابدأ بإدارة مبيعاتك ومخزونك وحساباتك الآن.
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
        {/* Company Name */}
        <div>
          <label htmlFor="register-company" className="block text-[13px] font-semibold text-[#040D1B] mb-1.5">
            اسم الشركة / المؤسسة
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 end-0 pe-3.5 flex items-center pointer-events-none">
              <Building2 className="w-4 h-4 text-[#75777D]" />
            </div>
            <input
              id="register-company"
              type="text"
              placeholder="مثال: شركة النور للزجاج"
              {...register('company_name')}
              className={`w-full h-11 rounded-lg border bg-white pe-10 ps-4 text-[14px] text-[#040D1B] placeholder:text-[#BEC7DB] outline-none transition-all text-start
                focus:ring-2 focus:ring-[#FF9800]/40 focus:border-[#FF9800]
                ${errors.company_name ? 'border-[#BA1A1A] ring-2 ring-[#BA1A1A]/20' : 'border-[#C5C6CC]'}`}
            />
          </div>
          {errors.company_name && (
            <p className="mt-1 text-[12px] text-[#BA1A1A]">{errors.company_name.message}</p>
          )}
        </div>

        {/* Full Name */}
        <div>
          <label htmlFor="register-name" className="block text-[13px] font-semibold text-[#040D1B] mb-1.5">
            الاسم بالكامل
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 end-0 pe-3.5 flex items-center pointer-events-none">
              <User className="w-4 h-4 text-[#75777D]" />
            </div>
            <input
              id="register-name"
              type="text"
              placeholder="مثال: أحمد محمد"
              {...register('full_name')}
              className={`w-full h-11 rounded-lg border bg-white pe-10 ps-4 text-[14px] text-[#040D1B] placeholder:text-[#BEC7DB] outline-none transition-all text-start
                focus:ring-2 focus:ring-[#FF9800]/40 focus:border-[#FF9800]
                ${errors.full_name ? 'border-[#BA1A1A] ring-2 ring-[#BA1A1A]/20' : 'border-[#C5C6CC]'}`}
            />
          </div>
          {errors.full_name && (
            <p className="mt-1 text-[12px] text-[#BA1A1A]">{errors.full_name.message}</p>
          )}
        </div>

        {/* Email */}
        <div>
          <label htmlFor="register-email" className="block text-[13px] font-semibold text-[#040D1B] mb-1.5">
            البريد الإلكتروني
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 end-0 pe-3.5 flex items-center pointer-events-none">
              <Mail className="w-4 h-4 text-[#75777D]" />
            </div>
            <input
              id="register-email"
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              dir="ltr"
              {...register('email')}
              className={`w-full h-11 rounded-lg border bg-white pe-10 ps-4 text-[14px] text-[#040D1B] placeholder:text-[#BEC7DB] outline-none transition-all text-start
                focus:ring-2 focus:ring-[#FF9800]/40 focus:border-[#FF9800]
                ${errors.email ? 'border-[#BA1A1A] ring-2 ring-[#BA1A1A]/20' : 'border-[#C5C6CC]'}`}
            />
          </div>
          {errors.email && (
            <p className="mt-1 text-[12px] text-[#BA1A1A]">{errors.email.message}</p>
          )}
        </div>

        {/* Password */}
        <div>
          <label htmlFor="register-password" className="block text-[13px] font-semibold text-[#040D1B] mb-1.5">
            كلمة المرور
          </label>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute inset-y-0 start-0 ps-3.5 flex items-center text-[#75777D] hover:text-[#040D1B] transition-colors"
              tabIndex={-1}
            >
              {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
            <div className="absolute inset-y-0 end-0 pe-3.5 flex items-center pointer-events-none">
              <Lock className="w-4 h-4 text-[#75777D]" />
            </div>
            <input
              id="register-password"
              type={showPw ? 'text' : 'password'}
              autoComplete="new-password"
              placeholder="••••••••"
              dir="ltr"
              {...register('password')}
              className={`w-full h-11 rounded-lg border bg-white pe-10 ps-10 text-[14px] text-[#040D1B] placeholder:text-[#BEC7DB] outline-none transition-all
                focus:ring-2 focus:ring-[#FF9800]/40 focus:border-[#FF9800]
                ${errors.password ? 'border-[#BA1A1A] ring-2 ring-[#BA1A1A]/20' : 'border-[#C5C6CC]'}`}
            />
          </div>
          {errors.password && (
            <p className="mt-1 text-[12px] text-[#BA1A1A]">{errors.password.message}</p>
          )}
          <p className="text-[11px] text-[#75777D] mt-1.5">يجب أن تحتوي على 8 أحرف ورقم وحرف كبير.</p>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={isLoading}
          className="group relative flex w-full justify-center items-center gap-2.5 h-12 rounded-xl bg-[#FF9800] hover:bg-[#E6890A] text-white font-bold text-[15px] transition-all duration-200 shadow-lg shadow-[#FF9800]/25 hover:shadow-[#FF9800]/40 hover:scale-[1.01] active:scale-[0.98] disabled:opacity-70 disabled:cursor-not-allowed disabled:scale-100 mt-6"
        >
          {isLoading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              جاري إنشاء الحساب…
            </>
          ) : (
            <>
              إنشاء حساب جديد
              <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
            </>
          )}
        </button>

        {/* Divider */}
        <div className="relative flex items-center gap-3 py-3">
          <div className="flex-1 h-px bg-[#E4E2E3]" />
          <span className="text-[12px] text-[#75777D]">لديك حساب بالفعل؟</span>
          <div className="flex-1 h-px bg-[#E4E2E3]" />
        </div>

        <Link
          href="/login"
          className="flex w-full justify-center items-center h-11 rounded-xl border border-[#C5C6CC] hover:border-[#FF9800]/50 text-[#040D1B] hover:text-[#FF9800] font-semibold text-[14px] transition-all duration-200 hover:bg-[#FFF3E0]"
        >
          تسجيل الدخول
        </Link>
      </form>
    </div>
  );
}
