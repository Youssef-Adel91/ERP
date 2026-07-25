'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod/v4';
import Link from 'next/link';
import { Mail, Lock, Eye, EyeOff, ArrowLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAppStore } from '@/store/use-app-store';
import { apiClient, saveSession } from '@/lib/api-client';

// ── Schema ────────────────────────────────────────────────────────────────────

const loginSchema = z.object({
  email: z.email('بريد إلكتروني غير صحيح'),
  password: z.string().min(1, 'كلمة المرور مطلوبة'),
  remember: z.boolean().optional(),
});

type LoginForm = z.infer<typeof loginSchema>;

// ── Backend response ──────────────────────────────────────────────────────────

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAppStore();
  const [showPw, setShowPw] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '', remember: false },
  });

  const onSubmit = async (data: LoginForm) => {
    setIsLoading(true);
    try {
      // 1. Exchange credentials for tokens
      const tokens = await apiClient.post<TokenResponse>('/auth/login', {
        email: data.email,
        password: data.password,
      });

      // 2. Fetch the authenticated user profile to get tenant_id
      //    We save a temporary token first so getAuthHeaders() can attach it
      localStorage.setItem('access_token', tokens.access_token);
      if (tokens.refresh_token) localStorage.setItem('refresh_token', tokens.refresh_token);

      const me = await apiClient.get<{
        id: string;
        email: string;
        full_name: string;
        tenant_id: string;
        roles: string[];
        is_active: boolean;
      }>('/auth/me');

      // 3. Persist full session
      saveSession(tokens.access_token, me.tenant_id);

      // 4. Update Zustand
      setUser({
        id: me.id,
        tenantId: me.tenant_id,
        name: me.full_name,
        email: me.email,
        role: me.roles[0] ?? 'staff',
        avatar: `https://ui-avatars.com/api/?name=${encodeURIComponent(me.full_name)}&background=FF9800&color=fff`,
      });

      toast.success(`مرحباً ${me.full_name}!`);
      router.push('/financial-core');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'فشل تسجيل الدخول، تحقق من بياناتك.';
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
          مرحباً بعودتك
        </h1>
        <p className="text-[#75777D] text-[14px]">
          سجّل دخولك للوصول إلى لوحة التحكم.
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5">
        {/* Email */}
        <div>
          <label htmlFor="login-email" className="block text-[13px] font-semibold text-[#040D1B] mb-1.5">
            البريد الإلكتروني
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 end-0 pe-3.5 flex items-center pointer-events-none">
              <Mail className="w-4 h-4 text-[#75777D]" />
            </div>
            <input
              id="login-email"
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
            <p className="mt-1 text-[12px] text-[#BA1A1A]">{errors.email.message as string}</p>
          )}
        </div>

        {/* Password */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label htmlFor="login-password" className="block text-[13px] font-semibold text-[#040D1B]">
              كلمة المرور
            </label>
            <Link
              href="/forgot-password"
              className="text-[12px] text-[#FF9800] hover:text-[#E6890A] font-medium transition-colors"
            >
              نسيت كلمة المرور؟
            </Link>
          </div>
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
              id="login-password"
              type={showPw ? 'text' : 'password'}
              autoComplete="current-password"
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
        </div>

        {/* Remember me */}
        <div className="flex items-center justify-end gap-2">
          <label htmlFor="login-remember" className="text-[13px] text-[#75777D] cursor-pointer select-none">
            تذكرني على هذا الجهاز
          </label>
          <input
            id="login-remember"
            type="checkbox"
            {...register('remember')}
            className="h-4 w-4 rounded border-[#C5C6CC] text-[#FF9800] accent-[#FF9800] cursor-pointer"
          />
        </div>

        {/* Submit */}
        <button
          id="login-submit-btn"
          type="submit"
          disabled={isLoading}
          className="group relative flex w-full justify-center items-center gap-2.5 h-12 rounded-xl bg-[#FF9800] hover:bg-[#E6890A] text-white font-bold text-[15px] transition-all duration-200 shadow-lg shadow-[#FF9800]/25 hover:shadow-[#FF9800]/40 hover:scale-[1.01] active:scale-[0.98] disabled:opacity-70 disabled:cursor-not-allowed disabled:scale-100 mt-2"
        >
          {isLoading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              جاري تسجيل الدخول…
            </>
          ) : (
            <>
              تسجيل الدخول
              <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
            </>
          )}
        </button>

        {/* Divider */}
        <div className="relative flex items-center gap-3 py-1">
          <div className="flex-1 h-px bg-[#E4E2E3]" />
          <span className="text-[12px] text-[#75777D]">ليس لديك حساب؟</span>
          <div className="flex-1 h-px bg-[#E4E2E3]" />
        </div>

        <Link
          href="/register"
          id="go-to-register-link"
          className="flex w-full justify-center items-center h-11 rounded-xl border border-[#C5C6CC] hover:border-[#FF9800]/50 text-[#040D1B] hover:text-[#FF9800] font-semibold text-[14px] transition-all duration-200 hover:bg-[#FFF3E0]"
        >
          إنشاء حساب جديد مجاناً
        </Link>
      </form>
    </div>
  );
}
