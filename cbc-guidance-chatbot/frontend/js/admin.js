/**
 * admin.js
 * CBC Guidance Chatbot — Admin Dashboard
 *
 * Sections:
 *   Overview     — key metrics at a glance
 *   Questions    — recent student questions (history)
 *   Users        — manage accounts (activate/deactivate/delete)
 *   Schools      — browse school catalog (read-only)
 *   Documents    — upload/delete knowledge base documents
 *   Analytics    — query performance, document usage, knowledge gaps, feedback
 */

const API_BASE = 'https://cbc-kcse-guidance-chatbot.onrender.com';

// Chart instances
let chartQueries  = null;
let chartSuccess  = null;
let chartDocs     = null;

// Pagination state
const schoolsState   = { page: 1, pageSize: 30, total: 0, totalPages: 0 };
const docsState      = { page: 1, pageSize: 15, total: 0, totalPages: 0 };


// ── Auth helpers ──────────────────────────────────────────────────────────────

function getAdminId() {
  return localStorage.getItem('userId') || '';
}

function adminHeaders(extra = {}) {
  return { 'X-Admin-User-Id': getAdminId(), ...extra };
}

async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const headers = adminHeaders(options.headers || {});
  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    alert('Please log in to access the admin dashboard.');
    window.location.href = 'login.html';
    throw new Error('Not authenticated');
  }
  if (res.status === 403) {
    alert('Your account does not have admin access. Contact the system owner.');
    window.location.href = 'dashboard.html';
    throw new Error('Not admin');
  }
  return res;
}

async function checkAdminAccess() {
  const userId = getAdminId();
  if (!userId) {
    alert('Please log in first.');
    window.location.href = 'login.html';
    return false;
  }
  try {
    // Use admin stats endpoint to verify access
    const res = await apiFetch('/admin/stats');
    return res.ok;
  } catch {
    return false;
  }
}

function adminLogout() {
  ['userId','userEmail','userName','userProfile','userStage',
   'pendingStageMissing','profileOwnerUserId'].forEach(k => localStorage.removeItem(k));
  window.location.href = 'login.html';
}


// ── Section navigation ────────────────────────────────────────────────────────

function showSection(name) {
  document.querySelectorAll('.admin-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.admin-nav button').forEach(b => b.classList.remove('active'));

  const section = document.getElementById(`section-${name}`);
  if (section) section.classList.add('active');

  const btn = document.querySelector(`.admin-nav button[data-section="${name}"]`);
  if (btn) btn.classList.add('active');

  // Lazy load section data
  if (name === 'overview')   loadOverview();
  if (name === 'questions')  loadRecentQuestions();
  if (name === 'users')      loadUsers();
  if (name === 'schools')    loadSchools(1);
  if (name === 'documents')  loadDocuments(1);
  if (name === 'analytics')  loadAnalytics();
}


// ── Badge helpers ─────────────────────────────────────────────────────────────

function roleBadge(role) {
  const r = (role || 'student').toLowerCase();
  return `<span class="badge ${r === 'admin' ? 'badge-admin' : 'badge-student'}">${r}</span>`;
}

function statusBadge(active) {
  return active !== false
    ? `<span class="badge badge-active">Active</span>`
    : `<span class="badge badge-inactive">Inactive</span>`;
}

function emptyRow(cols, msg) {
  return `<tr><td colspan="${cols}"><div class="empty">${msg}</div></td></tr>`;
}


// ── Pagination helper ─────────────────────────────────────────────────────────

function renderPagination(containerId, state, onChangeFn) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!state.totalPages || state.totalPages <= 1) { el.innerHTML = ''; return; }

  el.innerHTML = `
    <button onclick="${onChangeFn}(${state.page - 1})" ${state.page <= 1 ? 'disabled' : ''}>← Prev</button>
    <span>Page ${state.page} of ${state.totalPages} &nbsp;·&nbsp; ${state.total} total</span>
    <button onclick="${onChangeFn}(${state.page + 1})" ${state.page >= state.totalPages ? 'disabled' : ''}>Next →</button>
  `;
}


// ── OVERVIEW ──────────────────────────────────────────────────────────────────

async function loadOverview() {
  try {
    const [statsRes, healthRes, docsRes] = await Promise.all([
      apiFetch('/admin/stats'),
      apiFetch('/admin/analytics/system-health?days=7'),
      apiFetch('/documents?page=1&page_size=1'),
    ]);

    const stats  = await statsRes.json();
    const health = await healthRes.json();
    const docs   = await docsRes.json();

    setText('m-users',   stats.total_users   ?? '—');
    setText('m-queries', health.total_queries ?? '—');
    setText('m-success', health.success_rate != null
      ? `${(health.success_rate * 100).toFixed(0)}%` : '—');
    setText('m-docs',    docs.total ?? '—');
  } catch (e) {
    console.error('Overview load failed:', e);
  }
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}


// ── RECENT QUESTIONS ──────────────────────────────────────────────────────────

async function loadRecentQuestions() {
  const container = document.getElementById('questions-list');
  if (!container) return;
  container.innerHTML = '<div class="empty">Loading...</div>';

  try {
    const res  = await apiFetch('/recent-questions?limit=30');
    const data = await res.json();
    const qs   = data.questions || [];

    if (!qs.length) {
      container.innerHTML = '<div class="empty">No questions yet. Students will appear here once they start chatting.</div>';
      return;
    }

    container.innerHTML = qs.map(q => {
      const date   = q.created_at ? new Date(q.created_at).toLocaleString() : '';
      const answer = (q.answer || '').slice(0, 120) + ((q.answer || '').length > 120 ? '…' : '');
      return `
        <div class="question-row">
          <div class="question-text">${escHtml(q.question || '')}</div>
          <div class="question-answer">${escHtml(answer)}</div>
          <div class="question-meta">${date}</div>
        </div>
      `;
    }).join('');
  } catch (e) {
    container.innerHTML = '<div class="empty">Failed to load questions.</div>';
    console.error(e);
  }
}

function escHtml(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}


// ── USERS ─────────────────────────────────────────────────────────────────────

async function loadUsers() {
  const tbody = document.getElementById('users-tbody');
  if (!tbody) return;
  tbody.innerHTML = emptyRow(5, 'Loading users...');

  try {
    const res  = await apiFetch('/users/');
    const data = await res.json();
    const users = data.users || data || [];

    if (!users.length) {
      tbody.innerHTML = emptyRow(5, 'No users found.');
      return;
    }

    tbody.innerHTML = users.map(u => `
      <tr>
        <td>${escHtml(u.name || '')}</td>
        <td>${escHtml(u.email || '')}</td>
        <td>${roleBadge(u.role)}</td>
        <td>${statusBadge(u.active)}</td>
        <td>
          <button class="btn-sm" onclick="toggleUser('${u.user_id}', ${u.active !== false})">
            ${u.active === false ? 'Activate' : 'Deactivate'}
          </button>
          <button class="btn-sm btn-danger" onclick="deleteUser('${u.user_id}', '${escHtml(u.name || u.email || '')}')">
            Delete
          </button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = emptyRow(5, 'Failed to load users.');
    console.error(e);
  }
}

async function toggleUser(userId, isCurrentlyActive) {
  const action = isCurrentlyActive ? 'deactivate' : 'activate';
  if (!confirm(`Are you sure you want to ${action} this user?`)) return;
  try {
    const res = await apiFetch(`/users/${userId}/status?active=${!isCurrentlyActive}`, { method: 'PUT' });
    if (res.ok) { loadUsers(); }
    else { alert('Failed to update user status.'); }
  } catch (e) { alert('Error: ' + e.message); }
}

async function deleteUser(userId, name) {
  if (!confirm(`Permanently delete user "${name}"? This cannot be undone.`)) return;
  try {
    const res = await apiFetch(`/users/${userId}`, { method: 'DELETE' });
    if (res.ok) { loadUsers(); }
    else { alert('Failed to delete user.'); }
  } catch (e) { alert('Error: ' + e.message); }
}


// ── SCHOOLS ───────────────────────────────────────────────────────────────────

window.changeSchoolsPage = function(page) { loadSchools(page); };

async function loadSchools(page = 1) {
  const tbody   = document.getElementById('schools-tbody');
  const summary = document.getElementById('schools-summary');
  if (!tbody) return;

  schoolsState.page = page;
  tbody.innerHTML = emptyRow(5, 'Loading schools...');

  try {
    const res  = await apiFetch(`/schools?page=${page}&page_size=${schoolsState.pageSize}`);
    const data = await res.json();
    const schools = data.schools || [];

    schoolsState.total      = data.total      || schools.length;
    schoolsState.totalPages = data.total_pages || 0;

    if (!schools.length) {
      tbody.innerHTML = emptyRow(5, 'No schools found.');
      if (summary) summary.textContent = '';
      return;
    }

    tbody.innerHTML = schools.map(s => {
      const pathways = Array.isArray(s.pathways_offered)
        ? s.pathways_offered.join(', ')
        : (s.pathways_offered || '—');
      return `
        <tr>
          <td>${escHtml(s.name || s.school_name || '')}</td>
          <td>${escHtml(s.county || '')}</td>
          <td>${escHtml(s.type  || s.school_type || '')}</td>
          <td>${escHtml(s.gender || '')}</td>
          <td>${escHtml(pathways)}</td>
        </tr>
      `;
    }).join('');

    if (summary) {
      const from = (page - 1) * schoolsState.pageSize + 1;
      const to   = Math.min(page * schoolsState.pageSize, schoolsState.total);
      summary.textContent = `Showing ${from}–${to} of ${schoolsState.total} schools`;
    }
    renderPagination('schools-pagination', schoolsState, 'changeSchoolsPage');
  } catch (e) {
    tbody.innerHTML = emptyRow(5, 'Failed to load schools.');
    console.error(e);
  }
}


// ── DOCUMENTS ─────────────────────────────────────────────────────────────────

window.changeDocsPage = function(page) { loadDocuments(page); };

async function loadDocuments(page = 1) {
  const tbody   = document.getElementById('docs-tbody');
  const summary = document.getElementById('docs-summary');
  if (!tbody) return;

  docsState.page = page;
  tbody.innerHTML = emptyRow(4, 'Loading documents...');

  try {
    const res  = await apiFetch(`/documents?page=${page}&page_size=${docsState.pageSize}`);
    const data = await res.json();
    const docs = data.documents || [];

    docsState.total      = data.total      || docs.length;
    docsState.totalPages = data.total_pages || 0;

    if (!docs.length) {
      tbody.innerHTML = emptyRow(4, 'No documents indexed yet. Upload a PDF or DOCX above.');
      if (summary) summary.textContent = '';
      return;
    }

    tbody.innerHTML = docs.map(doc => `
      <tr>
        <td>${escHtml(doc.title || '')}</td>
        <td>${escHtml(doc.type  || '')}</td>
        <td>${doc.uploaded ? new Date(doc.uploaded).toLocaleDateString() : '—'}</td>
        <td>
          <button class="btn-sm btn-danger"
            onclick="deleteDocument('${encodeURIComponent(doc.path || doc.title)}', '${escHtml(doc.title || '')}')">
            Delete
          </button>
        </td>
      </tr>
    `).join('');

    if (summary) summary.textContent = `${docsState.total} document${docsState.total !== 1 ? 's' : ''} indexed`;
    renderPagination('docs-pagination', docsState, 'changeDocsPage');
  } catch (e) {
    tbody.innerHTML = emptyRow(4, 'Failed to load documents.');
    console.error(e);
  }
}

async function uploadDocument() {
  const input = document.getElementById('upload-input');
  const btn   = document.getElementById('upload-btn');
  if (!input || !input.files.length) { alert('Please select a file first.'); return; }

  const file = input.files[0];
  const valid = ['application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
  if (!valid.includes(file.type)) { alert('Only PDF and DOCX files are supported.'); return; }

  const formData = new FormData();
  formData.append('file', file);

  btn.disabled    = true;
  btn.textContent = 'Uploading…';

  try {
    const res  = await apiFetch('/documents', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      input.value = '';
      loadDocuments(1);
      alert(`"${file.name}" uploaded successfully and added to the knowledge base.`);
    } else {
      alert('Upload failed: ' + (data.detail || 'Unknown error'));
    }
  } catch (e) {
    alert('Upload error: ' + e.message);
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Upload';
    btn.innerHTML   = '<i class="bi bi-upload"></i> Upload';
  }
}

async function deleteDocument(docPath, docTitle) {
  if (!confirm(`Delete "${docTitle}" from the knowledge base?`)) return;
  try {
    const res = await apiFetch(`/documents/${docPath}`, { method: 'DELETE' });
    if (res.ok) {
      loadDocuments(docsState.page);
      alert('Document deleted.');
    } else {
      alert('Failed to delete document.');
    }
  } catch (e) { alert('Error: ' + e.message); }
}


// ── ANALYTICS ─────────────────────────────────────────────────────────────────

async function loadAnalytics() {
  try {
    const [healthRes, queryRes, docRes, gapRes, feedbackRes] = await Promise.all([
      apiFetch('/admin/analytics/system-health?days=7'),
      apiFetch('/admin/analytics/query-stats?days=7'),
      apiFetch('/admin/analytics/documents'),
      apiFetch('/admin/analytics/knowledge-gaps?limit=10'),
      apiFetch('/admin/analytics/feedback?days=7'),
    ]);

    renderHealth(await healthRes.json());
    renderQueryStats(await queryRes.json());
    renderDocStats((await docRes.json()).documents || []);
    renderGaps((await gapRes.json()).gaps || []);
    renderFeedback(await feedbackRes.json());
  } catch (e) {
    console.error('Analytics load failed:', e);
  }
}

function renderHealth(data) {
  const el = document.getElementById('health-metrics');
  if (!el) return;
  el.innerHTML = `
    <div class="metric-card">
      <div class="metric-value">${data.total_queries ?? '—'}</div>
      <div class="metric-label">Total Queries</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${data.success_rate != null ? (data.success_rate * 100).toFixed(0) + '%' : '—'}</div>
      <div class="metric-label">Success Rate</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${data.avg_confidence != null ? data.avg_confidence.toFixed(2) : '—'}</div>
      <div class="metric-label">Avg Confidence</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${data.fallback_count ?? '—'}</div>
      <div class="metric-label">Fallback Triggers</div>
    </div>
  `;
}

function renderQueryStats(data) {
  const stats = data.topic_stats || [];
  const tbody = document.getElementById('query-stats-tbody');
  if (!tbody) return;

  if (!stats.length) {
    tbody.innerHTML = emptyRow(4, 'No query data yet. Data appears after students use the chatbot.');
    return;
  }

  tbody.innerHTML = stats.map(s => `
    <tr>
      <td>${escHtml(s.topic_category || 'Unknown')}</td>
      <td>${s.count || 0}</td>
      <td>${(s.avg_confidence || 0).toFixed(2)}</td>
      <td>${((s.success_rate || 0) * 100).toFixed(1)}%</td>
    </tr>
  `).join('');

  // Bar chart — query volume
  const labels = stats.map(s => s.topic_category || 'Unknown');
  const counts = stats.map(s => s.count || 0);
  const rates  = stats.map(s => +((s.success_rate || 0) * 100).toFixed(1));

  buildChart('chart-queries', chartQueries, 'bar', labels, counts,
    'Queries', '#1e3a8a', c => { chartQueries = c; });

  buildChart('chart-success', chartSuccess, 'doughnut', labels, rates,
    'Success Rate %',
    ['#1e3a8a','#0f766e','#0891b2','#7c3aed','#db2777','#ea580c'],
    c => { chartSuccess = c; });
}

function renderDocStats(docs) {
  const tbody = document.getElementById('doc-stats-tbody');
  if (!tbody) return;

  if (!docs.length) {
    tbody.innerHTML = emptyRow(3, 'No document retrieval data yet.');
    return;
  }

  tbody.innerHTML = docs.map(d => `
    <tr>
      <td>${escHtml(d.document_name || '—')}</td>
      <td>${d.retrieval_count || 0}</td>
      <td>${(d.avg_confidence_score || 0).toFixed(2)}</td>
    </tr>
  `).join('');

  buildChart('chart-docs', chartDocs, 'bar',
    docs.slice(0,10).map(d => d.document_name || '—'),
    docs.slice(0,10).map(d => d.retrieval_count || 0),
    'Times Retrieved', '#0f766e',
    c => { chartDocs = c; }, true);
}

function renderGaps(gaps) {
  const tbody = document.getElementById('gaps-tbody');
  if (!tbody) return;
  if (!gaps.length) {
    tbody.innerHTML = emptyRow(4, 'No knowledge gaps detected yet.');
    return;
  }
  tbody.innerHTML = gaps.map(g => `
    <tr>
      <td>${escHtml(g.topic_category || '—')}</td>
      <td>${escHtml(g.fallback_reason || '—')}</td>
      <td>${g.count || 0}</td>
      <td>${escHtml(g.suggested_document_topic || '—')}</td>
    </tr>
  `).join('');
}

function renderFeedback(data) {
  const el = document.getElementById('feedback-container');
  if (!el) return;
  const entries = Object.entries(data || {});
  if (!entries.length) {
    el.innerHTML = '<div class="empty">No feedback submitted yet. Students use thumbs up/down in chat.</div>';
    return;
  }
  el.innerHTML = `
    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap:12px;">
      ${entries.map(([topic, counts]) => `
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px;">
          <strong style="font-size:13px; color:#0f172a;">${escHtml(topic)}</strong>
          <div style="margin-top:8px;">
            ${Object.entries(counts).map(([type, count]) => `
              <div style="display:flex; justify-content:space-between; font-size:13px; padding:4px 0; border-bottom:1px solid #f1f5f9;">
                <span style="color:#475569;">${type.replace(/_/g,' ')}</span>
                <strong>${count}</strong>
              </div>
            `).join('')}
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

// Generic chart builder
function buildChart(canvasId, existingChart, type, labels, data, label, color, onCreated, horizontal = false) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  if (existingChart) existingChart.destroy();

  const isArray = Array.isArray(color);
  const chart = new Chart(ctx, {
    type,
    data: {
      labels,
      datasets: [{
        label,
        data,
        backgroundColor: isArray ? color : color + (type === 'bar' ? '33' : ''),
        borderColor:     isArray ? color : color,
        borderWidth: 2,
      }]
    },
    options: {
      indexAxis: horizontal ? 'y' : 'x',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: type === 'doughnut', position: 'right' } },
      scales: type === 'doughnut' ? {} : { [horizontal ? 'x' : 'y']: { beginAtZero: true } },
    }
  });
  if (onCreated) onCreated(chart);
}


// ── Init ──────────────────────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', async () => {
  const ok = await checkAdminAccess();
  if (!ok) return;

  // Show admin email in topbar
  const emailEl = document.getElementById('admin-current-user');
  if (emailEl) emailEl.textContent = localStorage.getItem('userEmail') || 'Admin';

  // Load default section
  loadOverview();
});
