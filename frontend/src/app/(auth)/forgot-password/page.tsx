"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import Link from "next/link";

const forgotPasswordSchema = z.object({
  email: z.string().email({ message: "الرجاء إدخال بريد إلكتروني صحيح" }),
});

type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>;

export default function ForgotPasswordPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const form = useForm<ForgotPasswordFormValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });

  const onSubmit = async (data: ForgotPasswordFormValues) => {
    setIsLoading(true);
    setErrorMsg("");
    try {
      await apiClient.post("/auth/forgot-password", { email: data.email });
    } catch (err) {
      // Deliberately not surfacing this as a hard failure for most cases —
      // the backend returns a generic response regardless of whether the
      // email exists, so we only show a real error for actual outages.
      const axiosErr = err as AxiosError<{ detail?: string }>;
      if (axiosErr.code === "ERR_NETWORK" || !axiosErr.response) {
        setErrorMsg(pickDetail(axiosErr, "تعذر الاتصال بالخادم، حاول مرة أخرى."));
        setIsLoading(false);
        return;
      }
    }
    setIsLoading(false);
    setSubmitted(true);
  };

  return (
    <div
      className="min-h-screen bg-surface flex flex-col items-center justify-center p-gutter"
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
            نسيت كلمة المرور؟
          </h2>
        </div>

        {/* Forgot Password Card */}
        <div className="glass-card rounded-xl p-8 mb-8">
          {errorMsg && (
            <div className="w-full flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-5 text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {errorMsg}
            </div>
          )}

          {submitted ? (
            <div className="text-center space-y-4 py-2">
              <div className="w-14 h-14 rounded-full bg-success-bg text-success flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-7 h-7" />
              </div>
              <p className="text-body-md text-on-surface leading-relaxed">
                لو البريد الإلكتروني ده مسجل عندنا، هيوصلك رابط لإعادة تعيين كلمة المرور.
              </p>
              <Link
                href="/login"
                className="inline-block text-primary font-bold text-body-sm hover:underline"
              >
                العودة لتسجيل الدخول
              </Link>
            </div>
          ) : (
            <form className="space-y-6" onSubmit={form.handleSubmit(onSubmit)}>
              <p className="text-body-sm text-on-surface-variant">
                أدخل بريدك الإلكتروني وسنرسل لك رابط إعادة تعيين كلمة المرور إذا كان مسجلاً لدينا.
              </p>

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
                  {...form.register("email")}
                  id="email"
                  type="email"
                  className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right font-mono ${
                    form.formState.errors.email
                      ? "border-error focus:border-error ring-1 ring-error"
                      : "border-outline-variant"
                  }`}
                  placeholder="example@nexus-erp.com"
                  dir="ltr"
                />
                {form.formState.errors.email && (
                  <p className="text-body-sm text-error">{form.formState.errors.email.message}</p>
                )}
              </div>

              {/* Submit Button */}
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
                    <span>جاري الإرسال...</span>
                  </>
                ) : (
                  <span>إرسال رابط إعادة التعيين</span>
                )}
              </button>
            </form>
          )}

          {!submitted && (
            <div className="mt-8 pt-6 border-t border-outline-variant text-center">
              <p className="text-on-surface-variant font-body-sm text-body-sm">
                تذكرت كلمة المرور؟{" "}
                <Link href="/login" className="text-primary font-bold hover:underline">
                  تسجيل الدخول
                </Link>
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
