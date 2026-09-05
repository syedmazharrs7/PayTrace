/**
 * API client for PayTrace
 */

const API_BASE = '/api';

class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
    }
}

async function fetchApi(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        if (!response.ok) {
            let errorMsg = `API Error: ${response.status} ${response.statusText}`;
            try {
                const errorData = await response.json();
                if (errorData.detail) {
                    errorMsg = errorData.detail;
                }
            } catch (e) {
                // Ignore json parsing errors on error response
            }
            throw new ApiError(errorMsg, response.status);
        }
        
        return await response.json();
    } catch (error) {
        if (error instanceof ApiError) {
            throw error;
        }
        throw new Error(`Network Error: ${error.message}`);
    }
}

const api = {
    // Health check
    getApiStatus: () => fetchApi('/'),
    
    // Incidents
    getIncidents: () => fetchApi(`${API_BASE}/incidents`),
    getIncident: (id) => fetchApi(`${API_BASE}/incidents/${id}`),
    
    // Analysis
    getAnalysis: (id) => fetchApi(`${API_BASE}/incidents/${id}/analysis`),
    generateAnalysis: (id) => fetchApi(`${API_BASE}/incidents/${id}/analysis`, { method: 'POST' }),
    
    // Audit Trail
    getAuditTrail: (id) => fetchApi(`${API_BASE}/incidents/${id}/audit`),
    
    // Resolution
    resolveIncident: (id) => fetchApi(`${API_BASE}/incidents/${id}/resolve`, { method: 'POST' }),
    
    // Merchant Orders (Explorer & Checkout)
    getMerchantOrders: () => fetchApi(`${API_BASE}/merchant/orders`),
    getMerchantOrderEvents: (razorpay_order_id) => fetchApi(`${API_BASE}/merchant/orders/${razorpay_order_id}/events`),
    createMerchantOrder: (data) => fetchApi(`${API_BASE}/merchant/orders`, { method: 'POST', body: JSON.stringify(data) }),
    
    // Config
    getConfig: () => fetchApi(`${API_BASE}/config`)
};
