"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { AxiosError } from "axios";
import { apiClient, pickDetail } from "@/lib/api-client";
import { AlertCircle, Loader2 } from "lucide-react";
import Link from "next/link";

const resetPasswordSchema = z
  .object({
    password: z.string().min(6, { message: "كلمة المرور يجب أن تكون 6 أحرف على الأقل" }),
    confirmPassword: z.string().min(6, { message: "كلمة المرور يجب أن تكون 6 أحرف على الأقل" }),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "كلمتا المرور غير متطابقتين",
    path: ["confirmPassword"],
  });

type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;

function ResetPasswordInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const form = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirmPassword: "" },
  });

  const onSubmit = async (data: ResetPasswordFormValues) => {
    if (!token) {
      setErrorMsg("رابط إعادة التعيين غير صالح أو منتهي الصلاحية.");
      return;
    }
    setIsLoading(true);
    setErrorMsg("");
    try {
      await apiClient.post("/auth/reset-password", {
        token,
        new_password: data.password,
      });
      router.push("/login?reset=success");
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      if (axiosErr.response?.status === 400 || axiosErr.response?.status === 401) {
        setErrorMsg("الرابط غير صالح أو منتهي الصلاحية، برجاء طلب رابط جديد.");
      } else {
        setErrorMsg(pickDetail(axiosErr, axiosErr.message || "تعذر إعادة تعيين كلمة المرور، حاول مرة أخرى."));
      }
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
            إعادة تعيين كلمة المرور
          </h2>
        </div>

        {/* Reset Password Card */}
        <div className="glass-card rounded-xl p-8 mb-8">
          {!token && (
            <div className="w-full flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-5 text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" />
              رابط إعادة التعيين غير صالح، برجاء التأكد من الرابط أو طلب رابط جديد.
            </div>
          )}

          {errorMsg && (
            <div className="w-full flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-5 text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {errorMsg}
            </div>
          )}

          <form className="space-y-6" onSubmit={form.handleSubmit(onSubmit)}>
            {/* New Password Field */}
            <div className="space-y-2">
              <label
                htmlFor="password"
                className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1"
              >
                {/* lock icon */}
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-3.5 h-3.5 fill-current">
                  <path d="M240-80q-33 0-56.5-23.5T160-160v-400q0-33 23.5-56.5T240-640h40v-80q0-83 58.5-141.5T480-920q83 0 141.5 58.5T680-720v80h40q33 0 56.5 23.5T800-560v400q0 33-23.5 56.5T720-80H240Zm240-200q33 0 56.5-23.5T560-360q0-33-23.5-56.5T480-440q-33 0-56.5 23.5T400-360q0 33 23.5 56.5T480-280ZM360-640h240v-80q0-50-35-85t-85-35q-50 0-85 35t-35 85v80Z"/>
                </svg>
                كلمة المرور الجديدة
              </label>
              <input
                {...form.register("password")}
                id="password"
                type="password"
                className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right ${
                  form.formState.errors.password
                    ? "border-error focus:border-error ring-1 ring-error"
                    : "border-outline-variant"
                }`}
                placeholder="••••••••"
                dir="ltr"
              />
              {form.formState.errors.password && (
                <p className="text-body-sm text-error">{form.formState.errors.password.message}</p>
              )}
            </div>

            {/* Confirm Password Field */}
            <div className="space-y-2">
              <label
                htmlFor="confirmPassword"
                className="font-label-caps text-label-caps text-on-surface-variant flex items-center gap-1"
              >
                {/* lock icon */}
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-3.5 h-3.5 fill-current">
                  <path d="M240-80q-33 0-56.5-23.5T160-160v-400q0-33 23.5-56.5T240-640h40v-80q0-83 58.5-141.5T480-920q83 0 141.5 58.5T680-720v80h40q33 0 56.5 23.5T800-560v400q0 33-23.5 56.5T720-80H240Zm240-200q33 0 56.5-23.5T560-360q0-33-23.5-56.5T480-440q-33 0-56.5 23.5T400-360q0 33 23.5 56.5T480-280ZM360-640h240v-80q0-50-35-85t-85-35q-50 0-85 35t-35 85v80Z"/>
                </svg>
                تأكيد كلمة المرور
              </label>
              <input
                {...form.register("confirmPassword")}
                id="confirmPassword"
                type="password"
                className={`w-full px-4 py-3 bg-surface-container-low border rounded-lg focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all outline-none text-right ${
                  form.formState.errors.confirmPassword
                    ? "border-error focus:border-error ring-1 ring-error"
                    : "border-outline-variant"
                }`}
                placeholder="••••••••"
                dir="ltr"
              />
              {form.formState.errors.confirmPassword && (
                <p className="text-body-sm text-error">{form.formState.errors.confirmPassword.message}</p>
              )}
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading || !token}
              className="w-full bg-primary text-on-primary py-4 px-6 rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:bg-primary-container hover:shadow-overlay active:scale-[0.98] transition-all duration-200 disabled:opacity-70"
            >
              {isLoading ? (
                <>
                  <svg className="w-5 h-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                  <span>جاري الحفظ...</span>
                </>
              ) : (
                <span>حفظ كلمة المرور الجديدة</span>
              )}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-outline-variant text-center">
            <p className="text-on-surface-variant font-body-sm text-body-sm">
              تذكرت كلمة المرور؟{" "}
              <Link href="/login" className="text-primary font-bold hover:underline">
                تسجيل الدخول
              </Link>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-surface flex items-center justify-center">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
        </div>
      }
    >
      <ResetPasswordInner />
    </Suspense>
  );
}
