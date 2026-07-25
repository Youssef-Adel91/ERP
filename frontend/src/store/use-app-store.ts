import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Language, Theme, User } from '@/types/core';
import type { PluginInfo } from '@/types/plugins';
import { apiClient } from '@/lib/api-client';

// ── Master Plugin Registry ────────────────────────────────────────────────────
// This is the single source of truth for ALL possible plugins in Omni ERP.
// The Zustand store simply filters this list down to what the tenant has active.
export const ALL_PLUGINS: PluginInfo[] = [
  { id: 'accounting',  nameAr: 'الحسابات',        nameEn: 'Accounting',    isActive: false, icon: 'Wallet' },
  { id: 'contacts',    nameAr: 'جهات الاتصال',    nameEn: 'Contacts',      isActive: false, icon: 'Users' },
  { id: 'inventory',   nameAr: 'المخزن',           nameEn: 'Inventory',     isActive: false, icon: 'Package' },
  { id: 'shipping',    nameAr: 'الشحن',            nameEn: 'Shipping',      isActive: false, icon: 'Truck' },
  { id: 'pos',         nameAr: 'نقطة البيع',       nameEn: 'Point of Sale', isActive: false, icon: 'ShoppingCart' },
  { id: 'ecommerce',   nameAr: 'التجارة الإلكترونية', nameEn: 'E-Commerce', isActive: false, icon: 'Globe' },
  { id: 'assets',      nameAr: 'الأصول الثابتة',  nameEn: 'Fixed Assets',  isActive: false, icon: 'Landmark' },
];

interface AppState {
  user: User | null;
  language: Language;
  theme: Theme;
  activePlugins: PluginInfo[];
  setLanguage: (lang: Language) => void;
  setTheme: (theme: Theme) => void;
  setUser: (user: User | null) => void;
  setActivePlugins: (plugins: PluginInfo[]) => void;
  /** Fetches active plugin slugs from the API and hydrates the store. */
  fetchActivePlugins: () => Promise<void>;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      user: null,
      language: 'ar',
      theme: 'light',
      activePlugins: [],
      setLanguage: (language) => set({ language }),
      setTheme: (theme) => set({ theme }),
      setUser: (user) => set({ user }),
      setActivePlugins: (activePlugins) => set({ activePlugins }),

      fetchActivePlugins: async () => {
        try {
          const res = await apiClient.get<{ active_plugins: string[] }>(
            '/system/plugins/active'
          );
          const hydrated: PluginInfo[] = res.active_plugins
            .map((slug) => ALL_PLUGINS.find((p) => p.id === slug))
            .filter((p): p is PluginInfo => Boolean(p))
            .map((p) => ({ ...p, isActive: true }));
          set({ activePlugins: hydrated });
        } catch {
          // Silently keep existing state if the network call fails
        }
      },
    }),
    {
      name: 'omni-erp-storage',
      // Only persist user + preferences — plugins are always re-fetched live
      partialize: (state) => ({
        user: state.user,
        language: state.language,
        theme: state.theme,
      }),
    }
  )
);

