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
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      user: {
        id: 'usr-001',
        name: 'أحمد منصور',
        email: 'ahmed@trustcore.com',
        phone: '+20 10 1234 5678',
        role: 'مدير الحسابات',
        avatar: 'https://ui-avatars.com/api/?name=Ahmed+Mansour&background=random'
      },
      language: 'ar',
      theme: 'light',
      activePlugins: [],
      setLanguage: (language) => set({ language }),
      setTheme: (theme) => set({ theme }),
      setUser: (user) => set({ user }),
      setActivePlugins: (activePlugins) => set({ activePlugins }),
    }),
    {
      name: 'trust-core-storage',
    }
  )
);
