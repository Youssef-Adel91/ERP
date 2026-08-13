import type { Metadata } from "next";
import { IBM_Plex_Sans_Arabic, JetBrains_Mono, Manrope, Inter } from "next/font/google";
import { QueryProvider } from "@/lib/query-provider";
import "./globals.css";

const plexArabic = IBM_Plex_Sans_Arabic({
  subsets: ["arabic", "latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-manrope",
});

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "المرجع الرقمي للتاجر المصري - Nexus ERP",
  description: "Enterprise Resource Planning for Egyptian Merchants",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ar" dir="rtl">
      <body
        suppressHydrationWarning
        className={`${plexArabic.variable} ${jetbrainsMono.variable} ${manrope.variable} ${inter.variable} font-sans bg-surface text-on-surface min-h-screen antialiased`}
      >
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
