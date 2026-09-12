"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import Link from "next/link";
import { AlertCircle, Loader2 } from "lucide-react";
import { useAppStore } from "@/store/use-app-store";
import { apiClient, saveSession, pickDetail } from "@/lib/api-client";
import { AxiosError } from "axios";

const registerSchema = z.object({
  company_name: z.string().min(2, "اسم الشركة/المؤسسة مطلوب (حرفين على الأقل)"),
  full_name: z.string().min(2, "الاسم بالكامل مطلوب"),
  email: z.string().email("بريد إلكتروني غير صحيح"),
  password: z
    .string()
    .min(8, "كلمة المرور يجب أن تكون 8 أحرف على الأقل")
    .regex(/\d/, "يجب أن تحتوي على رقم واحد على الأقل")
    .regex(/[A-Z]/, "يجب أن تحتوي على حرف كبير واحد على الأقل"),
});

type RegisterForm = z.infer<typeof registerSchema>;

interface RegisterResponse {
  tenant_id: string;
  user_id: string;
  email: string;
  full_name: string;
  access_token: string;
  refresh_token: string;
  token_type: string;
  message: string;
}

const steps = ["بيانات الشركة", "بيانات المسؤول", "إنشاء الحساب"];

export default function RegisterPage() {
  const router = useRouter();
  const { setUser } = useAppStore();
  const [showPw, setShowPw] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [errorMsg, setErrorMsg] = useState("");
  const [step, setStep] = useState(0); // 0=company, 1=user info, 2=submit

  const loadingMessages = [
    "جاري إنشاء الحساب...",
    "جاري إعداد قاعدة البيانات...",
    "جاري تهيئة نظام المحاسبة...",
    "جاري الانتهاء من الإعداد...",
  ];

  const form = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
    defaultValues: { company_name: "", full_name: "", email: "", password: "" },
    mode: "onTouched",
  });

  const { formState: { errors } } = form;

  const goNext = async () => {
    if (step === 0) {
      const ok = await form.trigger("company_name");
      if (ok) setStep(1);
    } else if (step === 1) {
      const ok = await form.trigger(["full_name", "email"]);
      if (ok) setStep(2);
    }
  };

  const onSubmit = async (data: RegisterForm) => {
    setIsLoading(true);
    setLoadingStep(0);
    setErrorMsg("");

    // Cycle through loading messages while we wait for provisioning
    const msgInterval = setInterval(() => {
      setLoadingStep((prev) => (prev + 1) % loadingMessages.length);
    }, 3000);

    try {
      // Register takes up to ~60s (Alembic tenant migrations + COA seed)
      const { data: res } = await apiClient.post<RegisterResponse>("/auth/register", {
        company_name: data.company_name,
        full_name: data.full_name,
        email: data.email,
        password: data.password,
      }, { timeout: 120_000 });

      clearInterval(msgInterval);

      saveSession(res.access_token, res.tenant_id, res.refresh_token);

      setUser({
        id: res.user_id,
        tenantId: res.tenant_id,
        name: res.full_name,
        email: res.email,
        role: "OWNER",
        avatar: `https://ui-avatars.com/api/?name=${encodeURIComponent(res.full_name)}&background=00288E&color=fff`,
      });

      router.push("/onboarding/systems");
    } catch (err) {
      clearInterval(msgInterval);
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setErrorMsg(pickDetail(axiosErr, axiosErr.message || "حدث خطأ أثناء إنشاء الحساب."));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen bg-surface flex flex-col items-center justify-center p-gutter"
      style={{
        backgroundImage: "radial-gradient(#e5e7eb 0.5px, transparent 0.5px)",
        backgroundSize: "24px 24px",
      }}
    >
      <main className="w-full max-w-[500px] animate-in fade-in duration-700 slide-in-from-bottom-4">

        {/* Logo & Header */}
        <div className="text-center mb-8">
          <div className="flex justify-center items-center gap-3 mb-4">
            <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center shadow-overlay">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-7 h-7 fill-white">
                <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z"/>
              </svg>
            </div>
            <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">Nexus ERP</h1>
          </div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface-variant">
            أنشئ مساحة عمل شركتك — مجاناً
          </h2>
        </div>

        {/* Step Indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {steps.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold transition-all ${
                i < step ? "bg-secondary text-on-secondary" :
                i === step ? "bg-primary text-on-primary" :
                "bg-surface-container text-outline"
              }`}>
                {i < step ? (
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-4 h-4 fill-current">
                    <path d="M382-240 154-468l57-57 171 171 367-367 57 57-424 424Z"/>
                  </svg>
                ) : i + 1}
              </div>
              <span className={`text-body-sm hidden sm:inline ${i === step ? "text-primary font-bold" : "text-outline"}`}>{s}</span>
              {i < steps.length - 1 && <div className={`w-8 h-px ${i < step ? "bg-secondary" : "bg-outline-variant"}`} />}
            </div>
          ))}
        </div>

        {/* Card */}
        <div className="glass-card rounded-xl p-8 mb-6">
          {errorMsg && (
            <div className="flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-5 text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {errorMsg}
            </div>
          )}

          <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
            {/* Step 0 — Company */}
            {step === 0 && (
              <div className="space-y-5">
                <div>
                  <h3 className="font-headline-sm text-headline-sm text-on-surface mb-1">بيانات الشركة</h3>
                  <p className="text-body-sm text-on-surface-variant">أخبرنا عن شركتك أو مؤسستك</p>
                </div>
                <div className="space-y-2">
                  <label htmlFor="register-company" className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-3.5 h-3.5 fill-current">
                      <path d="M120-120v-560l320-160 320 160v560H120Zm80-80h560v-400L440-740 200-600v400Zm200-200h80v-80h80v80h80v-200H400v200Zm-200 200v-400 400Z"/>
                    </svg>
                    اسم الشركة / المؤسسة
                  </label>
                  <input
                    id="register-company"
                    type="text"
                    placeholder="مثال: شركة النور للتجارة"
                    {...form.register("company_name")}
                    className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right ${errors.company_name ? "border-error" : "border-outline-variant"}`}
                  />
                  {errors.company_name && <p className="text-body-sm text-error">{errors.company_name.message}</p>}
                </div>

                <button
                  type="button"
                  onClick={goNext}
                  className="w-full bg-primary text-on-primary py-3.5 px-6 rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all"
                >
                  التالي
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-white" style={{ transform: "scaleX(-1)" }}>
                    <path d="M647-440H160v-80h487L423-744l57-56 320 320-320 320-57-56 224-224Z"/>
                  </svg>
                </button>
              </div>
            )}

            {/* Step 1 — User Info */}
            {step === 1 && (
              <div className="space-y-5">
                <div>
                  <h3 className="font-headline-sm text-headline-sm text-on-surface mb-1">بيانات المسؤول</h3>
                  <p className="text-body-sm text-on-surface-variant">هتبقى المدير الرئيسي للنظام</p>
                </div>
                <div className="space-y-2">
                  <label htmlFor="register-name" className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-3.5 h-3.5 fill-current">
                      <path d="M480-480q-66 0-113-47t-47-113q0-66 47-113t113-47q66 0 113 47t47 113q0 66-47 113t-113 47ZM160-160v-112q0-34 17.5-62.5T224-378q62-31 128.5-46.5T480-440q66 0 132.5 15.5T741-378q29 15 46 43.5t17 62.5v112H160Z"/>
                    </svg>
                    الاسم بالكامل
                  </label>
                  <input
                    id="register-name"
                    type="text"
                    placeholder="مثال: أحمد محمد"
                    {...form.register("full_name")}
                    className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right ${errors.full_name ? "border-error" : "border-outline-variant"}`}
                  />
                  {errors.full_name && <p className="text-body-sm text-error">{errors.full_name.message}</p>}
                </div>
                <div className="space-y-2">
                  <label htmlFor="register-email" className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-3.5 h-3.5 fill-current">
                      <path d="M160-160q-33 0-56.5-23.5T80-240v-480q0-33 23.5-56.5T160-800h640q33 0 56.5 23.5T880-720v480q0 33-23.5 56.5T800-160H160Zm320-280L160-640v400h640v-400L480-440Zm0-80 320-200H160l320 200ZM160-640v-80 480-400Z"/>
                    </svg>
                    البريد الإلكتروني
                  </label>
                  <input
                    id="register-email"
                    type="email"
                    placeholder="you@company.com"
                    dir="ltr"
                    autoComplete="email"
                    {...form.register("email")}
                    className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right font-mono ${errors.email ? "border-error" : "border-outline-variant"}`}
                  />
                  {errors.email && <p className="text-body-sm text-error">{errors.email.message}</p>}
                </div>

                <div className="flex gap-3">
                  <button type="button" onClick={() => setStep(0)}
                    className="flex-1 border border-outline-variant py-3 rounded-lg text-on-surface-variant hover:bg-surface-container transition-colors font-medium">
                    رجوع
                  </button>
                  <button type="button" onClick={goNext}
                    className="flex-[2] bg-primary text-on-primary py-3 rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all">
                    التالي
                  </button>
                </div>
              </div>
            )}

            {/* Step 2 — Password & Submit */}
            {step === 2 && (
              <div className="space-y-5">
                <div>
                  <h3 className="font-headline-sm text-headline-sm text-on-surface mb-1">أنشئ كلمة المرور</h3>
                  <p className="text-body-sm text-on-surface-variant">استخدم كلمة مرور قوية تحتوي على أرقام وحروف كبيرة</p>
                </div>
                <div className="space-y-2">
                  <label htmlFor="register-password" className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-3.5 h-3.5 fill-current">
                      <path d="M240-80q-33 0-56.5-23.5T160-160v-400q0-33 23.5-56.5T240-640h40v-80q0-83 58.5-141.5T480-920q83 0 141.5 58.5T680-720v80h40q33 0 56.5 23.5T800-560v400q0 33-23.5 56.5T720-80H240Zm240-200q33 0 56.5-23.5T560-360q0-33-23.5-56.5T480-440q-33 0-56.5 23.5T400-360q0 33 23.5 56.5T480-280ZM360-640h240v-80q0-50-35-85t-85-35q-50 0-85 35t-35 85v80Z"/>
                    </svg>
                    كلمة المرور
                  </label>
                  <div className="relative">
                    <input
                      id="register-password"
                      type={showPw ? "text" : "password"}
                      placeholder="••••••••"
                      dir="ltr"
                      autoComplete="new-password"
                      {...form.register("password")}
                      className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right ${errors.password ? "border-error" : "border-outline-variant"}`}
                    />
                    <button type="button" onClick={() => setShowPw(v => !v)} tabIndex={-1}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-primary transition-colors">
                      {showPw
                        ? <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-current"><path d="m644-428-58-58q9-47-27-88t-93-32l-58-58q17-8 34.5-12t37.5-4q75 0 127.5 52.5T660-500q0 20-4 37.5T644-428Zm128 126-58-56q38-29 67.5-63.5T832-500q-50-101-143.5-160.5T480-720q-29 0-57 4t-55 12l-62-62q41-17 84-25.5t90-8.5q151 0 269 83.5T920-500q-23 59-60.5 109.5T772-302Zm20 246L624-222q-35 11-70.5 16.5T480-200q-151 0-269-83.5T40-500q21-53 53-98.5t73-81.5L56-792l56-56 736 736-56 56ZM222-624q-29 26-53 57t-41 67q50 101 143.5 160.5T480-280q20 0 39-2.5t39-5.5l-36-38q-11 3-21 4.5t-21 1.5q-75 0-127.5-52.5T300-500q0-11 1.5-21t4.5-21l-84-82Z"/></svg>
                        : <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-current"><path d="M480-320q75 0 127.5-52.5T660-500q0-75-52.5-127.5T480-680q-75 0-127.5 52.5T300-500q0 75 52.5 127.5T480-320Zm0-72q-45 0-76.5-31.5T372-500q0-45 31.5-76.5T480-608q45 0 76.5 31.5T588-500q0 45-31.5 76.5T480-392Zm0 192q-146 0-266-81.5T40-500q54-137 174-218.5T480-800q146 0 266 81.5T920-500q-54 137-174 218.5T480-200Z"/></svg>
                      }
                    </button>
                  </div>
                  {errors.password && <p className="text-body-sm text-error">{errors.password.message}</p>}
                  {/* Password strength hints */}
                  <div className="flex gap-3 mt-1">
                    {[
                      { label: "8 أحرف+", ok: (form.watch("password")?.length ?? 0) >= 8 },
                      { label: "رقم", ok: /\d/.test(form.watch("password") ?? "") },
                      { label: "حرف كبير", ok: /[A-Z]/.test(form.watch("password") ?? "") },
                    ].map(hint => (
                      <span key={hint.label} className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${hint.ok ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container text-outline"}`}>
                        {hint.ok ? "✓" : "○"} {hint.label}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Terms */}
                <p className="text-body-sm text-on-surface-variant text-center">
                  بالتسجيل أنت توافق على{" "}
                  <a href="#" className="text-primary hover:underline">شروط الاستخدام</a>
                  {" "}و{" "}
                  <a href="#" className="text-primary hover:underline">سياسة الخصوصية</a>
                </p>

                <div className="flex gap-3">
                  <button type="button" onClick={() => setStep(1)}
                    className="flex-1 border border-outline-variant py-3 rounded-lg text-on-surface-variant hover:bg-surface-container transition-colors font-medium">
                    رجوع
                  </button>
                  <button type="submit" disabled={isLoading}
                    className="flex-[2] bg-primary text-on-primary py-3.5 rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all disabled:opacity-70">
                    {isLoading ? (
                      <><Loader2 className="w-5 h-5 animate-spin" /> {loadingMessages[loadingStep]}</>
                    ) : "إنشاء الحساب"}
                  </button>
                </div>
              </div>
            )}
          </form>

          <div className="mt-6 pt-5 border-t border-outline-variant text-center">
            <p className="text-on-surface-variant font-body-sm text-body-sm">
              لديك حساب بالفعل؟{" "}
              <Link href="/login" className="text-primary font-bold hover:underline">تسجيل الدخول</Link>
            </p>
          </div>
        </div>

        {/* Security footer */}
        <div className="flex justify-center gap-8 opacity-50 hover:opacity-80 transition-opacity">
          {["SSL Secure", "GDPR Ready", "ISO 27001"].map(label => (
            <div key={label} className="flex flex-col items-center gap-1 text-on-surface-variant">
              <div className="w-5 h-5 rounded-full border-2 border-current flex items-center justify-center text-[8px] font-black">✓</div>
              <span className="text-[9px] uppercase tracking-widest font-bold">{label}</span>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
