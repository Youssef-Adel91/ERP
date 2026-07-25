'use client';

import { useAppStore } from '@/store/use-app-store';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Lock, Mail, ArrowRight, CheckCircle2 } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { toast } from 'sonner';

export default function ForgotPasswordPage() {
  const isAr = useAppStore((state) => state.language === 'ar');
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    
    // Simulate API call
    setTimeout(() => {
      setSubmitted(true);
      toast.success(isAr ? 'تم إرسال رابط الاستعادة' : 'Reset link sent');
    }, 1000);
  };

  return (
    <div className="min-h-screen bg-paper flex flex-col justify-center py-12 sm:px-6 lg:px-8 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/5 rounded-full blur-[100px] pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-accent/5 rounded-full blur-[100px] pointer-events-none"></div>

      <div className="sm:mx-auto sm:w-full sm:max-w-md relative z-10">
        <div className="flex justify-center mb-6">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-xl font-heading">T</span>
            </div>
            <span className="text-2xl font-bold font-heading text-foreground">Trust Core</span>
          </div>
        </div>

        <Card className="border-border shadow-xl backdrop-blur-sm bg-card/90">
          <CardContent className="pt-10 pb-10 px-8">
            {!submitted ? (
              <>
                <div className="text-center mb-8">
                  <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Lock className="w-8 h-8 text-primary" />
                  </div>
                  <h2 className="text-2xl font-bold mb-2 text-foreground">{isAr ? 'استعادة كلمة المرور' : 'Reset Password'}</h2>
                  <p className="text-sm text-muted-foreground">
                    {isAr ? 'أدخل بريدك الإلكتروني المسجل وسنرسل لك رابطاً لإنشاء كلمة مرور جديدة.' : 'Enter your registered email and we will send you a link to create a new password.'}
                  </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-6">
                  <div className="space-y-2">
                    <label htmlFor="email" className="block text-sm font-bold text-foreground">
                      {isAr ? 'البريد الإلكتروني' : 'Email Address'}
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 start-0 flex items-center ps-3 pointer-events-none text-muted-foreground">
                        <Mail className="w-5 h-5" />
                      </div>
                      <Input
                        id="email"
                        name="email"
                        type="email"
                        autoComplete="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="h-12 ps-10 block w-full rounded-lg border-border focus:ring-primary focus:border-primary sm:text-sm"
                        placeholder="admin@trustcore.com"
                        dir="ltr"
                      />
                    </div>
                  </div>

                  <Button type="submit" className="w-full h-12 font-bold text-base shadow-md">
                    {isAr ? 'إرسال الرابط' : 'Send Reset Link'}
                  </Button>
                </form>
              </>
            ) : (
              <div className="text-center py-4">
                <div className="w-20 h-20 bg-success/10 rounded-full flex items-center justify-center mx-auto mb-6">
                  <CheckCircle2 className="w-10 h-10 text-success" />
                </div>
                <h2 className="text-2xl font-bold mb-3 text-foreground">{isAr ? 'تحقق من بريدك الإلكتروني' : 'Check your email'}</h2>
                <p className="text-sm text-muted-foreground mb-8 leading-relaxed">
                  {isAr 
                    ? `لقد أرسلنا تعليمات استعادة كلمة المرور إلى البريد الإلكتروني: ${email}` 
                    : `We've sent password reset instructions to: ${email}`}
                </p>
                <Button 
                  variant="outline" 
                  className="w-full h-12 font-bold"
                  onClick={() => setSubmitted(false)}
                >
                  {isAr ? 'لم أستلم البريد؟ أعد الإرسال' : "Didn't receive it? Resend"}
                </Button>
              </div>
            )}

            <div className="mt-8 text-center">
              <Link href="/login" className="text-sm font-bold text-muted-foreground hover:text-primary transition-colors flex items-center justify-center gap-2">
                <ArrowRight className={`w-4 h-4 ${isAr ? '' : 'rotate-180'}`} />
                {isAr ? 'العودة لتسجيل الدخول' : 'Back to Login'}
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
