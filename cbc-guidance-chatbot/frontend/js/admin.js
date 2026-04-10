// Admin dashboard JS for CBC Guidance Chatbot
// Handles fetching and rendering for Users, Schools, Documents, Analytics

// Dynamic API_BASE for development vs production
const API_BASE = (() => {
    const hostname = window.location.hostname;
    
    // Development environments
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return 'https://cbc-kcse-guidance-chatbot.onrender.com';
    }
    
    // Production environments
    if (hostname.includes('netlify.app') || hostname.includes('netlify.com')) {
        // Frontend on Netlify, backend on Render
        return 'https://cbc-kcse-guidance-chatbot.onrender.com';
    }
    
    // If frontend is also on Render (different service)
    if (hostname.includes('onrender.com')) {
        // Check if this is a frontend service
        if (hostname.includes('frontend') || hostname.includes('-web')) {
            return 'https://cbc-kcse-guidance-chatbot.onrender.com';
        }
        // Otherwise assume same origin
        return '';
    }
    
    // Default: same origin
    return '';
})();

// Chart instances
let queryPerformanceChart = null;
let successRateChart = null;
let documentsChart = null;
const schoolsState = { page: 1, pageSize: 25, total: 0, totalPages: 0 };
const documentsState = { page: 1, pageSize: 15, total: 0, totalPages: 0 };

function roleBadge(role) {
  const safeRole = (role || 'student').toLowerCase();
  const roleClass = safeRole === 'admin' ? 'badge-role-admin' : 'badge-role-student';
  return `<span class="badge ${roleClass}">${safeRole}</span>`;
}

function statusBadge(isActive) {
  const active = isActive !== false;
  const statusClass = active ? 'badge-status-active' : 'badge-status-inactive';
  return `<span class="badge ${statusClass}">${active ? 'Active' : 'Inactive'}</span>`;
}

function getAdminUserId() {
  return localStorage.getItem('userId');
}

function buildAdminHeaders(extraHeaders = {}) {
  const adminUserId = getAdminUserId();
  return {
    ...extraHeaders,
    'X-Admin-User-Id': adminUserId || ''
  };
}

async function adminFetch(url, options = {}) {
  const headers = buildAdminHeaders(options.headers || {});
  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    try {
      localStorage.setItem('postLoginRedirect', 'admin.html');
    } catch {}
    alert('Please log in to access the admin dashboard.');
    window.location = 'login.html?next=admin.html';
    throw new Error('Admin login required');
  }

  if (response.status === 403) {
    alert('Your account does not have admin access.');
    window.location = 'dashboard.html';
    throw new Error('Admin access denied');
  }

  return response;
}

async function ensureAdminAccess() {
  const adminUserId = getAdminUserId();
  if (!adminUserId) {
    try {
      localStorage.setItem('postLoginRedirect', 'admin.html');
    } catch {}
    alert('Please log in first.');
    window.location = 'login.html?next=admin.html';
    return false;
  }

  try {
    const res = await adminFetch(`${API_BASE}/users/`);
    return res.ok;
  } catch (e) {
    console.error('Admin access check failed:', e);
    return false;
  }
}

// --- USERS ---
async function loadUsers() {
  const tbody = document.getElementById('users-table-body');
  tbody.innerHTML = '<tr><td colspan="5">Loading...</td></tr>';
  try {
    const res = await adminFetch(`${API_BASE}/users/`);
    let users = await res.json();
    if (users && users.users) users = users.users;
    tbody.innerHTML = '';
    (users || []).forEach(user => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${user.name || ''}</td>
        <td>${user.email || ''}</td>
        <td>${roleBadge(user.role)}</td>
        <td>${statusBadge(user.active)}</td>
        <td class="admin-actions">
          <button onclick="toggleUserStatus('${user.user_id}', ${user.active !== false})" class="btn-small">${user.active === false ? 'Activate' : 'Deactivate'}</button>
          <button onclick="deleteUser('${user.user_id}')" class="btn-small btn-danger">Delete</button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error('Error loading users:', e);
    tbody.innerHTML = '<tr><td colspan="5">Failed to load users</td></tr>';
  }
}

async function toggleUserStatus(userId, isActive) {
  if (!confirm(`Are you sure you want to ${isActive ? 'deactivate' : 'activate'} this user?`)) return;
  try {
    const res = await adminFetch(`${API_BASE}/users/${userId}/status?active=${!isActive}`, {
      method: 'PUT'
    });
    if (res.ok) {
      loadUsers();
      alert('User status updated successfully');
    } else {
      alert('Failed to update user status');
    }
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function deleteUser(userId) {
  if (!confirm('Are you sure you want to permanently delete this user? This cannot be undone.')) return;
  try {
    const res = await adminFetch(`${API_BASE}/users/${userId}`, {
      method: 'DELETE'
    });
    if (res.ok) {
      loadUsers();
      alert('User deleted successfully');
    } else {
      alert('Failed to delete user');
    }
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// --- SCHOOLS ---
function renderPagination(containerId, state, changeFnName) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!state.totalPages || state.totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <button onclick="${changeFnName}(${state.page - 1})" ${state.page <= 1 ? 'disabled' : ''}>Previous</button>
    <span class="text-muted">Page ${state.page} of ${state.totalPages}</span>
    <button onclick="${changeFnName}(${state.page + 1})" ${state.page >= state.totalPages ? 'disabled' : ''}>Next</button>
  `;
}

function renderRangeSummary(summaryId, label, state) {
  const summary = document.getElementById(summaryId);
  if (!summary) return;

  if (!state.total) {
    summary.textContent = `No ${label.toLowerCase()} found.`;
    return;
  }

  const start = ((state.page - 1) * state.pageSize) + 1;
  const end = Math.min(state.page * state.pageSize, state.total);
  summary.textContent = `Showing ${start}-${end} of ${state.total} ${label.toLowerCase()}.`;
}

window.changeSchoolsPage = function(nextPage) {
  if (nextPage < 1 || nextPage > schoolsState.totalPages) return;
  loadSchools(nextPage, schoolsState.pageSize);
};

window.changeDocumentsPage = function(nextPage) {
  if (nextPage < 1 || nextPage > documentsState.totalPages) return;
  loadDocuments(nextPage, documentsState.pageSize);
};

async function loadSchools(page = 1, pageSize = schoolsState.pageSize) {
  const tbody = document.getElementById('schools-table-body');
  if (!tbody) return;
  schoolsState.page = page;
  schoolsState.pageSize = pageSize;
  tbody.innerHTML = '<tr><td colspan="5">Loading...</td></tr>';
  try {
    const res = await adminFetch(`${API_BASE}/schools?page=${page}&page_size=${pageSize}`);
    const data = await res.json();
    const schools = data.schools || [];
    schoolsState.total = Number(data.total || schools.length || 0);
    schoolsState.totalPages = Number(data.total_pages || 0);
    tbody.innerHTML = '';
    if (schools.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5">No schools found.</td></tr>';
      renderRangeSummary('schools-summary', 'Schools', schoolsState);
      renderPagination('schools-pagination', schoolsState, 'changeSchoolsPage');
      return;
    }
    schools.forEach(school => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${school.name || ''}</td>
        <td>${school.county || ''}</td>
        <td>${Array.isArray(school.pathways_offered) ? school.pathways_offered.join(', ') : (school.pathways_offered || '')}</td>
        <td>${school.type || ''}</td>
        <td>${school.gender || ''}</td>
      `;
      tbody.appendChild(tr);
    });
    renderRangeSummary('schools-summary', 'Schools', schoolsState);
    renderPagination('schools-pagination', schoolsState, 'changeSchoolsPage');
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="5">Failed to load schools.</td></tr>';
  }
}

// --- DOCUMENTS ---
async function loadDocuments(page = 1, pageSize = documentsState.pageSize) {
  const docsTable = document.getElementById('documents-table-body');
  if (!docsTable) return;
  documentsState.page = page;
  documentsState.pageSize = pageSize;
  docsTable.innerHTML = '<tr><td colspan="4">Loading...</td></tr>';
  try {
    const res = await adminFetch(`${API_BASE}/documents?page=${page}&page_size=${pageSize}`);
    const data = await res.json();
    const docs = data.documents || [];
    documentsState.total = Number(data.total || docs.length || 0);
    documentsState.totalPages = Number(data.total_pages || 0);
    if (docs.length === 0) {
      docsTable.innerHTML = '<tr><td colspan="4">No documents found.</td></tr>';
      renderRangeSummary('documents-summary', 'Documents', documentsState);
      renderPagination('documents-pagination', documentsState, 'changeDocumentsPage');
      return;
    }
    docsTable.innerHTML = '';
    docs.forEach(doc => {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td>${doc.title || ''}</td>
        <td>${doc.type || ''}</td>
        <td>${doc.uploaded ? new Date(doc.uploaded).toLocaleString() : ''}</td>
        <td>
          <button onclick="deleteDocument('${encodeURIComponent(doc.path || doc.title)}', '${doc.title}')" class="btn-small btn-danger">Delete</button>
        </td>
      `;
      docsTable.appendChild(row);
    });
    renderRangeSummary('documents-summary', 'Documents', documentsState);
    renderPagination('documents-pagination', documentsState, 'changeDocumentsPage');
  } catch (e) {
    docsTable.innerHTML = '<tr><td colspan="4">Failed to load documents.</td></tr>';
  }
}

function deleteDocument(docPath, docTitle) {
  if (!confirm(`Are you sure you want to delete "${docTitle}"?`)) return;
  adminFetch(`${API_BASE}/documents/${docPath}`, { method: 'DELETE' })
    .then(res => {
      if (res.ok) {
        if (documentsState.page > 1 && documentsState.total === 1 + ((documentsState.page - 1) * documentsState.pageSize)) {
          documentsState.page -= 1;
        }
        loadDocuments(documentsState.page, documentsState.pageSize);
        alert('Document deleted successfully');
      } else {
        alert('Failed to delete document.');
      }
    })
    .catch(e => alert('Error: ' + e.message));
}

function uploadDocument(event) {
  event.preventDefault();
  const fileInput = document.getElementById('document-upload-input');
  if (!fileInput || !fileInput.files.length) {
    alert('Please select a file');
    return;
  }
  
  const file = fileInput.files[0];
  const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
  
  if (!validTypes.includes(file.type)) {
    alert('Only PDF and DOCX files are supported');
    return;
  }
  
  const formData = new FormData();
  formData.append('file', file);
  
  const uploadBtn = event.target.querySelector('button[type="submit"]');
  uploadBtn.disabled = true;
  uploadBtn.textContent = 'Uploading...';
  
  adminFetch(`${API_BASE}/documents`, {
    method: 'POST',
    body: formData
  })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        loadDocuments(1, documentsState.pageSize);
        fileInput.value = '';
        alert('Document uploaded successfully');
      } else {
        alert('Failed to upload document: ' + (data.detail || 'Unknown error'));
      }
    })
    .catch(e => alert('Error: ' + e.message))
    .finally(() => {
      uploadBtn.disabled = false;
      uploadBtn.textContent = 'Upload Document';
    });
}

// --- PRIVACY-FIRST ANALYTICS ---
async function loadAnalytics() {
  try {
    const healthRes = await adminFetch(`${API_BASE}/admin/analytics/system-health?days=7`);
    const healthData = await healthRes.json();
    displaySystemHealth(healthData);
    
    const queryRes = await adminFetch(`${API_BASE}/admin/analytics/query-stats?days=7`);
    const queryData = await queryRes.json();
    displayQueryStats(queryData);
    
    const docRes = await adminFetch(`${API_BASE}/admin/analytics/documents`);
    const docData = await docRes.json();
    displayDocumentStats(docData.documents || []);
    
    const gapRes = await adminFetch(`${API_BASE}/admin/analytics/knowledge-gaps?limit=10`);
    const gapData = await gapRes.json();
    displayKnowledgeGaps(gapData.gaps || []);
    
    const feedbackRes = await adminFetch(`${API_BASE}/admin/analytics/feedback?days=7`);
    const feedbackData = await feedbackRes.json();
    displayFeedback(feedbackData);
  } catch (e) {
    console.error('Error loading analytics:', e);
  }
}

function displaySystemHealth(data) {
  const container = document.getElementById('health-stats');
  if (!container) return;
  
  const html = `
    <div class="metric-card">
      <div class="metric-value">${data.total_queries || 0}</div>
      <div class="metric-label">Total Queries (7 days)</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${((data.success_rate || 0) * 100).toFixed(1)}%</div>
      <div class="metric-label">Success Rate</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${(data.avg_confidence || 0).toFixed(2)}</div>
      <div class="metric-label">Avg Confidence Score</div>
    </div>
    <div class="metric-card">
      <div class="metric-value">${data.fallback_count || 0}</div>
      <div class="metric-label">Fallback Triggers</div>
    </div>
  `;
  container.innerHTML = html;
}

function displayQueryStats(data) {
  const tbody = document.getElementById('query-stats-body');
  if (!tbody) return;
  
  const stats = data.topic_stats || [];
  if (stats.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state">No query analytics yet. Ask a few CBC questions and this table will start filling.</div></td></tr>';
    return;
  }
  
  tbody.innerHTML = stats.map(stat => `
    <tr>
      <td>${stat.topic_category || 'Unknown'}</td>
      <td>${stat.count || 0}</td>
      <td>${(stat.avg_confidence || 0).toFixed(2)}</td>
      <td>${((stat.success_rate || 0) * 100).toFixed(1)}%</td>
    </tr>
  `).join('');
  
  createQueryPerformanceChart(stats);
  createSuccessRateChart(stats);
}

function createQueryPerformanceChart(stats) {
  const ctx = document.getElementById('queryPerformanceChart');
  if (!ctx) return;
  
  if (queryPerformanceChart) queryPerformanceChart.destroy();
  
  queryPerformanceChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: stats.map(s => s.topic_category || 'Unknown'),
      datasets: [{
        label: 'Query Count',
        data: stats.map(s => s.count || 0),
        backgroundColor: '#007bff',
        borderColor: '#0056b3',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top' }
      },
      scales: {
        y: { beginAtZero: true }
      }
    }
  });
}

function createSuccessRateChart(stats) {
  const ctx = document.getElementById('successRateChart');
  if (!ctx) return;
  
  if (successRateChart) successRateChart.destroy();
  
  successRateChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: stats.map(s => s.topic_category || 'Unknown'),
      datasets: [{
        label: 'Success Rate (%)',
        data: stats.map(s => ((s.success_rate || 0) * 100).toFixed(1)),
        backgroundColor: [
          '#28a745',
          '#ffc107',
          '#17a2b8',
          '#6f42c1',
          '#e83e8c'
        ],
        borderColor: '#fff',
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'right' }
      }
    }
  });
}

function displayDocumentStats(docs) {
  const tbody = document.getElementById('document-stats-body');
  if (!tbody) return;
  
  if (docs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3"><div class="empty-state">No Pinecone document retrieval has been recorded yet.</div></td></tr>';
    return;
  }
  
  tbody.innerHTML = docs.map(doc => `
    <tr>
      <td>${doc.document_name || 'Unknown'}</td>
      <td>${doc.retrieval_count || 0}</td>
      <td>${(doc.avg_confidence_score || 0).toFixed(2)}</td>
    </tr>
  `).join('');
  
  createDocumentsChart(docs);
}

function createDocumentsChart(docs) {
  const ctx = document.getElementById('documentsChart');
  if (!ctx) return;
  
  if (documentsChart) documentsChart.destroy();
  
  documentsChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: docs.map(d => d.document_name || 'Unknown').slice(0, 10),
      datasets: [{
        label: 'Times Retrieved',
        data: docs.map(d => d.retrieval_count || 0).slice(0, 10),
        backgroundColor: '#28a745',
        borderColor: '#1e7e34',
        borderWidth: 1
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: 'top' }
      },
      scales: {
        x: { beginAtZero: true }
      }
    }
  });
}

function displayKnowledgeGaps(gaps) {
  const tbody = document.getElementById('knowledge-gaps-body');
  if (!tbody) return;
  
  if (gaps.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state">No unanswered-document gaps detected so far.</div></td></tr>';
    return;
  }
  
  tbody.innerHTML = gaps.map(gap => `
    <tr>
      <td>${gap.topic_category || 'Unknown'}</td>
      <td>${gap.fallback_reason || 'Unknown'}</td>
      <td>${gap.count || 0}</td>
      <td>${gap.suggested_document_topic || 'N/A'}</td>
    </tr>
  `).join('');
}

function displayFeedback(feedbackData) {
  const container = document.getElementById('feedback-summary');
  if (!container) return;
  
  if (!feedbackData || Object.keys(feedbackData).length === 0) {
    container.innerHTML = '<div class="empty-state">No chat feedback has been submitted yet. Use the thumbs up or thumbs down buttons in chat to collect this data.</div>';
    return;
  }
  
  const html = `
    <div class="feedback-grid">
      ${Object.entries(feedbackData).map(([topic, feedback]) => `
        <div class="feedback-card">
          <h4>${topic}</h4>
          ${Object.entries(feedback).map(([type, count]) => `
            <div class="feedback-stat">
              <span>${type.replace('_', ' ')}</span>
              <strong>${count}</strong>
            </div>
          `).join('')}
        </div>
      `).join('')}
    </div>
  `;
  container.innerHTML = html;
}

window.showSection = function(eventOrSection, maybeSection) {
  const section = typeof eventOrSection === 'string' ? eventOrSection : maybeSection;
  const trigger = typeof eventOrSection === 'string' ? null : eventOrSection.currentTarget;
  document.querySelectorAll('.admin-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.admin-nav button').forEach(b => b.classList.remove('active'));
  
  const sectionEl = document.getElementById('admin-' + section);
  if (sectionEl) {
    sectionEl.classList.add('active');
  }

  if (trigger) {
    trigger.classList.add('active');
  } else {
    const activeButton = document.querySelector(`.admin-nav button[data-section="${section}"]`);
    if (activeButton) activeButton.classList.add('active');
  }

  if (section === 'users') loadUsers();
  if (section === 'schools') loadSchools();
  if (section === 'documents') loadDocuments();
  if (section === 'analytics') loadAnalytics();
};

// Initial load
window.addEventListener('DOMContentLoaded', async () => {
  const hasAccess = await ensureAdminAccess();
  if (!hasAccess) return;

  loadUsers();
  loadSchools();
  loadDocuments();
  
  const uploadForm = document.getElementById('document-upload-form');
  if (uploadForm) {
    uploadForm.addEventListener('submit', uploadDocument);
  }

  const currentUserLabel = document.getElementById('admin-current-user');
  if (currentUserLabel) {
    const currentEmail = localStorage.getItem('userEmail') || 'Admin';
    currentUserLabel.textContent = currentEmail;
  }
});
