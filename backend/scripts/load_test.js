import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';
import exec from 'k6/execution';

// --- Custom Trends for precise threshold tracking ---
const dashboardDuration = new Trend('dashboard_req_duration');
const datatableDuration = new Trend('datatable_req_duration');
const invoiceDuration = new Trend('invoice_req_duration');

// --- Configuration & Thresholds (FR-823, FR-824, FR-825) ---
export const options = {
    // Phase 8 Load Testing: 200 Concurrent VUs for 5 minutes
    stages: [
        { duration: '30s', target: 200 }, // Ramp up to 200 users
        { duration: '5m', target: 200 },  // Stay at 200 users for 5 minutes
        { duration: '30s', target: 0 },   // Ramp down to 0 users
    ],
    thresholds: {
        'dashboard_req_duration': ['p(95) < 1200'], // FR-823
        'datatable_req_duration': ['p(95) < 400'],  // FR-824
        'invoice_req_duration': ['p(95) < 600'],    // FR-825
        'http_req_failed': ['rate<0.01'],           // <1% failure rate globally
    },
};

// --- Tenant Isolation Data (FR-822 Noisy Neighbour) ---
// The heavy tenant that received 50x volume from our seeder script.
const HEAVY_TENANT_ID = '00000000-0000-0000-0000-000000000001'; 
// A pool of standard tenants running normal volumes.
const NORMAL_TENANT_IDS = [
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444'
];

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || 'test-load-token'; // Replace with a valid JWT generator if needed.

export default function () {
    // 1. Determine Tenant Context (Noisy-Neighbour Logic)
    // We force specific VUs (e.g., VU ID ending in 0) to hammer the Heavy Tenant.
    // This perfectly simulates a noisy-neighbour scenario impacting shared DB compute resources.
    let currentTenantId;
    if (exec.vu.idInTest % 10 === 0) {
        currentTenantId = HEAVY_TENANT_ID;
    } else {
        // Distribute other VUs randomly across normal tenants
        currentTenantId = NORMAL_TENANT_IDS[Math.floor(Math.random() * NORMAL_TENANT_IDS.length)];
    }

    const headers = {
        'Authorization': `Bearer ${AUTH_TOKEN}`,
        'Content-Type': 'application/json',
        'X-Tenant-ID': currentTenantId // Assuming the tenant can be overridden or inferred by the token
    };

    // 2. Scenario A: Dashboard Resolvers (Complex Aggregations)
    const dashboardPayload = JSON.stringify({
        widgets: ['sales_overview', 'inventory_valuation', 'recent_transactions']
    });
    
    let dashboardRes = http.post(`${BASE_URL}/api/v1/dashboard/resolve`, dashboardPayload, {
        headers,
        tags: { type: 'dashboard' }
    });
    
    dashboardDuration.add(dashboardRes.timings.duration);
    check(dashboardRes, {
        'Dashboard status 200': (r) => r.status === 200,
    });

    // Short think time simulating human interaction
    sleep(1);

    // 3. Scenario B: High-Volume DataTables (Sorting & Pagination on 100k+ rows)
    let datatableRes = http.get(`${BASE_URL}/api/v1/inventory/cost-layers?sort=created_at&dir=desc&limit=50&offset=0`, {
        headers,
        tags: { type: 'datatable' }
    });
    
    datatableDuration.add(datatableRes.timings.duration);
    check(datatableRes, {
        'Datatable status 200': (r) => r.status === 200,
    });

    sleep(1);

    // 4. Scenario C: Invoice Composer (Write-Heavy Multi-line Transaction)
    // Simulating the 20-Second Invoice Composer payload from Phase 6
    const invoicePayload = JSON.stringify({
        contact_id: '00000000-0000-0000-0000-000000000000', // Mock contact
        lines: [
            { item_id: '00000000-0000-0000-0000-000000000000', qty: 2, unit_price: 150.0 },
            { item_id: '00000000-0000-0000-0000-000000000000', qty: 1, unit_price: 50.0 }
        ],
        currency: 'EGP',
        issue_date: new Date().toISOString().split('T')[0]
    });

    let invoiceRes = http.post(`${BASE_URL}/api/v1/invoices`, invoicePayload, {
        headers,
        tags: { type: 'invoice' }
    });

    invoiceDuration.add(invoiceRes.timings.duration);
    check(invoiceRes, {
        'Invoice creation status 201': (r) => r.status === 201 || r.status === 200,
    });

    // Pacing loop
    sleep(Math.random() * 2 + 1); // Random sleep between 1-3 seconds
}
