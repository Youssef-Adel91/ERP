export type Language = 'ar' | 'en';
export type Theme = 'light' | 'dark';

export interface User {
  id: string;
  tenantId: string;
  name: string;
  email: string;
  phone?: string;
  role: string;
  avatar?: string;
}

export interface Contact {
  id: string;
  name: string;
  type: 'client' | 'supplier' | 'employee';
  email: string;
  phone: string;
  status: 'active' | 'inactive';
}
