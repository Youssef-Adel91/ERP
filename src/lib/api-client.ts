/**
 * Mock API Client for Trust Core ERP
 */

export const apiClient = {
  get: async <T>(url: string): Promise<T> => {
    // Simulate network delay
    await new Promise((resolve) => setTimeout(resolve, 500));
    
    // Mock responses based on URL
    if (url.includes('/api/plugins')) {
      return [
        { id: 'inventory', nameAr: 'المخزون', nameEn: 'Inventory', isActive: true },
        { id: 'import', nameAr: 'الاستيراد', nameEn: 'Import', isActive: false },
      ] as any;
    }
    
    throw new Error(`Mock endpoint not implemented: ${url}`);
  },
  
  post: async <T>(url: string, data: any): Promise<T> => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    console.log(`Mock POST to ${url}`, data);
    return data as any;
  }
};
