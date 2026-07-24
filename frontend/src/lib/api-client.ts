/**
 * API Client for Omni ERP
 */

const getAuthHeaders = (): HeadersInit => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('token');
    const tenantId = localStorage.getItem('tenantId');
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    if (tenantId) {
      headers['X-Tenant-ID'] = tenantId;
    }
  }

  return headers;
};

const getBaseUrl = () => {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
};

export const apiClient = {
  get: async <T>(url: string): Promise<T> => {
    const fullUrl = url.startsWith('http') ? url : `${getBaseUrl()}${url}`;
    const response = await fetch(fullUrl, {
      method: 'GET',
      headers: getAuthHeaders(),
    });
    
    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }
    
    return response.json();
  },
  
  post: async <T>(url: string, data: any): Promise<T> => {
    const fullUrl = url.startsWith('http') ? url : `${getBaseUrl()}${url}`;
    const response = await fetch(fullUrl, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }
    
    return response.json();
  }
};
