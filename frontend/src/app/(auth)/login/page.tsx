"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { useAppStore } from "@/store/use-app-store";
import { apiClient, saveSession } from "@/lib/api-client";
import { AlertCircle } from "lucide-react";
import Link from "next/link";

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

      saveSession(tokens.access_token, "", tokens.refresh_token);

      const { data: me } = await apiClient.get<MeResponse>("/auth/me");
      saveSession(tokens.access_token, me.tenant_id, tokens.refresh_token);

      setUser({
        id: me.id,
        tenantId: me.tenant_id,
        name: me.full_name,
        email: me.email,
        role: me.role,
        avatar: `https://ui-avatars.com/api/?name=${encodeURIComponent(me.full_name)}&background=00288E&color=fff`,
      });

      router.push("/dashboard");
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      if (axiosErr.response?.status === 401) {
        setErrorMsg("البريد الإلكتروني أو كلمة المرور غير صحيحة.");
      } else {
        setErrorMsg(axiosErr.response?.data?.detail || axiosErr.message || "تعذر تسجيل الدخول، حاول مرة أخرى.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center p-gutter"
      style={{
        backgroundImage: "radial-gradient(#e5e7eb 0.5px, transparent 0.5px)",
        backgroundSize: "24px 24px",
      }}
    >
      <main className="w-full max-w-[440px] animate-in fade-in duration-700 slide-in-from-bottom-4">
        {/* Logo & Header */}
        <div className="text-center mb-10">
          <div className="flex justify-center items-center gap-3 mb-4">
            <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center shadow-overlay">
              {/* Material Symbol: hub */}
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-7 h-7 fill-white">
                <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z"/>
              </svg>
            </div>
            <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">Nexus ERP</h1>
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
                placeholder="example@nexus-erp.com"
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
                <a href="#" className="text-primary font-body-sm text-body-sm hover:underline">
                  نسيت كلمة المرور؟
                </a>
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
          <div className="flex items-center justify-center gap-8 opacity-60 hover:opacity-100 transition-all duration-300 grayscale hover:grayscale-0">
            {[
              { label: "SSL Secure", icon: (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-6 h-6 fill-current">
                  <path d="m438-452-58-57q-11-11-27.5-11T325-509q-11 11-11 27.5t11 27.5l84 85q12 12 28 12t28-12l170-170q11-11 11-27.5T635-594q-11-11-27.5-11T580-594L438-452Zm42 356q-7 0-14-1t-13-3Q270-162 175-261T80-480v-240q0-27 16.5-47.5T138-800l320-120q10-4 22-4t22 4l320 120q25 9 41.5 29.5T880-720v240q0 151-95 250T493-99q-6 2-13 3t-14 1Z"/>
                </svg>
              )},
              { label: "GDPR Ready", icon: (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-6 h-6 fill-current">
                  <path d="M480-80q-83 0-141.5-58.5T280-280q0-48 18.5-91T351-446q-11-20-16-43t-5-45q0-83 58.5-141.5T530-734q23 0 44 5.5t39 15.5l-81 81q-5 5-7.5 11t-2.5 13q0 13 9 22t22 9q7 0 13-2.5t11-7.5l81-81q10 18 15.5 39t5.5 44q0 46-18 87.5T601-446q33 26 51.5 65T671-297q0 79-56.5 138T480-80Zm0-80q46 0 78-32.5T590-271q0-28-10.5-51.5T549-363l-43 43q-12 12-28.5 12T449-320q-12-12-12-28.5t12-28.5l43-43q-17-15-26-37.5T457-506q-28 13-45.5 38.5T394-406h-80q0-57 32-103.5T432-577q-7-12-11.5-25.5T416-630q0-46 32-79t79-33q14 0 27 3.5t24 9.5l-39 39q-24 24-24 56.5t24 56.5q24 24 56.5 24t56.5-24l39-39q6 11 9.5 24t3.5 27q0 47-33 79t-79 32h-4q5 10 7.5 20.5T620-491q50 26 81.5 74T733-314q-1 66-47.5 113T580-154q-16 0-31-2.5T521-164l53-53q6-6 8.5-13.5T585-246q0-17-11.5-28.5T545-286q-7 0-14.5 2.5T519-277l-53 53q-5-15-7.5-30T456-284q0-51 29-91t75-56q-13-4-24.5-11T516-459q-5 5-7.5 11t-2.5 13q0 13 8.5 22T536-404q7 0 13.5-2.5T561-414q26 27 40.5 62.5T616-275q0 46-32.5 80.5T505-160q-3 0-12.5-.5T480-160Z"/>
                </svg>
              )},
              { label: "ISO 27001", icon: (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-6 h-6 fill-current">
                  <path d="M480-80q-83 0-156-31.5T197-197q-54-54-85.5-127T80-480q0-83 31.5-156T197-763q54-54 127-85.5T480-880q83 0 156 31.5T763-763q54 54 85.5 127T880-480q0 83-31.5 156T763-197q-54 54-127 85.5T480-80Zm0-80q134 0 227-93t93-227q0-134-93-227t-227-93q-134 0-227 93t-93 227q0 134 93 227t227 93Zm0-120q-83 0-141.5-58.5T280-480q0-83 58.5-141.5T480-680q83 0 141.5 58.5T680-480q0 83-58.5 141.5T480-280Z"/>
                </svg>
              )},
            ].map(({ label, icon }) => (
              <div key={label} className="flex flex-col items-center gap-1 text-on-surface-variant">
                {icon}
                <span className="font-label-caps text-[9px] uppercase tracking-widest">{label}</span>
              </div>
            ))}
          </div>

          <div className="text-center text-on-surface-variant font-body-sm text-body-sm space-y-1">
            <p>© {new Date().getFullYear()} Nexus ERP. جميع الحقوق محفوظة.</p>
            <div className="flex justify-center gap-4">
              <a href="#" className="hover:text-primary transition-colors">سياسة الخصوصية</a>
              <span className="text-outline-variant">|</span>
              <a href="#" className="hover:text-primary transition-colors">شروط الاستخدام</a>
              <span className="text-outline-variant">|</span>
              <a href="mailto:youssefffadel555@gmail.com?subject=Nexus%20ERP%20Support" className="hover:text-primary transition-colors">الدعم الفني</a>
            </div>
          </div>
        </footer>
      </main>

      <style jsx>{`
        .rtl-flip {
          transform: scaleX(-1);
        }
      `}</style>
    </div>
  );
}
