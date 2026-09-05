/**
 * PayTrace Operations Console Main Application
 */

const appState = {
    currentRoute: '',
    incidents: [],
    apiStatus: null,
    incidentFilter: 'ALL',
    incidentSearch: ''
};

// Utils
const utils = {
    formatDate: (isoString) => {
        if (!isoString) return '-';
        let parseString = isoString;
        if (typeof parseString === 'string' && !parseString.endsWith('Z') && !parseString.includes('+')) {
            parseString = parseString.replace(' ', 'T') + 'Z';
        }
        const d = new Date(parseString);
        return d.toLocaleString('en-US', { 
            month: 'short', day: 'numeric', 
            hour: '2-digit', minute: '2-digit'
        });
    },
    formatTime: (isoString) => {
        if (!isoString) return '-';
        let parseString = isoString;
        if (typeof parseString === 'string' && !parseString.endsWith('Z') && !parseString.includes('+')) {
            parseString = parseString.replace(' ', 'T') + 'Z';
        }
        const d = new Date(parseString);
        return d.toLocaleString('en-US', { 
            hour: '2-digit', minute: '2-digit'
        });
    },
    formatCurrency: (amount, currency) => {
        if (amount == null) return '-';
        return new Intl.NumberFormat('en-IN', { style: 'currency', currency: currency || 'INR' }).format(amount / 100);
    },
    getStatusBadge: (status) => {
        const map = {
            'OPEN': 'status-open',
            'RESOLVED': 'status-resolved',
            'CAPTURED': 'status-resolved',
            'FAILED': 'status-critical',
            'PENDING': 'status-open',
            'AUTHORIZED': 'status-neutral',
            'INFORMATIONAL': 'status-neutral',
            'REQUIRES_HUMAN_APPROVAL': 'status-open',
            'BLOCKED': 'status-critical'
        };
        const cls = map[status] || 'status-neutral';
        return `<span class="status-indicator ${cls}"><span class="status-dot"></span>${status}</span>`;
    },
    renderLoading: (msg = 'Loading...') => `<div class="loading-text">${msg}</div>`,
    renderError: (msg) => `<div class="error-msg">Error: ${msg}</div>`,
    renderEmpty: (msg) => `<div class="empty-state">${msg}</div>`
};

// Routing
function handleRoute() {
    const hash = window.location.hash || '#/';
    appState.currentRoute = hash;
    
    // Update nav active state
    document.querySelectorAll('.nav-item').forEach(el => {
        const target = el.getAttribute('data-nav');
        if (hash === '#/' && target === 'dashboard') {
            el.classList.add('active');
        } else if (hash.startsWith('#/incident') && target === 'incidents') {
            el.classList.add('active');
        } else if (hash === '#/health' && target === 'health') {
            el.classList.add('active');
        } else {
            el.classList.remove('active');
        }
    });

    const container = document.getElementById('view-container');
    const topContext = document.getElementById('top-context');
    container.innerHTML = utils.renderLoading();

    if (hash === '#/' || hash === '') {
        topContext.textContent = "Overview";
        renderDashboard(container);
    } else if (hash === '#/incidents') {
        topContext.textContent = "Incidents";
        renderIncidents(container);
    } else if (hash === '#/health') {
        topContext.textContent = "System Health";
        renderHealth(container);
    } else if (hash === '#/explorer') {
        topContext.textContent = "Order Explorer";
        renderExplorer(container);
    } else if (hash.startsWith('#/explorer/')) {
        const id = hash.split('/')[2];
        topContext.innerHTML = `Order Explorer / <span class="mono-id">${id}</span>`;
        renderExplorerDetail(container, id);
    } else if (hash === '#/checkout') {
        topContext.textContent = "Test Checkout";
        renderCheckout(container);
    } else if (hash.startsWith('#/incident/')) {
        const id = hash.split('/')[2];
        topContext.innerHTML = `Incidents / <span class="mono-id">#${id}</span>`;
        renderIncidentDetail(container, id);
    } else {
        topContext.textContent = "Not Found";
        container.innerHTML = utils.renderEmpty("View not found.");
    }
}

// Global API Status Poller
async function updateGlobalStatus() {
    const dot = document.getElementById('global-status-dot');
    const txt = document.getElementById('global-status-text');
    try {
        await api.getApiStatus();
        if (dot) dot.className = 'status-dot-global online';
        if (txt) txt.textContent = 'Online';
        appState.apiStatus = 'online';
    } catch (e) {
        if (dot) dot.className = 'status-dot-global offline';
        if (txt) txt.textContent = 'Offline';
        appState.apiStatus = 'offline';
    }
}
updateGlobalStatus();
setInterval(updateGlobalStatus, 30000);

// Views
async function renderDashboard(container) {
    try {
        const incidents = await api.getIncidents();
        
        const openIncidents = incidents.filter(i => i.status === 'OPEN');
        const resolvedIncidents = incidents.filter(i => i.status === 'RESOLVED');
        
        // Build Recent Activity by fetching audits for up to the 3 most recent incidents
        let recentActivityHtml = utils.renderEmpty("No activity available.");
        if (incidents.length > 0) {
            const recentTop3 = incidents.slice(0, 3);
            const auditPromises = recentTop3.map(i => api.getAuditTrail(i.id).catch(() => []));
            const auditsArrays = await Promise.all(auditPromises);
            
            // Flatten, sort by timestamp desc, take top 5
            const allAudits = auditsArrays.flat().sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 5);
            
            if (allAudits.length > 0) {
                recentActivityHtml = `
                    <div class="timeline">
                        ${allAudits.map(entry => {
                            const reasonStr = entry.reason || '';
                            const isAI = entry.action === 'INVESTIGATE' || reasonStr.includes('AI Recommendation') || entry.safety_classification !== 'INFORMATIONAL';
                            const actorName = isAI ? 'AI Investigator' : 'Human Operator';
                            return `
                                <div class="timeline-item">
                                    <div class="timeline-marker"></div>
                                    <div class="timeline-time">${utils.formatTime(entry.timestamp)}</div>
                                    <div class="timeline-actor">${actorName}</div>
                                    <div class="timeline-action">${entry.action.replace(/_/g, ' ')} <span class="mono-id text-subtle">#${entry.incident_id}</span></div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                `;
            }
        }

        let html = `
            <div class="content-section" style="padding: 0; background: transparent; border: none;">
                <div class="section-header">
                    <h2>OVERVIEW</h2>
                </div>
                <div class="metrics-strip">
                    <div class="metric-item">
                        <div class="metric-label">System Status</div>
                        <div class="metric-value" style="color: ${appState.apiStatus === 'online' ? 'var(--success)' : 'var(--danger)'}">
                            ${appState.apiStatus === 'online' ? 'ONLINE' : 'OFFLINE'}
                        </div>
                    </div>
                    <div class="metric-separator"></div>
                    <div class="metric-item">
                        <div class="metric-label">Open Incidents</div>
                        <div class="metric-value" style="${openIncidents.length > 0 ? 'color: var(--warning)' : 'color: var(--text-primary)'}">
                            ${openIncidents.length}
                        </div>
                    </div>
                    <div class="metric-separator"></div>
                    <div class="metric-item">
                        <div class="metric-label">Resolved</div>
                        <div class="metric-value">${resolvedIncidents.length}</div>
                    </div>
                    <div class="metric-separator"></div>
                    <div class="metric-item">
                        <div class="metric-label">Total</div>
                        <div class="metric-value">${incidents.length}</div>
                    </div>
                </div>
            </div>
            
            <div class="content-section">
                <div class="section-header">
                    <h2>Needs Attention</h2>
                </div>
                ${openIncidents.length === 0 ? utils.renderEmpty("NO OPEN INCIDENTS<br><br><span style='color: var(--text-muted)'>There are currently no unresolved incidents requiring attention.</span>") : `
                <div class="attention-list">
                    ${openIncidents.map(i => `
                        <a href="#/incident/${i.id}" class="attention-row">
                            <div class="attention-col mono-id">#${i.id}</div>
                            <div class="attention-col">
                                <div style="font-weight:500; font-size:13px">${i.incident_type.replace(/_/g, ' ')}</div>
                                <div class="mono-id text-subtle" style="font-size:12px">${i.razorpay_order_id || i.event_id}</div>
                            </div>
                            <div class="attention-col">
                                <div style="font-size:11px; color:var(--text-muted); text-transform:uppercase; margin-bottom:2px">
                                    <span style="display:inline-block; width:80px">MERCHANT</span> RAZORPAY
                                </div>
                                <div class="text-subtle" style="font-size:12px; font-weight: 500;">
                                    <span style="display:inline-block; width:80px; color:var(--warning)">${i.merchant_status}</span> 
                                    <span style="color:var(--success)">${i.razorpay_status}</span>
                                </div>
                            </div>
                            <div class="attention-col text-subtle" style="font-size:12px">${utils.formatDate(i.detected_at)}</div>
                            <div class="attention-col" style="align-items: flex-end;">
                                ${utils.getStatusBadge(i.status)}
                            </div>
                        </a>
                    `).join('')}
                </div>
                `}
            </div>

            <div class="content-section">
                <div class="section-header">
                    <h2>Recent Activity</h2>
                </div>
                ${recentActivityHtml}
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load dashboard: ${e.message}`);
    }
}

async function renderHealth(container) {
    try {
        const status = await api.getApiStatus();
        const isOnline = status && status.status === 'running';
        const statusText = isOnline ? 'ONLINE' : 'OFFLINE';
        const statusColor = isOnline ? 'var(--success)' : 'var(--danger)';
        const statusDesc = isOnline ? 'System is responding normally.' : 'System is experiencing issues.';

        let html = `
            <div class="incident-header-block">
                <h1 style="font-size:16px; margin:0; margin-bottom: 24px;">SYSTEM HEALTH</h1>
                
                <div style="margin-bottom: 24px;">
                    <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px;">API</div>
                    <div style="font-size: 20px; font-weight: 500; color: ${statusColor}; margin-bottom: 4px;">${statusText}</div>
                    <div style="font-size: 13px; color: var(--text-secondary);">${statusDesc}</div>
                </div>
            </div>
            
            <div class="content-section" style="padding: 0; background: transparent; border: none;">
                <div class="section-header">
                    <h2>SERVICE</h2>
                </div>
                <div class="comparison-grid" style="margin-bottom: 32px; grid-template-columns: 140px 1fr;">
                    <div class="comp-row">
                        <div class="comp-label">API</div>
                        <div class="comp-value-razorpay" style="padding-left: 0; color: var(--text-primary); font-weight: 500;">PayTrace API</div>
                    </div>
                    <div class="comp-row">
                        <div class="comp-label">Status</div>
                        <div class="comp-value-razorpay" style="padding-left: 0; color: ${statusColor}; font-weight: 500;">${statusText}</div>
                    </div>
                    <div class="comp-row">
                        <div class="comp-label">Endpoint</div>
                        <div class="comp-value-razorpay mono-id" style="padding-left: 0;">/</div>
                    </div>
                    <div class="comp-row">
                        <div class="comp-label">Response</div>
                        <div class="comp-value-razorpay" style="padding-left: 0;">Healthy</div>
                    </div>
                </div>
                
                <div class="section-header">
                    <h2>ENVIRONMENT</h2>
                </div>
                <div class="comparison-grid" style="margin-bottom: 32px; grid-template-columns: 140px 1fr;">
                    <div class="comp-row">
                        <div class="comp-label">Frontend</div>
                        <div class="comp-value-razorpay" style="padding-left: 0;">PayTrace Operations</div>
                    </div>
                    <div class="comp-row">
                        <div class="comp-label">API</div>
                        <div class="comp-value-razorpay" style="padding-left: 0;">Connected</div>
                    </div>
                    <div class="comp-row">
                        <div class="comp-label">Environment</div>
                        <div class="comp-value-razorpay" style="padding-left: 0;">Local</div>
                    </div>
                </div>
                
                <div class="section-header">
                    <h2>LAST CHECK</h2>
                </div>
                <div class="comparison-grid" style="margin-bottom: 32px; grid-template-columns: 140px 1fr;">
                    <div class="comp-row">
                        <div class="comp-label">Status</div>
                        <div class="comp-value-razorpay" style="padding-left: 0; border-bottom: none;">Operational</div>
                    </div>
                </div>
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load system health: ${e.message}`);
    }
}

async function renderIncidents(container) {
    try {
        if (appState.incidents.length === 0) {
            appState.incidents = await api.getIncidents();
        }
        const incidents = appState.incidents;
        
        let html = `
            <div class="incident-header-block">
                <h1 style="font-size:16px; margin:0">INCIDENTS</h1>
            </div>
            
            <div class="controls-row">
                <div class="filters">
                    <button class="filter-btn ${appState.incidentFilter === 'ALL' ? 'active' : ''}" onclick="setIncidentFilter('ALL')">ALL ${incidents.length}</button>
                    <button class="filter-btn ${appState.incidentFilter === 'OPEN' ? 'active' : ''}" onclick="setIncidentFilter('OPEN')">OPEN ${incidents.filter(i=>i.status==='OPEN').length}</button>
                    <button class="filter-btn ${appState.incidentFilter === 'RESOLVED' ? 'active' : ''}" onclick="setIncidentFilter('RESOLVED')">RESOLVED ${incidents.filter(i=>i.status==='RESOLVED').length}</button>
                </div>
                <div>
                    <input type="text" id="incident-search" class="search-input" placeholder="Search ID, Order, Payment..." value="${appState.incidentSearch}" oninput="setIncidentSearch(this.value)">
                </div>
            </div>
            
            <div id="incidents-table-container" class="data-table-container">
                ${renderIncidentsTableHtml()}
            </div>
        `;
        container.innerHTML = html;
        
        // Focus the search input if it had a value to keep typing smooth
        const searchInput = document.getElementById('incident-search');
        if (searchInput && appState.incidentSearch) {
            searchInput.focus();
            const val = searchInput.value;
            searchInput.value = '';
            searchInput.value = val;
        }
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load incidents: ${e.message}`);
    }
}

function renderIncidentsTableHtml() {
    let filtered = appState.incidents;
    
    // Apply status filter
    if (appState.incidentFilter !== 'ALL') {
        filtered = filtered.filter(i => i.status === appState.incidentFilter);
    }
    
    // Apply search filter
    if (appState.incidentSearch) {
        const query = appState.incidentSearch.toLowerCase();
        filtered = filtered.filter(i => {
            return (i.id && i.id.toString().includes(query)) ||
                   (i.incident_type && i.incident_type.toLowerCase().includes(query)) ||
                   (i.razorpay_order_id && i.razorpay_order_id.toLowerCase().includes(query)) ||
                   (i.razorpay_payment_id && i.razorpay_payment_id.toLowerCase().includes(query)) ||
                   (i.event_id && i.event_id.toLowerCase().includes(query));
        });
    }

    if (filtered.length === 0) {
        return utils.renderEmpty("No incidents found.");
    }
    
    return `
        <table class="data-table">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Type / Severity</th>
                    <th>Order / Payment</th>
                    <th>Merchant State</th>
                    <th>Razorpay State</th>
                    <th>Status</th>
                    <th>Detected</th>
                </tr>
            </thead>
            <tbody>
                ${filtered.map(i => `
                    <tr onclick="window.location.hash='#/incident/${i.id}'">
                        <td class="mono-id">#${i.id}</td>
                        <td>${i.incident_type.replace(/_/g, ' ')}</td>
                        <td class="mono-id" style="font-size:12px">
                            ${i.razorpay_order_id || '-'}<br>
                            <span class="text-subtle">${i.razorpay_payment_id || '-'}</span>
                        </td>
                        <td>${i.merchant_status}</td>
                        <td>${i.razorpay_status}</td>
                        <td>${utils.getStatusBadge(i.status)}</td>
                        <td class="text-subtle" style="font-size:12px">${utils.formatDate(i.detected_at)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// Global actions for filters
window.setIncidentFilter = (filter) => {
    appState.incidentFilter = filter;
    renderIncidents(document.getElementById('view-container'));
};

window.setIncidentSearch = (query) => {
    appState.incidentSearch = query;
    const tableContainer = document.getElementById('incidents-table-container');
    if (tableContainer) {
        tableContainer.innerHTML = renderIncidentsTableHtml();
    }
};

async function renderIncidentDetail(container, id) {
    try {
        const incident = await api.getIncident(id);
        
        let html = `
            <div class="incident-header-block" style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class="incident-title-row">
                        <h1 class="incident-title mono-id">INCIDENT #${incident.id}</h1>
                    </div>
                    <div style="font-weight:500; font-size:14px; margin-bottom:4px; color: var(--text-primary);">
                        ${(incident.incident_type || '').replace(/_/g, ' ')}
                    </div>
                    <div class="meta-text mono-id">
                        ${incident.razorpay_order_id || incident.event_id || 'N/A'} &middot; Detected ${utils.formatDate(incident.detected_at)}
                    </div>
                </div>
                <div>
                    ${utils.getStatusBadge(incident.status)}
                </div>
            </div>
            
            <div class="content-section" style="padding: 0; background: transparent; border: none;">
                <div class="section-header">
                    <h2>PAYMENT STATE</h2>
                </div>
                
                <div class="comparison-grid">
                    <div class="comp-header">STATE</div>
                    <div class="comp-header comp-value-merchant">MERCHANT</div>
                    <div class="comp-header comp-value-razorpay">RAZORPAY</div>
                    
                    <div class="comp-row">
                        <div class="comp-label">State</div>
                        <div class="comp-value-merchant" style="font-weight: 500; ${(incident.merchant_status || '') !== (incident.razorpay_status || '') ? 'color: var(--warning)' : 'color: var(--text-primary)'}">
                            ${incident.merchant_status || '—'}
                        </div>
                        <div class="comp-value-razorpay" style="font-weight: 500; ${(incident.razorpay_status || '') === 'CAPTURED' ? 'color: var(--success)' : 'color: var(--text-primary)'}">
                            ${incident.razorpay_status || '—'}
                        </div>
                    </div>
                    
                    <div class="comp-row">
                        <div class="comp-label">Order</div>
                        <div class="comp-value-merchant mono-id">${incident.razorpay_order_id || '—'}</div>
                        <div class="comp-value-razorpay mono-id">—</div>
                    </div>
                    
                    <div class="comp-row">
                        <div class="comp-label">Payment</div>
                        <div class="comp-value-merchant mono-id">—</div>
                        <div class="comp-value-razorpay mono-id">${incident.razorpay_payment_id || '—'}</div>
                    </div>
                    
                    <div class="comp-row">
                        <div class="comp-label">Amount</div>
                        <div class="comp-value-merchant">—</div>
                        <div class="comp-value-razorpay">${utils.formatCurrency(incident.amount, incident.currency)}</div>
                    </div>

                    ${(incident.merchant_status || '') !== (incident.razorpay_status || '') ? `
                        <div class="mismatch-banner" style="border-left: 2px solid var(--danger); padding-left: 12px; margin-top: 24px;">
                            <div style="font-weight:600; margin-bottom:2px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;">STATE MISMATCH</div>
                            <div style="color: var(--text-secondary);">Merchant state differs from Razorpay payment state.</div>
                        </div>
                    ` : ''}
                </div>
            </div>
            
            <div id="ai-section">
                <div class="content-section">
                    <div class="section-header">
                        <h2>INVESTIGATION</h2>
                    </div>
                    ${utils.renderLoading('Loading investigation...')}
                </div>
            </div>
            
            <div id="audit-section">
                <div class="content-section">
                    <div class="section-header">
                        <h2>ACTIVITY</h2>
                    </div>
                    ${utils.renderLoading('Loading activity...')}
                </div>
            </div>
        `;
        container.innerHTML = html;
        
        renderAnalysisSection(document.getElementById('ai-section'), incident);
        renderAuditSection(document.getElementById('audit-section'), incident);
        
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load incident #${id}: ${e.message}`);
    }
}

async function renderAnalysisSection(container, incident) {
    try {
        let analysis;
        try {
            analysis = await api.getAnalysis(incident.id);
        } catch (e) {
            if (e.status === 404) {
                if (incident.status === 'OPEN') {
                    container.innerHTML = `
                        <div class="content-section">
                            <div class="section-header">
                                <h2>INVESTIGATION</h2>
                            </div>
                            <div class="investigation-meta">Generated by AI &middot; Advisory only</div>
                            ${utils.renderLoading('Generating investigation...')}
                        </div>
                    `;
                    analysis = await api.generateAnalysis(incident.id);
                } else {
                    container.innerHTML = `
                        <div class="content-section">
                            <div class="section-header">
                                <h2>INVESTIGATION</h2>
                            </div>
                            <div class="empty-state">No investigation generated before resolution.</div>
                        </div>
                    `;
                    return;
                }
            } else {
                throw e;
            }
        }
        
        container.innerHTML = `
            <div class="content-section" style="padding: 0; background: transparent; border: none;">
                <div class="section-header" style="margin-bottom: 2px;">
                    <h2>INVESTIGATION</h2>
                </div>
                <div class="investigation-meta" style="margin-bottom: 24px; font-weight: 500;">Generated by AI &middot; Advisory only</div>
                
                <div class="investigation-grid mb-8">
                    <div>
                        <div class="inv-section-title">Summary</div>
                        <div class="inv-text" style="color: var(--text-secondary);">${analysis.summary || '—'}</div>
                    </div>
                    <div>
                        <div class="inv-section-title">Likely Cause</div>
                        <div class="inv-text mb-4" style="color: var(--text-secondary);">${analysis.likely_cause || '—'}</div>
                        <div class="inv-section-title">Impact</div>
                        <div class="inv-text" style="color: var(--text-secondary);">${analysis.impact || '—'}</div>
                    </div>
                </div>
                
                <div class="section-header">
                    <h2>RECOMMENDATION</h2>
                </div>
                
                <div class="inv-section-title mt-4">${analysis.action_type || '—'}</div>
                <div class="inv-text" style="color: var(--text-primary); font-weight: 500;">${analysis.recommended_action || '—'}</div>
                
                <div class="safety-block" style="border-left: 2px solid var(--accent); border-radius: 0; background: var(--bg-surface);">
                    <div class="safety-header" style="color: var(--accent);">REQUIRES HUMAN APPROVAL</div>
                    <div style="color:var(--text-secondary)">
                        AI recommendation only. No automated state mutation will be performed without human confirmation.
                    </div>
                </div>
            </div>
        `;
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load AI Investigation: ${e.message}`);
    }
}

async function renderAuditSection(container, incident) {
    try {
        const audit = await api.getAuditTrail(incident.id);
        
        let resolutionHtml = '';
        if (incident.status === 'OPEN') {
            resolutionHtml = `
                <div class="resolution-area">
                    <div class="section-header">
                        <h2>RESOLUTION</h2>
                    </div>
                    <div class="resolution-text">
                        Review the recommendation and resolve the incident when appropriate.
                    </div>
                    <button id="btn-resolve" class="btn" onclick="handleResolve(${incident.id})">Mark as Resolved</button>
                    <div id="resolve-error" class="error-msg"></div>
                </div>
            `;
        } else {
            resolutionHtml = `
                <div class="resolution-area">
                    <div class="section-header">
                        <h2>RESOLUTION</h2>
                    </div>
                    <div class="resolution-text" style="color:var(--color-resolved); font-weight:500;">
                        Incident resolution recorded.
                    </div>
                </div>
            `;
        }
        
        let html = `
            <div class="content-section" style="padding: 0; background: transparent; border: none;">
                <div class="section-header">
                    <h2>ACTIVITY</h2>
                </div>
                
                ${audit.length === 0 ? utils.renderEmpty('No activity available.') : `
                    <div class="timeline">
                        ${audit.map(entry => {
                            const reasonStr = entry.reason || '';
                            const isAI = entry.action === 'INVESTIGATE' || reasonStr.includes('AI Recommendation') || entry.safety_classification !== 'INFORMATIONAL';
                            const actorName = isAI ? 'AI Investigator' : (entry.action === 'DETECT' ? 'System' : 'Human Operator');
                            
                            return `
                            <div class="timeline-item">
                                <div class="timeline-marker"></div>
                                <div class="timeline-time">${utils.formatTime(entry.timestamp)}</div>
                                <div class="timeline-actor">${actorName}</div>
                                <div class="timeline-action">${entry.action.replace(/_/g, ' ')}</div>
                                <div class="timeline-reason">${reasonStr}</div>
                            </div>
                            `;
                        }).join('')}
                    </div>
                `}
                
                ${resolutionHtml}
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load Audit Trail: ${e.message}`);
    }
}

// Actions
window.handleResolve = async (incidentId) => {
    const btn = document.getElementById('btn-resolve');
    const errDiv = document.getElementById('resolve-error');
    btn.disabled = true;
    btn.innerHTML = 'Resolving...';
    errDiv.innerHTML = '';
    
    try {
        await api.resolveIncident(incidentId);
        // Force refresh from backend
        appState.incidents = []; 
        handleRoute(); // refresh
    } catch (e) {
        btn.disabled = false;
        btn.innerHTML = 'Mark as Resolved';
        errDiv.innerHTML = e.message;
    }
};

// --- Order Explorer Views ---

async function renderExplorer(container) {
    try {
        const orders = await api.getMerchantOrders();
        let html = `
            <div class="incident-header-block">
                <h1 style="font-size:16px; margin:0">ORDER EXPLORER</h1>
            </div>
            <div class="data-table-container">
                ${orders.length === 0 ? utils.renderEmpty("No orders found.") : `
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Order ID</th>
                                <th>Amount</th>
                                <th>Merchant Status</th>
                                <th>Created At</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${orders.map(o => `
                                <tr onclick="window.location.hash='#/explorer/${o.razorpay_order_id}'">
                                    <td class="mono-id">${o.razorpay_order_id}</td>
                                    <td>${utils.formatCurrency(o.amount, o.currency)}</td>
                                    <td>${utils.getStatusBadge(o.status)}</td>
                                    <td class="text-subtle" style="font-size:12px">${utils.formatDate(o.created_at)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                `}
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load orders: ${e.message}`);
    }
}

async function renderExplorerDetail(container, orderId) {
    try {
        const events = await api.getMerchantOrderEvents(orderId);
        let html = `
            <div class="incident-header-block" style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div class="incident-title-row">
                        <h1 class="incident-title mono-id">ORDER ${orderId}</h1>
                    </div>
                </div>
                <div>
                    <a href="#/explorer" class="btn" style="background: var(--bg-surface); border: 1px solid var(--border-color); color: var(--text-primary);">Back to Explorer</a>
                </div>
            </div>
            
            <div class="content-section" style="padding: 0; background: transparent; border: none;">
                <div class="section-header">
                    <h2>EVENT HISTORY</h2>
                </div>
                
                ${events.length === 0 ? utils.renderEmpty("No webhook events recorded for this order.") : `
                    <div class="timeline">
                        ${events.map(e => `
                            <div class="timeline-item">
                                <div class="timeline-marker"></div>
                                <div class="timeline-time">${utils.formatTime(e.received_at)}</div>
                                <div class="timeline-actor mono-id" style="font-size:12px">${e.event_id}</div>
                                <div class="timeline-action">${e.event_type}</div>
                                <div class="timeline-reason text-subtle" style="font-size:12px">
                                    Created: ${utils.formatDate(new Date(e.created_at * 1000).toISOString())} &middot; Received: ${utils.formatDate(e.received_at)}<br>
                                    Payment ID: <span class="mono-id">${e.razorpay_payment_id || 'N/A'}</span> &middot; Status: <span class="mono-id">${e.payment_status || 'N/A'}</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `}
            </div>
        `;
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load order events: ${e.message}`);
    }
}

// --- Checkout View ---

async function renderCheckout(container) {
    let config = null;
    try {
        config = await api.getConfig();
    } catch (e) {
        container.innerHTML = utils.renderError(`Failed to load config: ${e.message}`);
        return;
    }
    
    let html = `
        <div class="incident-header-block">
            <h1 style="font-size:16px; margin:0">TEST CHECKOUT</h1>
        </div>
        
        <div class="content-section">
            <div class="section-header">
                <h2>CREATE PAYMENT</h2>
            </div>
            <div style="margin-bottom: 24px; color: var(--text-secondary);">
                This will create a real Razorpay Test Mode order and open the checkout widget. 
                Webhook events will be delivered to PayTrace.
            </div>
            
            <div style="margin-bottom: 16px;">
                <label style="display:block; margin-bottom:8px; font-weight:500;">Amount (INR)</label>
                <input type="number" id="checkout-amount" value="500" class="search-input" style="max-width:200px;">
            </div>
            
            <button id="btn-checkout" class="btn" onclick="handleCheckout()">Pay Now</button>
            <div id="checkout-msg" style="margin-top:16px; color:var(--text-secondary);"></div>
        </div>
    `;
    container.innerHTML = html;
    
    window.handleCheckout = async () => {
        const btn = document.getElementById('btn-checkout');
        const msgDiv = document.getElementById('checkout-msg');
        const amountInput = document.getElementById('checkout-amount');
        const amount = parseInt(amountInput.value) * 100; // to paise
        
        btn.disabled = true;
        btn.textContent = 'Creating Order...';
        msgDiv.textContent = '';
        msgDiv.className = 'text-subtle';
        
        try {
            const order = await api.createMerchantOrder({ amount, currency: 'INR' });
            msgDiv.innerHTML = `Order created: <span class="mono-id">${order.razorpay_order_id}</span>. Opening checkout...`;
            
            const options = {
                key: config.razorpay_key_id,
                amount: order.amount,
                currency: order.currency,
                name: 'PayTrace Demo',
                description: 'Test Transaction',
                order_id: order.razorpay_order_id,
                handler: function (response) {
                    msgDiv.innerHTML = `<span style="color:var(--success)">Payment Successful!</span> Payment ID: <span class="mono-id">${response.razorpay_payment_id}</span>`;
                    btn.disabled = false;
                    btn.textContent = 'Pay Again';
                },
                prefill: {
                    name: 'Test User',
                    email: 'test@example.com',
                    contact: '9999999999'
                },
                theme: {
                    color: '#3399cc'
                }
            };
            
            // Wait a tick for UI update, then open
            setTimeout(() => {
                const rzp = new window.Razorpay(options);
                rzp.on('payment.failed', function (response) {
                    msgDiv.innerHTML = `<span style="color:var(--danger)">Payment Failed!</span> Reason: ${response.error.description}`;
                    btn.disabled = false;
                    btn.textContent = 'Retry Payment';
                });
                rzp.open();
            }, 500);
            
        } catch (e) {
            btn.disabled = false;
            btn.textContent = 'Pay Now';
            msgDiv.className = 'error-msg';
            msgDiv.textContent = e.message;
        }
    };
}

// Init
window.addEventListener('hashchange', handleRoute);
handleRoute();
