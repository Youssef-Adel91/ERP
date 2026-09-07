"use client";

import { useRouter } from "next/navigation";
import { clearPortalSession } from "@/lib/portal-api-client";

/**
 * Shared header for every /portal/* page. Deliberately minimal and
 * separate from the staff dashboard's sidebar layout (app/dashboard/layout.tsx)
 * — a customer should never see internal navigation, module names, or
 * anything implying they're inside the merchant's own ERP.
 */
export function PortalHeader({ showLogout = true }: { showLogout?: boolean }) {
  const router = useRouter();

  const handleLogout = () => {
    clearPortalSession();
    router.push("/portal/login");
  };

  return (
    <header className="w-full border-b border-outline-variant bg-surface-container-lowest/80 backdrop-blur-sm sticky top-0 z-10">
      <div className="max-w-3xl mx-auto px-gutter py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-primary rounded-lg flex items-center justify-center shadow-overlay">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-5 h-5 fill-white">
              <path d="M440-80v-167l-44 43-56-56 140-140 140 140-56 56-44-43v167h-80ZM220-340l-56-56 43-44H40v-80h167l-43-44 56-56 140 140-140 140Zm520 0L600-480l140-140 56 56-43 44h167v80H753l43 44-56 56ZM480-600q-33 0-56.5-23.5T400-680q0-33 23.5-56.5T480-760q33 0 56.5 23.5T560-680q0 33-23.5 56.5T480-600Z" />
            </svg>
          </div>
          <div>
            <h1 className="font-headline-sm text-headline-sm text-primary leading-tight">بوابة العملاء</h1>
            <p className="text-body-sm text-on-surface-variant leading-tight">Nexus ERP</p>
          </div>
        </div>
        {showLogout && (
          <button
            type="button"
            onClick={handleLogout}
            className="text-body-sm text-on-surface-variant hover:text-error transition-colors flex items-center gap-1.5"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" className="w-4 h-4 fill-current">
              <path d="M200-120q-33 0-56.5-23.5T120-200v-560q0-33 23.5-56.5T200-840h280v80H200v560h280v80H200Zm440-160-56-58 102-102H360v-80h326L584-622l56-58 200 200-200 200Z" />
            </svg>
            <span>تسجيل الخروج</span>
          </button>
        )}
      </div>
    </header>
  );
}
