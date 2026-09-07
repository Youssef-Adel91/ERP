"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import {
  portalApiClient,
  getPortalTenantId,
  getPortalPhone,
  savePortalContact,
  savePortalSession,
} from "@/lib/portal-api-client";
import { pickDetail } from "@/lib/api-client";

type Step = "phone" | "otp";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // A merchant shares a portal link with the tenant baked in
  // (?tenant=<uuid>) so a customer never has to know/paste it themselves.
  // Falls back to whatever tenant id this browser used last time, then to
  // a manual field only if neither is available.
  const tenantFromUrl = searchParams.get("tenant") ?? "";

  const [step, setStep] = useState<Step>("phone");
  const [tenantId, setTenantId] = useState(tenantFromUrl || getPortalTenantId() || "");
  const [phone, setPhone] = useState(getPortalPhone() || "");
  const [otpCode, setOtpCode] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [infoMsg, setInfoMsg] = useState("");

  const needsManualTenant = !tenantFromUrl;

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg("");
    setInfoMsg("");

    if (!tenantId.trim()) {
      setErrorMsg("الرجاء إدخال معرف المنشأة.");
      return;
    }
    if (!phone.trim()) {
      setErrorMsg("الرجاء إدخال رقم الهاتف.");
      return;
    }

    setIsLoading(true);
    try {
      await portalApiClient.post("/portal/auth/login", {
        phone_e164: phone.trim(),
        tenant_id: tenantId.trim(),
      });
      savePortalContact(tenantId.trim(), phone.trim());
      setInfoMsg("تم إرسال رمز الدخول عبر واتساب أو البريد الإلكتروني.");
      setStep("otp");
    } catch (err) {
      setErrorMsg(pickDetail(err, "تعذر إرسال رمز الدخول، تحقق من رقم الهاتف والمحاولة مرة أخرى."));
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg("");

    if (!otpCode.trim()) {
      setErrorMsg("الرجاء إدخال رمز التحقق.");
      return;
    }

    setIsLoading(true);
    try {
      const { data } = await portalApiClient.post<{ access_token: string; token_type: string }>(
        "/portal/auth/login/verify",
        {
          phone_e164: phone.trim(),
          tenant_id: tenantId.trim(),
          otp_code: otpCode.trim(),
        },
      );
      savePortalSession(data.access_token, tenantId.trim(), phone.trim());
      router.push("/portal/invoices");
    } catch (err) {
      setErrorMsg(pickDetail(err, "رمز التحقق غير صحيح أو منتهي الصلاحية."));
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
        <div className="text-center mb-10">
          <div className="flex justify-center items-center gap-3 mb-4">
            <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center shadow-overlay">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-7 h-7 fill-white">
                <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z" />
              </svg>
            </div>
            <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight">بوابة العملاء</h1>
          </div>
          <h2 className="font-headline-sm text-headline-sm text-on-surface-variant">
            {step === "phone" ? "سجّل الدخول لعرض فواتيرك ودفعها" : "أدخل رمز التحقق المرسل إليك"}
          </h2>
        </div>

        <div className="glass-card rounded-xl p-8 mb-8">
          {errorMsg && (
            <div className="w-full flex items-center gap-2 bg-error-container text-on-error-container p-3 rounded-lg mb-5 text-body-sm font-medium border border-error">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {errorMsg}
            </div>
          )}
          {infoMsg && !errorMsg && (
            <div className="w-full flex items-center gap-2 bg-success-bg text-success p-3 rounded-lg mb-5 text-body-sm font-medium border border-success/30">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              {infoMsg}
            </div>
          )}

          {step === "phone" ? (
            <form className="space-y-5" onSubmit={handleSendCode}>
              {needsManualTenant && (
                <div className="space-y-2">
                  <label htmlFor="tenantId" className="font-label-caps text-label-caps text-on-surface-variant">
                    معرف المنشأة
                  </label>
                  <input
                    id="tenantId"
                    type="text"
                    value={tenantId}
                    onChange={(e) => setTenantId(e.target.value)}
                    className="input-field font-mono"
                    placeholder="سيوفره لك النشاط التجاري الذي تتعامل معه"
                    dir="ltr"
                  />
                </div>
              )}
              <div className="space-y-2">
                <label htmlFor="phone" className="font-label-caps text-label-caps text-on-surface-variant">
                  رقم الهاتف
                </label>
                <input
                  id="phone"
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="input-field font-mono"
                  placeholder="+201012345678"
                  dir="ltr"
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-primary text-on-primary py-4 px-6 rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:bg-primary-container hover:shadow-overlay active:scale-[0.98] transition-all duration-200 disabled:opacity-70"
              >
                {isLoading ? (
                  <>
                    <svg className="w-5 h-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span>جاري الإرسال...</span>
                  </>
                ) : (
                  <span>إرسال رمز الدخول</span>
                )}
              </button>
            </form>
          ) : (
            <form className="space-y-5" onSubmit={handleVerify}>
              <div className="space-y-2">
                <label htmlFor="otp" className="font-label-caps text-label-caps text-on-surface-variant">
                  رمز التحقق (6 أرقام)
                </label>
                <input
                  id="otp"
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                  className="input-field font-mono text-center tracking-[0.5em] text-headline-sm"
                  placeholder="••••••"
                  dir="ltr"
                  autoFocus
                />
              </div>
              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-primary text-on-primary py-4 px-6 rounded-lg font-headline-sm text-headline-sm flex items-center justify-center gap-2 hover:bg-primary-container hover:shadow-overlay active:scale-[0.98] transition-all duration-200 disabled:opacity-70"
              >
                {isLoading ? (
                  <>
                    <svg className="w-5 h-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span>جاري التحقق...</span>
                  </>
                ) : (
                  <span>تأكيد الدخول</span>
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setStep("phone");
                  setOtpCode("");
                  setErrorMsg("");
                  setInfoMsg("");
                }}
                className="w-full text-center text-body-sm text-primary hover:underline"
              >
                تعديل رقم الهاتف أو إعادة إرسال الرمز
              </button>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}

export default function PortalLoginPage() {
  // useSearchParams() requires a Suspense boundary in the app router.
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
