let earningsChart = null;

document.addEventListener('DOMContentLoaded', () => {
    applyRoleRestrictions();
    refreshData();
    setupForms();
    if (window.lucide) {
        lucide.createIcons();
    }
});

function applyRoleRestrictions() {
    if (window.userRole === 'investor' || window.userRole === 'client') {
        // Hide admin sections from sidebar
        const adminOnlyIds = ['nav-investors', 'nav-audit', 'nav-expenses'];
        if (window.userRole === 'client') adminOnlyIds.push('nav-clients');
        
        adminOnlyIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
        
        // Hide action buttons
        const actionButtons = document.querySelectorAll('header .actions button');
        actionButtons.forEach(btn => btn.style.display = 'none');
    }
}

function setupForms() {
    const forms = [
        { id: 'client-form', url: '/api/clients', method: 'POST', modal: 'client-modal' },
        { id: 'loan-form', url: '/api/loans', method: 'POST', modal: 'loan-modal' },
        { id: 'payment-form', url: (data) => `/api/loans/${data.loan_id}/payments`, method: 'POST', modal: 'payment-modal' },
        { id: 'expense-form', url: '/api/expenses', method: 'POST', modal: 'expense-modal' },
        { id: 'investor-form', url: '/api/investors', method: 'POST', modal: 'investor-modal' },
    ];

    forms.forEach(f => {
        document.getElementById(f.id).addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            const url = typeof f.url === 'function' ? f.url(data) : f.url;
            
            try {
                const res = await fetch(url, {
                    method: f.method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                if (res.ok) {
                    closeModal(f.modal);
                    refreshData();
                    e.target.reset();
                }
            } catch (err) { console.error(err); }
        });
    });

    // Quota Edit Form
    document.getElementById('quota-edit-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('edit-quota-id').value;
        const data = {
            amount: parseFloat(document.getElementById('edit-quota-amount').value),
            due_date: document.getElementById('edit-quota-date').value
        };
        try {
            const res = await fetch(`/api/quotas/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            if (res.ok) {
                closeModal('quota-edit-modal');
                refreshData();
                alert('Cuota actualizada');
            }
        } catch (err) { console.error(err); }
    });

    // Attachment Form
    document.getElementById('attachment-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const loanId = document.getElementById('attachment-loan-id').value;
        const formData = new FormData();
        formData.append('label', document.getElementById('attachment-label').value);
        formData.append('file', document.getElementById('attachment-file').files[0]);

        try {
            const res = await fetch(`/api/loans/${loanId}/attachments`, {
                method: 'POST',
                body: formData
            });
            if (res.ok) {
                closeModal('attachment-modal');
                alert('Archivo subido');
                refreshData();
            }
        } catch (err) { console.error(err); }
    });
}

async function refreshData() {
    await updateStats();
    await updateClientsList();
    await updateLoansList();
    await updateAuditLogs();
    await updateExpensesList();
    await updateInvestorsList();
}

async function updateStats() {
    const res = await fetch('/api/dashboard-stats');
    const data = await res.json();
    
    if (data.role === 'client') {
        document.getElementById('section-title').textContent = `Bienvenido, ${data.client_name}`;
        const grid = document.querySelector('.stats-grid');
        grid.innerHTML = `
            <div class="stat-card"><h3>Préstamos Activos</h3><div class="value" style="color: var(--accent);">${data.total_loans}</div></div>
            <div class="stat-card"><h3>Total Pagado</h3><div class="value" style="color: var(--success);">$${data.total_paid.toLocaleString()}</div></div>
            <div class="stat-card"><h3>Saldo Pendiente</h3><div class="value" style="color: var(--danger);">$${data.total_pending.toLocaleString()}</div></div>
        `;
        const chartGrid = document.querySelector('.chart-container').parentElement;
        if (chartGrid) chartGrid.style.display = 'none';
    } else {
        document.getElementById('stat-clients').textContent = data.total_clients;
        document.getElementById('stat-lent').textContent = `$${data.total_lent.toLocaleString()}`;
        document.getElementById('stat-mora').textContent = `$${data.total_mora.toLocaleString()}`;
        if (document.getElementById('stat-profit')) document.getElementById('stat-profit').textContent = `$${data.net_profit.toLocaleString()}`;
        if (document.getElementById('stat-expenses')) document.getElementById('stat-expenses').textContent = `$${data.total_expenses.toLocaleString()}`;
        updateChart(data.projections);
        updateProfitChart(data.profitability_trend);
    }
}

let profitChart = null;
function updateProfitChart(trend) {
    const canvas = document.getElementById('profitChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (profitChart) profitChart.destroy();

    profitChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: trend.map(t => t.month),
            datasets: [
                { label: 'Intereses Ganados', data: trend.map(t => t.income), backgroundColor: '#16a34a' },
                { label: 'Gastos', data: trend.map(t => t.expenses), backgroundColor: '#dc2626' }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true } }
        }
    });
}

function updateChart(projections) {
    const canvas = document.getElementById('earningsChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    
    if (earningsChart) {
        earningsChart.destroy();
    }
    
    // Ensure we have data or show zeroed chart
    const labels = projections && projections.length ? projections.map(p => p.month) : ['Sin datos'];
    const data = projections && projections.length ? projections.map(p => p.amount) : [0];

    earningsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Cobros Proyectados ($)',
                data: data,
                borderColor: '#2563eb',
                backgroundColor: 'rgba(37, 99, 235, 0.05)',
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                pointBackgroundColor: '#2563eb',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { 
                    beginAtZero: true, 
                    grid: { color: '#f1f5f9' }, 
                    ticks: { 
                        color: '#64748b', 
                        font: { size: 11 },
                        callback: function(value) { return '$' + value.toLocaleString(); }
                    } 
                },
                x: { 
                    grid: { display: false }, 
                    ticks: { color: '#64748b', font: { size: 11 } } 
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0f172a',
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: function(context) { return 'Cobro: $' + context.parsed.y.toLocaleString(); }
                    }
                }
            }
        }
    });
}

async function updateClientsList() {
    const res = await fetch('/api/clients');
    const clients = await res.json();
    const tbody = document.querySelector('#clients-table tbody');
    const select = document.getElementById('client-select');
    tbody.innerHTML = '';
    select.innerHTML = '<option value="">Seleccione un cliente...</option>';
    clients.forEach(c => {
        tbody.innerHTML += `<tr>
            <td>${c.name}</td>
            <td>${c.phone || '-'} <button onclick="shareWhatsApp('${c.name}', '${c.phone}', 0, 'general')" style="background:none; border:none; color:#25d366; cursor:pointer; padding:0;"><i data-lucide="message-circle" style="width:14px;"></i></button></td>
            <td>${c.email || '-'}</td>
            <td>${c.address || '-'}</td>
        </tr>`;
        select.innerHTML += `<option value="${c.id}">${c.name}</option>`;
    });
    if (window.lucide) lucide.createIcons();
}

async function updateLoansList() {
    const res = await fetch('/api/loans');
    const loans = await res.json();
    const overviewTbody = document.querySelector('#recent-loans-table tbody');
    const allLoansTbody = document.querySelector('#loans-table tbody');
    overviewTbody.innerHTML = '';
    allLoansTbody.innerHTML = '';
    loans.sort((a, b) => b.id - a.id);
    loans.forEach(l => {
        const row = `
            <tr>
                <td><a href="#" onclick="showClientDetail(${l.client_id})" style="color: #2563eb; font-weight: 600;">${l.client_name}</a></td>
                <td>$${l.amount.toLocaleString()}</td>
                <td>${l.interest_rate}%</td>
                <td><span class="status-badge status-${l.status}">${l.status.toUpperCase()}</span></td>
                <td>
                    <div style="display: flex; gap: 0.3rem;">
                        ${window.userRole === 'admin' ? `<button onclick="openPaymentModal(${l.id}, ${l.amount * (l.interest_rate/100)})" style="padding: 0.3rem 0.5rem; width: auto;">Pagar</button>` : ''}
                        <button onclick="downloadContract(${l.id})" class="btn-outline" style="padding: 0.3rem 0.5rem; width: auto;">Contrato</button>
                    </div>
                </td>
            </tr>`;
        overviewTbody.innerHTML += row;
        allLoansTbody.innerHTML += `
            <tr data-status="${l.status}" data-late="${l.is_late}" data-today="${l.due_today}">
                <td>${l.id}</td>
                <td>${l.client_name} ${l.is_late ? '🔴' : ''}</td>
                <td>$${l.amount.toLocaleString()}</td>
                <td>${l.interest_rate}%</td>
                <td><span class="status-badge status-${l.status}">${l.status.toUpperCase()}</span></td>
                <td>
                    <button onclick="downloadContract(${l.id})" class="btn-outline" style="padding: 0.2rem 0.4rem; width: auto; font-size: 0.7rem;">Contrato</button>
                </td>
            </tr>`;
    });
}

async function updateAuditLogs() {
    const res = await fetch('/api/audit-logs');
    const logs = await res.json();
    const tbody = document.querySelector('#audit-table tbody');
    tbody.innerHTML = '';
    logs.forEach(log => {
        tbody.innerHTML += `<tr><td>${log.time}</td><td><span style="font-weight: 700;">${log.action}</span></td><td>${log.details}</td></tr>`;
    });
}

async function showClientDetail(clientId) {
    const res = await fetch(`/api/clients/${clientId}/history`);
    const data = await res.json();
    showSection('client-detail');
    document.getElementById('detail-client-name').textContent = data.name;
    const container = document.getElementById('loan-history');
    container.innerHTML = '';
    
    data.loans.forEach(loan => {
        let quotasHtml = loan.quotas.map(q => {
            let lateInfo = '';
            let dueD = new Date(q.due);
            let now = new Date();
            let daysLate = Math.floor((now - dueD) / (1000 * 60 * 60 * 24));
            if (daysLate > 0 && q.status !== 'paid') {
                let fee = daysLate * (loan.late_fee_per_day || 0);
                lateInfo = `<span style="color:var(--danger); font-size: 0.75rem;">(+${daysLate}d mora: $${fee})</span>`;
            }
            
            let paidText = q.paid_amount > 0 && q.status !== 'paid' ? `<br><small style="color:var(--text-muted)">Abonado: $${q.paid_amount.toLocaleString()}</small>` : '';

            return `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; border-bottom: 1px solid var(--border); font-size: 0.9rem;">
                <div>
                    <span>Cuota ${q.number} (${q.due})</span><br>
                    <span style="font-weight:600">$${q.amount.toLocaleString()}</span> 
                    <small style="color:var(--text-muted)">(Cap: $${q.principal.toLocaleString()} | Int: $${q.interest.toLocaleString()})</small>
                    ${lateInfo}
                    ${paidText}
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span class="status-badge status-${q.status}">${q.status}</span>
                    <button onclick="openQuotaEdit(${q.id}, ${q.amount}, '${q.due}')" class="btn-outline" style="padding: 0.2rem 0.4rem; width: auto; font-size: 0.7rem;">Editar</button>
                </div>
            </div>`;
        }).join('');

        let attachmentsHtml = loan.attachments.map(a => `
            <a href="/uploads/${a.filename}" target="_blank" style="display: block; padding: 0.4rem; font-size: 0.8rem; color: #2563eb;">📎 ${a.label}</a>
        `).join('');
        
        let paymentsHtml = (loan.payments || []).map(p => `
            <div style="padding: 0.4rem; font-size: 0.8rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between;">
                <div>
                    <span style="font-weight:600;">${p.date}</span><br>
                    <span>$${p.amount.toLocaleString()}</span>
                    <small style="color:var(--text-muted)">(Cap: $${p.principal_paid.toLocaleString()} | Int: $${p.interest_paid.toLocaleString()})</small>
                </div>
                <button onclick="downloadReceipt(${p.id})" style="padding: 0.1rem 0.4rem; width: auto; font-size: 0.7rem; background: var(--accent); color: white; border-radius: 0.2rem; border: none; cursor: pointer;">PDF</button>
            </div>
        `).join('');
        if(paymentsHtml === '') paymentsHtml = '<p style="font-size: 0.75rem; color: var(--text-muted);">Sin pagos registrados</p>';


        container.innerHTML += `
            <div class="stat-card" style="margin-bottom: 2rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                    <div>
                        <h4 style="font-size: 1.1rem;">Préstamo #${loan.id} (${loan.type.toUpperCase()})</h4>
                        <p style="color: var(--text-muted); font-size: 0.85rem;">Monto: $${loan.amount.toLocaleString()} | Tasa: ${loan.interest}%</p>
                    </div>
                    <div style="display: flex; gap: 0.5rem;">
                        <button onclick="downloadContract(${loan.id})" class="btn-outline" style="width: auto; padding: 0.4rem 0.8rem; font-size: 0.8rem;">📄 Contrato</button>
                        <button onclick="openAttachmentModal(${loan.id})" class="btn-outline" style="width: auto; padding: 0.4rem 0.8rem; font-size: 0.8rem;">+ Doc</button>
                        <button onclick="shareWhatsApp('${data.name}', '${data.phone}', ${loan.amount}, 'loan')" style="width: auto; padding: 0.4rem 0.8rem; background: #25d366; font-size: 0.8rem; color: white;">WhatsApp</button>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                    <div style="background: #f8fafc; border-radius: 0.5rem; padding: 0.5rem;">${quotasHtml}</div>
                    <div style="background: #f1f5f9; border-radius: 0.5rem; padding: 1rem;">
                        <h5 style="font-size: 0.8rem; text-transform: uppercase; margin-bottom: 0.5rem;">Pagos y Recibos</h5>
                        <div style="margin-bottom: 1rem;">${paymentsHtml}</div>
                        <h5 style="font-size: 0.8rem; text-transform: uppercase; margin-bottom: 0.5rem;">Documentos</h5>
                        ${attachmentsHtml || '<p style="font-size: 0.75rem; color: var(--text-muted);">Sin archivos</p>'}
                    </div>
                </div>
            </div>
        `;
    });
}

function openPaymentModal(loanId, suggestedAmount) {
    document.getElementById('payment-loan-id').value = loanId;
    document.getElementById('payment-suggested-amount').value = suggestedAmount;
    openModal('payment-modal');
}

function openQuotaEdit(id, amount, date) {
    document.getElementById('edit-quota-id').value = id;
    document.getElementById('edit-quota-amount').value = amount;
    document.getElementById('edit-quota-date').value = date;
    openModal('quota-edit-modal');
}

function openAttachmentModal(loanId) {
    document.getElementById('attachment-loan-id').value = loanId;
    openModal('attachment-modal');
}

function shareWhatsApp(name, phone, amount, type) {
    let text = "";
    if (type === 'loan') {
        // Special message for late payments if we find it's late (we can pass a late flag here too)
        text = `Hola ${name}, le recordamos su cuota pendiente en MaxiPagos por un valor de $${amount.toLocaleString()}. Por favor realice su pago para evitar más recargos por mora.`;
    } else if (type === 'investor') {
        text = `Hola ${name}, le enviamos el reporte actual de su inversión en MaxiPagos. Su capital disponible es de $${amount.toLocaleString()}.`;
    } else {
        text = `Hola ${name}, le saludamos de MaxiPagos. ¿En qué podemos ayudarle hoy?`;
    }
    
    // Clean phone number (keep only digits)
    const cleanPhone = (phone || "").replace(/\D/g, '');
    const url = cleanPhone ? `https://wa.me/${cleanPhone}?text=${encodeURIComponent(text)}` : `https://wa.me/?text=${encodeURIComponent(text)}`;
    window.open(url, '_blank');
}

async function updateInvestorsList() {
    const res = await fetch('/api/investors');
    const investors = await res.json();
    const tbody = document.querySelector('#investors-table tbody');
    const select = document.getElementById('investor-select');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    select.innerHTML = '<option value="">Negocio (Propio)</option>';
    
    for (const i of investors) {
        // Fetch detailed history for earnings
        const hRes = await fetch(`/api/investors/${i.id}/history`);
        const h = await hRes.json();
        
        tbody.innerHTML += `
            <tr>
                <td>${i.name}</td>
                <td style="font-size:0.85rem;">
                    Cap. Prestado: <strong>$${h.total_capital_lent.toLocaleString()}</strong><br>
                    Ganancia (Int): <strong style="color:var(--success);">$${h.total_earnings.toLocaleString()}</strong>
                </td>
                <td style="color: var(--text-muted); font-weight: 600;">$${i.balance.toLocaleString()}</td>
                <td>
                    <button onclick="shareWhatsApp('${i.name}', '${i.phone}', ${i.balance}, 'investor')" style="background:#25d366; color:white; border:none; padding: 0.3rem 0.6rem; border-radius:0.3rem; cursor:pointer; width:auto;">WhatsApp</button>
                </td>
            </tr>`;
        select.innerHTML += `<option value="${i.id}">${i.name}</option>`;
    }
}

function showSection(section) {
    ['overview', 'clients', 'loans', 'audit', 'expenses', 'client-detail', 'investors'].forEach(s => {
        const el = document.getElementById(`${s}-section`);
        if (el) el.style.display = (s === section) ? 'block' : 'none';
    });
    
    if (section !== 'client-detail') {
        const titles = { 
            overview: 'Resumen Financiero', 
            clients: 'Gestión de Clientes', 
            loans: 'Control de Préstamos', 
            audit: 'Registro de Auditoría', 
            expenses: 'Control de Gastos',
            investors: 'Gestión de Inversionistas'
        };
        document.getElementById('section-title').textContent = titles[section];
        document.querySelectorAll('nav a').forEach(a => a.classList.remove('active'));
        const navItem = document.querySelector(`nav a[onclick*="${section}"]`);
        if (navItem) navItem.classList.add('active');
    }
}

function openModal(id) { document.getElementById(id).style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }
window.onclick = (e) => { if (e.target.classList.contains('modal')) e.target.style.display = 'none'; }

async function updateExpensesList() {
    const res = await fetch('/api/expenses');
    const expenses = await res.json();
    const tbody = document.querySelector('#expenses-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    expenses.forEach(e => {
        const date = new Date(e.date).toLocaleDateString();
        tbody.innerHTML += `<tr><td>${date}</td><td>${e.description}</td><td style="color: var(--danger);">-$${e.amount.toLocaleString()}</td></tr>`;
    });
}

function filterClients() {
    const term = document.getElementById('search-client').value.toLowerCase();
    const rows = document.querySelectorAll('#clients-table tbody tr');
    rows.forEach(r => {
        const text = r.innerText.toLowerCase();
        r.style.display = text.includes(term) ? '' : 'none';
    });
}

function filterLoans() {
    const term = document.getElementById('search-loan').value.toLowerCase();
    const filter = document.getElementById('filter-loan-status').value;
    const rows = document.querySelectorAll('#loans-table tbody tr');
    rows.forEach(r => {
        const text = r.innerText.toLowerCase();
        const rowStatus = r.getAttribute('data-status');
        const isLate = r.getAttribute('data-late') === 'true';
        const isToday = r.getAttribute('data-today') === 'true';

        const matchesTerm = text.includes(term);
        let matchesFilter = false;
        
        if (filter === 'all') matchesFilter = true;
        else if (filter === 'late') matchesFilter = isLate;
        else if (filter === 'today') matchesFilter = isToday;
        else matchesFilter = (rowStatus === filter);

        r.style.display = matchesTerm && matchesFilter ? '' : 'none';
    });
}

function downloadReceipt(paymentId) {
    window.location = `/api/payments/${paymentId}/receipt`;
}

function downloadContract(loanId) {
    window.location = `/api/loans/${loanId}/contract`;
}
