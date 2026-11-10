"use client";

import { useState } from "react";
import { SUPPORT_EMAIL } from "@/lib/brand";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { useAppStore } from "@/store/use-app-store";
import { apiClient, saveSession, pickDetail } from "@/lib/api-client";
import { AlertCircle } from "lucide-react";
import Link from "next/link";
import AuthShell from "@/components/auth/AuthShell";

const loginSchema = z.object({
  identifier: z.string().email({ message: "الرجاء إدخال بريد إلكتروني صحيح" }),
  password: z.string().min(6, { message: "كلمة المرور يجب أن تكون 6 أحرف على الأقل" }),
  remember: z.boolean().optional(),
});

type LoginFormValues = z.infer<typeof loginSchema>;

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

interface MeResponse {
  id: string;
  email: string;
  full_name: string;
  tenant_id: string;
  role: string;
  is_active: boolean;
}

export default function LoginPage() {
  const router = useRouter();
  const { setUser } = useAppStore();
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      identifier: "",
      password: "",
      remember: false,
    },
  });

  const onSubmit = async (data: LoginFormValues) => {
    setIsLoading(true);
    setErrorMsg("");
    try {
      const { data: tokens } = await apiClient.post<TokenResponse>("/auth/login", {
        email: data.identifier,
        password: data.password,
      });

      const persist = !!data.remember;

      saveSession(tokens.access_token, "", tokens.refresh_token, persist);

      const { data: me } = await apiClient.get<MeResponse>("/auth/me");
      saveSession(tokens.access_token, me.tenant_id, tokens.refresh_token, persist);

      setUser({
        id: me.id,
        tenantId: me.tenant_id,
        name: me.full_name,
        email: me.email,
        role: me.role,
        avatar: `https://ui-avatars.com/api/?name=${encodeURIComponent(me.full_name)}&background=2540F0&color=fff`,
      });

      router.push("/dashboard");
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      if (axiosErr.response?.status === 401) {
        setErrorMsg("البريد الإلكتروني أو كلمة المرور غير صحيحة.");
      } else {
        setErrorMsg(pickDetail(axiosErr, axiosErr.response ? "تعذر تسجيل الدخول، حاول مرة أخرى." : "تعذر الاتصال بالخادم، حاول مرة أخرى بعد قليل."));
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthShell>
      <main className="w-full max-w-[440px] animate-in fade-in duration-700 slide-in-from-bottom-4">
        {/* Logo & Header */}
        <div className="text-center mb-10">
          <div className="flex justify-center items-center gap-3 mb-4 lg:hidden">
            <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center shadow-overlay">
              {/* Material Symbol: hub */}
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-7 h-7 fill-white">
                <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z"/>
              </svg>
            </div>
            <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">Trust Core</h1>
          </div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface-variant">
            مرحباً بك مجدداً في نظام الإدارة المتكامل
          </h2>
        </div>

        {/* Login Card */}
        <div className="glass-card rounded-xl p-8 mb-8">
          {errorMsg && (
            <div className="w-full flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-5 text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {errorMsg}
            </div>
          )}

          <form className="space-y-6" onSubmit={form.handleSubmit(onSubmit)}>
            {/* Email Field */}
            <div className="space-y-2">
              <label
                htmlFor="email"
                className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1"
              >
                {/* mail icon */}
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-3.5 h-3.5 fill-current">
                  <path d="M160-160q-33 0-56.5-23.5T80-240v-480q0-33 23.5-56.5T160-800h640q33 0 56.5 23.5T880-720v480q0 33-23.5 56.5T800-160H160Zm320-280L160-640v400h640v-400L480-440Zm0-80 320-200H160l320 200ZM160-640v-80 480-400Z"/>
                </svg>
                البريد الإلكتروني
              </label>
              <input
                {...form.register("identifier")}
                id="email"
                type="email"
                className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right font-mono ${
                  form.formState.errors.identifier
                    ? "border-error focus:border-error ring-1 ring-error"
                    : "border-outline-variant"
                }`}
                placeholder="example@trustcore.app"
                dir="ltr"
              />
              {form.formState.errors.identifier && (
                <p className="text-body-sm text-error">{form.formState.errors.identifier.message}</p>
              )}
            </div>

            {/* Password Field */}
            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <label
                  htmlFor="password"
                  className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1"
                >
                  {/* lock icon */}
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-3.5 h-3.5 fill-current">
                    <path d="M240-80q-33 0-56.5-23.5T160-160v-400q0-33 23.5-56.5T240-640h40v-80q0-83 58.5-141.5T480-920q83 0 141.5 58.5T680-720v80h40q33 0 56.5 23.5T800-560v400q0 33-23.5 56.5T720-80H240Zm240-200q33 0 56.5-23.5T560-360q0-33-23.5-56.5T480-440q-33 0-56.5 23.5T400-360q0 33 23.5 56.5T480-280ZM360-640h240v-80q0-50-35-85t-85-35q-50 0-85 35t-35 85v80Z"/>
                  </svg>
                  كلمة المرور
                </label>
                <Link href="/forgot-password" className="text-primary font-body-sm text-body-sm hover:underline">
                  نسيت كلمة المرور؟
                </Link>
              </div>
              <div className="relative">
                <input
                  {...form.register("password")}
                  id="password"
                  type={showPassword ? "text" : "password"}
                  className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right ${
                    form.formState.errors.password
                      ? "border-error focus:border-error ring-1 ring-error"
                      : "border-outline-variant"
                  }`}
                  placeholder="••••••••"
                  dir="ltr"
                />
                <button
                  type="button"
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors"
                  onClick={() => setShowPassword((v) => !v)}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-current">
                      <path d="m644-428-58-58q9-47-27-88t-93-32l-58-58q17-8 34.5-12t37.5-4q75 0 127.5 52.5T660-500q0 20-4 37.5T644-428Zm128 126-58-56q38-29 67.5-63.5T832-500q-50-101-143.5-160.5T480-720q-29 0-57 4t-55 12l-62-62q41-17 84-25.5t90-8.5q151 0 269 83.5T920-500q-23 59-60.5 109.5T772-302Zm20 246L624-222q-35 11-70.5 16.5T480-200q-151 0-269-83.5T40-500q21-53 53-98.5t73-81.5L56-792l56-56 736 736-56 56ZM222-624q-29 26-53 57t-41 67q50 101 143.5 160.5T480-280q20 0 39-2.5t39-5.5l-36-38q-11 3-21 4.5t-21 1.5q-75 0-127.5-52.5T300-500q0-11 1.5-21t4.5-21l-84-82Zm319 93Zm-93 93Z"/>
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-current">
                      <path d="M480-320q75 0 127.5-52.5T660-500q0-75-52.5-127.5T480-680q-75 0-127.5 52.5T300-500q0 75 52.5 127.5T480-320Zm0-72q-45 0-76.5-31.5T372-500q0-45 31.5-76.5T480-608q45 0 76.5 31.5T588-500q0 45-31.5 76.5T480-392Zm0 192q-146 0-266-81.5T40-500q54-137 174-218.5T480-800q146 0 266 81.5T920-500q-54 137-174 218.5T480-200Z"/>
                    </svg>
                  )}
                </button>
              </div>
              {form.formState.errors.password && (
                <p className="text-body-sm text-error">{form.formState.errors.password.message}</p>
              )}
            </div>

            {/* Remember Me */}
            <div className="flex items-center gap-2">
              <input
                {...form.register("remember")}
                id="remember"
                type="checkbox"
                className="w-4 h-4 rounded border-outline-variant text-primary focus:ring-primary cursor-pointer"
              />
              <label htmlFor="remember" className="text-body-sm text-on-surface-variant cursor-pointer select-none">
                تذكرني على هذا الجهاز
              </label>
            </div>

            {/* Login Button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-primary text-on-primary py-4 px-6 rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:bg-primary-container hover:shadow-overlay active:scale-[0.98] transition-all duration-200 disabled:opacity-70"
            >
              {isLoading ? (
                <>
                  <svg className="w-5 h-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                  <span>جاري التحقق...</span>
                </>
              ) : (
                <>
                  <span>تسجيل الدخول</span>
                  {/* arrow_back icon (RTL) */}
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-white rtl-flip">
                    <path d="M647-440H160v-80h487L423-744l57-56 320 320-320 320-57-56 224-224Z"/>
                  </svg>
                </>
              )}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-outline-variant text-center">
            <p className="text-on-surface-variant font-body-sm text-body-sm">
              ليس لديك حساب؟{" "}
              <Link href="/register" className="text-primary font-bold hover:underline">
                سجل الآن
              </Link>
            </p>
          </div>
        </div>

        {/* Security Footer */}
        <footer className="flex flex-col items-center gap-6">
          <div className="text-center text-on-surface-variant font-body-sm text-body-sm space-y-1">
            <p>© {new Date().getFullYear()} Trust Core. جميع الحقوق محفوظة.</p>
            <div className="flex justify-center gap-4">
              <a href="#" className="hover:text-primary transition-colors">سياسة الخصوصية</a>
              <span className="text-outline-variant">|</span>
              <a href="#" className="hover:text-primary transition-colors">شروط الاستخدام</a>
              <span className="text-outline-variant">|</span>
              <a href={`mailto:${SUPPORT_EMAIL}?subject=Trust%20Core%20Support`} className="hover:text-primary transition-colors">الدعم الفني</a>
            </div>
          </div>
        </footer>
      </main>

      <style jsx>{`
        .rtl-flip {
          transform: scaleX(-1);
        }
      `}</style>
    </AuthShell>
  );
}
