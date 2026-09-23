import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Language, Theme, User } from '@/types/core';
import type { PluginInfo } from '@/types/plugins';

interface AppState {
  user: User | null;
  language: Language;
  theme: Theme;
  activePlugins: PluginInfo[];
  setLanguage: (lang: Language) => void;
  setTheme: (theme: Theme) => void;
  setUser: (user: User | null) => void;
  setActivePlugins: (plugins: PluginInfo[]) => void;
  clearSession: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // Bug fix (live-reproduced): this used to be a hardcoded demo user
      // ("أحمد منصور" / ahmed@trustcore.com — leftover starter-template
      // data, note the mismatched trustcore.com domain vs. this app's real
      // nexus-erp.com). Because zustand's `persist` middleware rehydrates
      // from localStorage asynchronously (after first paint, to avoid an
      // SSR/hydration mismatch), every fresh page load/navigation briefly
      // rendered that fake identity in the header/sidebar before the real
      // logged-in user's data overwrote it a few seconds later — visible on
      // every hard refresh across the dashboard. `null` is safe: every
      // consumer of `user` in dashboard/layout.tsx already guards for it
      // (`user?.avatar`, `user && (...)`, `user?.name?.[0] ?? "?"`).
      user: null,
      language: 'ar',
      theme: 'light',
      activePlugins: [],
      setLanguage: (language) => set({ language }),
      setTheme: (theme) => set({ theme }),
      setUser: (user) => set({ user }),
      setActivePlugins: (activePlugins) => set({ activePlugins }),
      clearSession: () => set({ user: null, activePlugins: [] }),
    }),
    {
      name: 'trust-core-storage',
    }
  )
);
