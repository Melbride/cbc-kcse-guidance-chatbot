// Backend-Connected Functions for CBC Chatbot
const API_BASE = 'https://cbc-kcse-guidance-chatbot.onrender.com';const THEME_KEY = 'uiTheme';

function getStoredTheme() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return (value === 'dark' || value === 'light') ? value : null;
  } catch {
    return null;
  }
}

function getPreferredTheme() {
  const stored = getStoredTheme();
  if (stored) return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function updateThemeToggleLabels() {
  const isDark = document.body.classList.contains('theme-dark');
  const nextLabel = isDark ? 'Light mode' : 'Dark mode';
  const icon = isDark ? '☀' : '◐';

  document.querySelectorAll('.theme-toggle-text').forEach((el) => {
    el.textContent = nextLabel;
  });

  document.querySelectorAll('.theme-toggle-icon').forEach((el) => {
    el.textContent = icon;
  });

  document.querySelectorAll('.theme-toggle-button').forEach((el) => {
    el.setAttribute('aria-label', nextLabel);
    el.setAttribute('title', nextLabel);
  });
}

function applyTheme(theme, persist = true) {
  const resolved = theme === 'dark' ? 'dark' : 'light';
  document.body.classList.remove('theme-dark', 'theme-light');
  if (resolved === 'dark') {
    document.body.classList.add('theme-dark');
  }

  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, resolved);
    } catch {
      // Ignore storage failures for private browsing modes.
    }
  }

  updateThemeToggleLabels();
}

function toggleTheme() {
  const isDark = document.body.classList.contains('theme-dark');
  applyTheme(isDark ? 'light' : 'dark');
}

function backendStageToFrontend(stage) {
  if (stage === 'pre_exam') return 'before_exam';
  if (stage === 'post_results') return 'after_exam';
  if (stage === 'post_placement') return 'after_placement';
  return stage || 'before_exam';
}

function frontendStageToBackend(stage) {
  if (stage === 'before_exam') return 'pre_exam';
  if (stage === 'after_exam') return 'post_results';
  if (stage === 'after_placement') return 'post_placement';
  return stage || 'pre_exam';
}

function getStoredProfile() {
  try {
    return JSON.parse(localStorage.getItem('userProfile') || '{}');
  } catch {
    return {};
  }
}

function saveStoredProfile(profile) {
  const currentUserId = localStorage.getItem('userId');
  if (currentUserId) {
    localStorage.setItem('profileOwnerUserId', currentUserId);
  }
  localStorage.setItem('userProfile', JSON.stringify(profile || {}));
}

function getPostLoginRedirect() {
  try {
    const params = new URLSearchParams(window.location.search);
    const next = params.get('next');
    if (next && !next.includes('://') && !next.startsWith('//')) {
      return next;
    }
  } catch {
    // Ignore malformed URLs and fall back to storage.
  }

  try {
    const stored = localStorage.getItem('postLoginRedirect');
    if (stored && !stored.includes('://') && !stored.startsWith('//')) {
      return stored;
    }
  } catch {
    // Ignore storage failures.
  }

  return '';
}

function clearPostLoginRedirect() {
  try {
    localStorage.removeItem('postLoginRedirect');
  } catch {
    // Ignore storage failures.
  }
}

function clearStaleLocalProfileForUser(userId) {
  const owner = localStorage.getItem('profileOwnerUserId');
  if (owner && owner !== userId) {
    localStorage.removeItem('userProfile');
    localStorage.removeItem('userStage');
    localStorage.removeItem('pendingStageMissing');
  }
  localStorage.setItem('profileOwnerUserId', userId);
}

const CBC_STAGE2_SUBJECTS = [
  { code: '901', name: 'English' },
  { code: '902', name: 'Kiswahili' },
  { code: '903', name: 'Mathematics' },
  { code: '905', name: 'Integrated Science' },
  { code: '906', name: 'Agriculture' },
  { code: '907', name: 'Social Studies' },
  { code: '908', name: 'Christian Religious Education' },
  { code: '911', name: 'Creative Arts & Sports' },
  { code: '912', name: 'Pre-technical Studies' },
];

function performanceDescription(level) {
  if (!level) return '';
  if (level.startsWith('EE')) return 'Exceeding Expectation';
  if (level.startsWith('ME')) return 'Meeting Expectation';
  if (level.startsWith('AE')) return 'Approaching Expectation';
  if (level.startsWith('BE')) return 'Below Expectation';
  return '';
}

function updatePerformanceDescription(subjectCode) {
  const perf = document.getElementById(`perf-${subjectCode}`)?.value || '';
  const descInput = document.getElementById(`desc-${subjectCode}`);
  if (descInput) {
    descInput.value = performanceDescription(perf);
  }
}

function collectCBCSubjectResultsFromForm() {
  const subjects = [];
  const missing = [];

  for (const subject of CBC_STAGE2_SUBJECTS) {
    const performance = document.getElementById(`perf-${subject.code}`)?.value || '';
    const pointsRaw = document.getElementById(`pts-${subject.code}`)?.value || '';
    const points = parseInt(pointsRaw, 10);

    if (!performance || Number.isNaN(points)) {
      missing.push(`${subject.code} ${subject.name}`);
      continue;
    }

    subjects.push({
      subject_code: subject.code,
      subject_name: subject.name,
      performance_level: performance,
      points,
    });
  }

  return { subjects, missing };
}

function prefillCBCSubjectResults(subjectRows) {
  if (!Array.isArray(subjectRows)) return;
  const byCode = {};
  for (const row of subjectRows) {
    if (row && row.subject_code) {
      byCode[String(row.subject_code)] = row;
    }
  }

  for (const subject of CBC_STAGE2_SUBJECTS) {
    const row = byCode[subject.code];
    if (!row) continue;

    const perfInput = document.getElementById(`perf-${subject.code}`);
    const ptsInput = document.getElementById(`pts-${subject.code}`);
    if (perfInput && row.performance_level) perfInput.value = row.performance_level;
    if (ptsInput && row.points !== undefined && row.points !== null) ptsInput.value = row.points;
    updatePerformanceDescription(subject.code);
  }
}

function isStageComplete(profile, stage) {
  const p = profile || {};
  if (stage === 'before_exam') {
    return Boolean(p.favorite_subject && p.interests && p.strengths);
  }
  if (stage === 'after_exam') {
    const hasCBCSubjects = (p.cbc_subject_count || 0) >= CBC_STAGE2_SUBJECTS.length;
    const hasPathwayScores = [p.stem_score, p.social_sciences_score, p.arts_sports_score]
      .every(v => v !== null && v !== undefined && v !== '');
    return hasCBCSubjects && hasPathwayScores;
  }
  if (stage === 'after_placement') {
    return Boolean(p.placed_school && p.placed_pathway);
  }
  return false;
}

function stageLabel(stage) {
  if (stage === 'before_exam') return 'Stage 1: Before Exams';
  if (stage === 'after_exam') return 'Stage 2: After Exams';
  if (stage === 'after_placement') return 'Stage 3: After Placement';
  return stage;
}

function getMissingFieldsForStage(profile, stage) {
  const p = profile || {};
  if (stage === 'before_exam') {
    const missing = [];
    if (!p.favorite_subject) missing.push('Favorite Subject');
    if (!p.interests) missing.push('Interests');
    if (!p.strengths) missing.push('Strengths');
    return missing;
  }
  if (stage === 'after_exam') {
    const hasCBCSubjects = (p.cbc_subject_count || 0) >= CBC_STAGE2_SUBJECTS.length;
    const hasPathwayScores = [p.stem_score, p.social_sciences_score, p.arts_sports_score]
      .every(v => v !== null && v !== undefined && v !== '');
    const missing = [];
    if (!hasCBCSubjects) missing.push('All 9 CBC subjects (performance level + points)');
    if (!hasPathwayScores) missing.push('All 3 pathway scores (STEM, Social Science, Arts & Sports)');
    return missing;
  }
  if (stage === 'after_placement') {
    const missing = [];
    if (!p.placed_school) missing.push('Placed School');
    if (!p.placed_pathway) missing.push('Placed Pathway');
    return missing;
  }
  return [];
}

function openPendingStage(stage) {
  const profile = getStoredProfile();
  const missing = getMissingFieldsForStage(profile, stage);
  localStorage.setItem('userStage', stage);
  localStorage.setItem('pendingStageMissing', JSON.stringify({ stage, missing }));
  navigate('profile.html');
}

function renderStageProgressPanel(profile) {
  const panel = document.getElementById('stage-progress-panel');
  const content = document.getElementById('stage-progress-content');
  if (!panel || !content) {
    return;
  }

  const currentStage = (profile && profile.journey_stage) ? profile.journey_stage : 'before_exam';
  const stages = ['before_exam', 'after_exam', 'after_placement'];
  const completedCount = stages.filter((stage) => isStageComplete(profile, stage)).length;
  const completionPercent = Math.round((completedCount / stages.length) * 100);

  const rows = stages.map((stage) => {
    const complete = isStageComplete(profile, stage);
    const isCurrent = stage === currentStage;
    const dotClass = complete ? 'dot-done' : (isCurrent ? 'dot-current' : 'dot-pending');
    const badgeClass = complete ? 'badge-done' : (isCurrent ? 'badge-current' : 'badge-pending');
    const badgeText = complete ? 'Complete' : (isCurrent ? 'Current' : 'Pending');
    const currentMark = isCurrent ? ' <span class="stage-current-mark">(current)</span>' : '';
    const rowClass = [
      'stage-row',
      isCurrent ? 'stage-row-current' : '',
      complete ? 'stage-row-done' : 'stage-row-pending',
    ].join(' ').trim();
    return `<div class="${rowClass}"><div class="stage-dot ${dotClass}"></div><span class="stage-label">${stageLabel(stage)}${currentMark}</span><span class="stage-badge ${badgeClass}">${badgeText}</span></div>`;
  });

  const optionalHint = !isStageComplete(profile, 'before_exam') && (currentStage === 'after_exam' || currentStage === 'after_placement')
    ? '<p style="font-size:12px;color:var(--muted);margin-top:10px;margin-bottom:0;">You can continue without Stage 1 details. Adding it later improves personalisation.</p>'
    : '';

  const progressBlock = `
    <div class="stage-progress-metric">
      <span>${completedCount}/${stages.length} stages completed</span>
      <span>${completionPercent}%</span>
    </div>
    <div class="stage-progress-meter" aria-hidden="true">
      <div class="stage-progress-fill" style="width:${completionPercent}%"></div>
    </div>
  `;

  content.innerHTML = progressBlock + `<div class="stage-row-grid">${rows.join('')}</div>` + optionalHint;
  panel.style.display = 'block';
}

async function loadAndMergeProfile(userId) {
  const localProfile = getStoredProfile();
  try {
    const profileResponse = await fetch(`${API_BASE}/profiles/${userId}`);
    if (!profileResponse.ok) {
      return localProfile;
    }
    const backendProfile = await profileResponse.json();
    const merged = {
      ...backendProfile,
      ...localProfile,
      // Keep backend stage as source of truth if available.
      journey_stage: backendStageToFrontend(backendProfile.journey_stage) || localProfile.journey_stage,
    };
    saveStoredProfile(merged);
    return merged;
  } catch (error) {
    console.error('Profile load error:', error);
    return localProfile;
  }
}

function prefillProfileForm(profile) {
  const p = profile || {};
  const setValue = (id, value) => {
    const el = document.getElementById(id);
    if (el && value !== undefined && value !== null) {
      el.value = value;
    }
  };

  setValue('favorite-subject', p.favorite_subject || '');
  setValue('interests', p.interests || '');
  setValue('strengths', p.strengths || '');
  setValue('career-interests', p.career_interests || '');
  setValue('learning-style', p.learning_style || '');

  setValue('explore-goals', p.explore_goals || '');
  setValue('stem-pathway-score', p.stem_score ?? '');
  setValue('social-pathway-score', p.social_sciences_score ?? '');
  setValue('arts-pathway-score', p.arts_sports_score ?? '');

  setValue('placed-school', p.placed_school || '');
  setValue('placed-pathway', p.placed_pathway || '');

  prefillCBCSubjectResults(p.cbc_subject_results || []);
}

// Authentication
async function login() {
  const email = document.getElementById('login-email').value;
  const password = document.getElementById('login-password').value;
  
  if (!email || !password) {
    alert('Please enter email and password');
    return;
  }

  try {
    // First check if user exists
    const checkResponse = await fetch(`${API_BASE}/users/email/${encodeURIComponent(email)}`);
    
    if (checkResponse.ok) {
      const userData = await checkResponse.json();
      
      if (!userData.exists) {
        // User doesn't exist, redirect to signup
        alert('No account found with this email. Please create an account first.');
        navigate('signup.html');
        return;
      }
      
      // User exists, proceed with login
      const user = userData.user;
      localStorage.setItem('userId', user.user_id);
      localStorage.setItem('userEmail', email);
      localStorage.setItem('userName', user.name);
      clearStaleLocalProfileForUser(user.user_id);
      alert(`Welcome back, ${user.name}!`);

      // Route based on whether user already has a profile and stage.
      const profile = await loadAndMergeProfile(user.user_id);
      const stage = profile.journey_stage || 'before_exam';
      localStorage.setItem('userStage', stage);
      const postLoginRedirect = getPostLoginRedirect();

      if (postLoginRedirect) {
        clearPostLoginRedirect();
        navigate(postLoginRedirect);
        return;
      }

      if (!profile.journey_stage) {
        navigate('stage.html');
      } else if (!isStageComplete(profile, stage)) {
        // Only ask for missing details of the user's current stage.
        navigate('profile.html');
      } else {
        navigate('dashboard.html');
      }
      
    } else {
      alert('Error checking user. Please try again.');
    }
  } catch (error) {
    console.error('Login error:', error);
    alert('Network error. Please try again.');
  }
}

async function signUp() {
  const name = document.getElementById('signup-name').value;
  const email = document.getElementById('signup-email').value;
  const password = document.getElementById('signup-password').value;
  
  if (!name || !email || !password) {
    alert('Please fill all fields');
    return;
  }

  try {
    // Create new user in backend
    const response = await fetch(`${API_BASE}/users/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email })
    });

    if (response.ok) {
      const data = await response.json();
      localStorage.setItem('userId', data.user_id);
      localStorage.setItem('userEmail', email);
      localStorage.setItem('userName', data.name);
      // New account should never inherit prior browser profile state.
      localStorage.removeItem('userProfile');
      localStorage.removeItem('userStage');
      localStorage.removeItem('pendingStageMissing');
      localStorage.setItem('profileOwnerUserId', data.user_id);
      alert(`Account created successfully! Welcome, ${data.name}!`);
      // New users should choose stage first.
      navigate('stage.html');
    } else {
      alert('Sign up failed');
    }
  } catch (error) {
    console.error('Sign up error:', error);
    alert('Network error. Please try again.');
  }
}

function initializeStageSpecificProfileForm() {
  const stage = localStorage.getItem('userStage') || 'before_exam';
  const helpText = document.getElementById('stage-help-text');
  const modeNote = document.getElementById('stage-mode-note');
  const missingAlert = document.getElementById('stage-missing-alert');
  const commonFields = document.getElementById('common-profile-fields');
  const beforeExam = document.getElementById('stage-before-exam-fields');
  const afterExam = document.getElementById('stage-after-exam-fields');
  const afterPlacement = document.getElementById('stage-after-placement-fields');

  if (!helpText || !beforeExam || !afterExam || !afterPlacement || !modeNote || !commonFields || !missingAlert) {
    return;
  }

  beforeExam.style.display = 'none';
  afterExam.style.display = 'none';
  afterPlacement.style.display = 'none';

  if (stage === 'before_exam') {
    beforeExam.style.display = 'block';
    commonFields.style.display = 'block';
    modeNote.style.display = 'none';
    helpText.textContent = 'You are in the pre-exam stage. Share interests and strengths so we can suggest suitable pathways early.';
  } else if (stage === 'after_exam') {
    afterExam.style.display = 'block';
    commonFields.style.display = 'none';
    modeNote.style.display = 'block';
    modeNote.textContent = 'You are updating Stage 2 details only. Your Stage 1 profile remains saved and will still be used.';
    helpText.textContent = 'You are in the post-results stage. Add your latest performance so recommendations can be more accurate.';
  } else if (stage === 'after_placement') {
    afterPlacement.style.display = 'block';
    commonFields.style.display = 'none';
    modeNote.style.display = 'block';
    modeNote.textContent = 'You are updating Stage 3 details only. Previous profile details remain saved.';
    helpText.textContent = 'You are in the post-placement stage. Add placement details for pathway and school-specific guidance.';
  }

  // Prefill with any previously saved values so user only updates missing fields.
  const profile = getStoredProfile();
  prefillProfileForm(profile);

  try {
    const pendingRaw = localStorage.getItem('pendingStageMissing');
    if (pendingRaw) {
      const pendingData = JSON.parse(pendingRaw);
      if (pendingData.stage === stage && Array.isArray(pendingData.missing) && pendingData.missing.length > 0) {
        missingAlert.style.display = 'block';
        missingAlert.innerHTML = `<strong>Missing for this stage:</strong> ${pendingData.missing.join(', ')}`;
      }
    }
  } catch (e) {
    console.error('Pending stage parsing error:', e);
  }
}

// Chat functionality
let chatMessages = [];
let pathwayChosen = '';

async function submitChatFeedback(messageIndex, feedbackType) {
  const msg = chatMessages[messageIndex];
  if (!msg || msg.type !== 'bot' || !msg.question || msg.feedbackSubmitted) {
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: msg.question,
        feedback_type: feedbackType,
      })
    });

    if (!response.ok) {
      throw new Error(`Feedback failed (${response.status})`);
    }

    chatMessages[messageIndex] = {
      ...msg,
      feedbackSubmitted: feedbackType,
    };
    renderChat();
  } catch (error) {
    console.error('Feedback error:', error);
    alert('Could not save feedback right now. Please try again.');
  }
}

function startChat() {
  chatMessages = [];
  renderChat();
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  
  if (!text) return;

  // Add user message
  chatMessages.push({ type: 'user', text });
  renderChat();
  input.value = '';

  try {
    // Get user context
    const userId = localStorage.getItem('userId');
    const userProfile = localStorage.getItem('userProfile');
    const profile = userProfile ? JSON.parse(userProfile) : null;
    
    // Send to backend for Pinecone response with user context
    const response = await fetch(`${API_BASE}/query/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: text,
        user_id: userId || 'demo-user',
        context: {
          stage: profile?.journey_stage === 'before_exam' ? 'pre_exam' : 
                 profile?.journey_stage === 'after_exam' ? 'post_results' : 
                 profile?.journey_stage === 'after_placement' ? 'post_placement' : 'pre_exam',
          interests: profile?.interests || '',
          strengths: profile?.strengths || '',
          favorite_subject: profile?.favorite_subject || '',
          career_interests: profile?.career_interests || '',
          learning_style: profile?.learning_style || ''
        }
      })
    });

    if (response.ok) {
      const data = await response.json();
      chatMessages.push({ 
        type: 'bot', 
        text: data.answer || 'I need more information to help you with that.',
        question: text,
        feedbackSubmitted: null,
      });
    } else {
      chatMessages.push({ 
        type: 'bot', 
        text: 'Sorry, I encountered an error. Please try again.' 
      });
    }
  } catch (error) {
    console.error('Chat error:', error);
    chatMessages.push({ 
      type: 'bot', 
      text: 'Network error. Please check your connection.' 
    });
  }

  renderChat();

  // Remove auto-redirect - let user decide when to explore pathways
}

function useSuggestion(el) {
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = el.textContent;
    sendMessage();
  }
}

function renderChat() {
  const box = document.getElementById('chat-box');
  if (!box) return;

  if (chatMessages.length === 0) {
    box.innerHTML = `
      <div class="chat-empty">
        <img class="chat-empty-img" src="images/AI assistant graphic.jpg" alt="CBC Guidance AI" loading="lazy">
        <h3>CBC Guidance Assistant</h3>
        <p>Ask me anything about CBC pathways, subject combinations, school recommendations, and career options.</p>
        <div class="chat-suggestions">
          <span class="chat-suggestion" onclick="useSuggestion(this)">What does EE2 mean?</span>
          <span class="chat-suggestion" onclick="useSuggestion(this)">Best subjects for STEM?</span>
          <span class="chat-suggestion" onclick="useSuggestion(this)">Schools in Meru for STEM</span>
          <span class="chat-suggestion" onclick="useSuggestion(this)">Which pathway suits me?</span>
        </div>
      </div>
    `;
    return;
  }

  const userName = localStorage.getItem('userName') || 'You';
  const initials = userName.charAt(0).toUpperCase();

  box.innerHTML = '';
  chatMessages.forEach((msg, index) => {
    const row = document.createElement('div');
    row.className = `chat-msg-row ${msg.type}`;
    const avatarClass = msg.type === 'bot' ? 'av-bot' : 'av-user';
    const avatarText = msg.type === 'bot' ? 'AI' : initials;
    row.innerHTML = `<div class="chat-msg-avatar ${avatarClass}">${avatarText}</div><div class="chat-msg-text"></div>`;
    const textEl = row.querySelector('.chat-msg-text');
    textEl.textContent = msg.text;

    if (msg.type === 'bot' && msg.question) {
      const feedbackWrap = document.createElement('div');
      feedbackWrap.style.marginTop = '10px';
      feedbackWrap.style.display = 'flex';
      feedbackWrap.style.alignItems = 'center';
      feedbackWrap.style.gap = '8px';
      feedbackWrap.style.flexWrap = 'wrap';

      const label = document.createElement('span');
      label.style.fontSize = '12px';
      label.style.color = 'var(--muted)';
      label.textContent = msg.feedbackSubmitted ? 'Feedback saved' : 'Was this helpful?';
      feedbackWrap.appendChild(label);

      const upBtn = document.createElement('button');
      upBtn.type = 'button';
      upBtn.textContent = 'Thumbs Up';
      upBtn.className = 'btn btn-sm btn-outline-success';
      upBtn.disabled = Boolean(msg.feedbackSubmitted);
      upBtn.addEventListener('click', () => submitChatFeedback(index, 'thumbs_up'));
      feedbackWrap.appendChild(upBtn);

      const downBtn = document.createElement('button');
      downBtn.type = 'button';
      downBtn.textContent = 'Thumbs Down';
      downBtn.className = 'btn btn-sm btn-outline-secondary';
      downBtn.disabled = Boolean(msg.feedbackSubmitted);
      downBtn.addEventListener('click', () => submitChatFeedback(index, 'thumbs_down'));
      feedbackWrap.appendChild(downBtn);

      textEl.appendChild(feedbackWrap);
    }

    box.appendChild(row);
  });
  box.scrollTop = box.scrollHeight;
}

// Stage selection
async function selectStage(stage) {
  const userId = localStorage.getItem('userId');
  
  if (!userId) {
    alert('Please login first');
    navigate('login.html');
    return;
  }

  // Save stage to localStorage
  localStorage.setItem('userStage', stage);
  const existing = await loadAndMergeProfile(userId);
  existing.journey_stage = stage;
  saveStoredProfile(existing);

  // If this stage is already complete, continue directly to chat.
  if (isStageComplete(existing, stage)) {
    navigate('chat.html');
    return;
  }
  
  // Redirect to profile page
  navigate('profile.html');
}

// Profile Info Display
function displayProfileInfo() {
  const profile = getStoredProfile();
  const userEmail = localStorage.getItem('userEmail') || 'N/A';
  const storedName = localStorage.getItem('userName') || '';
  const inferredName = userEmail && userEmail.includes('@') ? userEmail.split('@')[0] : 'User';
  const userName = storedName || inferredName;
  const userSchool = localStorage.getItem('userSchool') || 'Not specified';
  const currentStage = profile?.journey_stage || 'Not selected';
  const selectedPathway = localStorage.getItem('selectedPathway') || '';
  
  // Build stage display text
  const stageDisplayText = currentStage === 'before_exam' ? 'Before Exams' :
                           currentStage === 'after_exam' ? 'After Exams' :
                           currentStage === 'after_placement' ? 'After Placement' : 'Not selected';
  
  // Populate name and email
  const nameEl = document.getElementById('profile-name');
  const emailEl = document.getElementById('profile-email');
  const avatarEl = document.getElementById('profile-avatar');
  if (nameEl) nameEl.textContent = userName;
  if (emailEl) emailEl.textContent = userEmail;
  if (avatarEl) {
    const initials = userName
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part[0].toUpperCase())
      .join('') || 'U';
    avatarEl.textContent = initials;
  }
  
  // Populate details
  const schoolEl = document.getElementById('profile-school');
  const stageEl = document.getElementById('profile-stage');
  const pathwayEl = document.getElementById('profile-pathway');
  const pathwayRow = document.getElementById('profile-pathway-row');
  const favRow = document.getElementById('profile-fav-row');
  const favEl = document.getElementById('profile-favorite-subject');
  const strengthsRow = document.getElementById('profile-strengths-row');
  const strengthsEl = document.getElementById('profile-strength-summary');
  
  if (schoolEl) schoolEl.textContent = userSchool;
  if (stageEl) stageEl.textContent = stageDisplayText;
  
  // Show pathway if available
  const pathwayValue = profile?.placed_pathway || selectedPathway;
  if (pathwayValue && pathwayRow) {
    pathwayEl.textContent = pathwayValue;
    pathwayRow.style.display = 'flex';
  }

  if (profile?.favorite_subject && favRow && favEl) {
    favEl.textContent = profile.favorite_subject;
    favRow.style.display = 'flex';
  }

  if (profile?.strengths && strengthsRow && strengthsEl) {
    strengthsEl.textContent = String(profile.strengths).slice(0, 40);
    strengthsRow.style.display = 'flex';
  }
}

// Profile management
async function saveProfile() {
  const userId = localStorage.getItem('userId');
  const stage = localStorage.getItem('userStage');
  
  if (!userId || !stage) {
    alert('Missing user information. Please start again.');
    navigate('dashboard.html');
    return;
  }

  const existingProfile = getStoredProfile();

  const profileData = { journey_stage: stage };

  const favoriteSubject = document.getElementById('favorite-subject')?.value || '';
  const interests = document.getElementById('interests')?.value || '';
  const strengths = document.getElementById('strengths')?.value || '';
  const careerInterests = document.getElementById('career-interests')?.value || '';
  const learningStyle = document.getElementById('learning-style')?.value || '';

  // Only set common fields when user is in stage 1 or explicitly entered values.
  if (stage === 'before_exam' || favoriteSubject) profileData.favorite_subject = favoriteSubject;
  if (stage === 'before_exam' || interests) profileData.interests = interests;
  if (stage === 'before_exam' || strengths) profileData.strengths = strengths;
  if (stage === 'before_exam' || careerInterests) profileData.career_interests = careerInterests;
  if (stage === 'before_exam' || learningStyle) profileData.learning_style = learningStyle;

  if (stage === 'before_exam') {
    profileData.explore_goals = document.getElementById('explore-goals')?.value || '';
  }

  if (stage === 'after_exam') {
    const stemPathwayScore = document.getElementById('stem-pathway-score')?.value;
    const socialPathwayScore = document.getElementById('social-pathway-score')?.value;
    const artsPathwayScore = document.getElementById('arts-pathway-score')?.value;

    if (stemPathwayScore === '' || socialPathwayScore === '' || artsPathwayScore === '') {
      alert('Please enter all three CBC pathway scores for Stage 2.');
      return;
    }
    profileData.stem_score = parseFloat(stemPathwayScore);
    profileData.social_sciences_score = parseFloat(socialPathwayScore);
    profileData.arts_sports_score = parseFloat(artsPathwayScore);

    const collected = collectCBCSubjectResultsFromForm();
    if (collected.missing.length > 0) {
      alert(`Please complete all CBC subjects. Missing: ${collected.missing.join(', ')}`);
      return;
    }
    profileData.cbc_subject_count = collected.subjects.length;
  }

  if (stage === 'after_placement') {
    const placedSchool = document.getElementById('placed-school')?.value || '';
    const placedPathway = document.getElementById('placed-pathway')?.value || '';
    if (placedSchool) profileData.placed_school = placedSchool;
    if (placedPathway) profileData.placed_pathway = placedPathway;
  }

  // Debug: Log what we're sending
  console.log('Stage being sent:', stage);
  console.log('Profile data:', profileData);

  // Stage-specific validation: only require details needed for the selected stage.
  if (stage === 'before_exam') {
    if (!profileData.favorite_subject || !profileData.interests || !profileData.strengths) {
      alert('Please fill in Favorite Subject, Interests, and Strengths for the before-exam stage.');
      return;
    }
  }

  if (stage === 'after_exam') {
    // CBC subject table is already enforced above.
  }

  if (stage === 'after_placement') {
    if (!profileData.placed_school || !profileData.placed_pathway) {
      alert('Please provide placed school and placed pathway for the after-placement stage.');
      return;
    }
  }

  try {
    // Save to backend
    const response = await fetch(`${API_BASE}/user-profile/${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profileData)
    });

    if (response.ok) {
      if (stage === 'after_exam') {
        const collected = collectCBCSubjectResultsFromForm();

        const cbcPayload = {
          subjects: collected.subjects,
          stem_pathway_score: profileData.stem_score ?? null,
          social_sciences_pathway_score: profileData.social_sciences_score ?? null,
          arts_sports_pathway_score: profileData.arts_sports_score ?? null,
          recommended_pathway: null,
        };

        if (collected.subjects.length > 0) {
          await fetch(`${API_BASE}/cbc-results/?user_id=${encodeURIComponent(userId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(cbcPayload),
          });
        }
      }

      // Merge with existing profile so users don't lose previously captured stage details.
      const frontendProfile = {
        ...existingProfile,
        ...profileData,
        journey_stage: stage,
      };
      saveStoredProfile(frontendProfile);
      localStorage.removeItem('pendingStageMissing');
      alert('Profile saved successfully! Let\'s start your personalized guidance.');
      navigate('chat.html');
    } else {
      throw new Error('Failed to save profile');
    }
  } catch (error) {
    console.error('Profile save error:', error);
    alert('Error saving profile. Please try again.');
  }
}

// Pathway selection
async function selectPathway(pathway) {
  pathwayChosen = pathway;
  const userId = localStorage.getItem('userId');
  
  if (!userId) {
    alert('Please login first');
    navigate('login.html');
    return;
  }

  try {
    // Save pathway selection to backend
    await fetch(`${API_BASE}/update-profile/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        journey_stage: 'pathway_selected',
        selected_pathway: pathway
      })
    });

    navigate(`schools.html?pathway=${encodeURIComponent(pathway)}`);
  } catch (error) {
    console.error('Pathway selection error:', error);
    alert('Error saving pathway selection');
  }
}

// Schools display
const schoolsState = {
  page: 1,
  pageSize: 30,
  pathway: '',
  county: '',
  schoolType: '',
  gender: '',
  search: '',
};

function readSchoolsFiltersFromUI() {
  const searchInput = document.getElementById('schools-search');
  const pathwaySelect = document.getElementById('schools-pathway');
  const countyInput = document.getElementById('schools-county');
  const typeSelect = document.getElementById('schools-type');
  const genderSelect = document.getElementById('schools-gender');

  if (searchInput) schoolsState.search = searchInput.value.trim();
  if (pathwaySelect) schoolsState.pathway = pathwaySelect.value;
  if (countyInput) schoolsState.county = countyInput.value.trim();
  if (typeSelect) schoolsState.schoolType = typeSelect.value;
  if (genderSelect) schoolsState.gender = genderSelect.value;
}

function syncSchoolsFiltersToUI() {
  const searchInput = document.getElementById('schools-search');
  const pathwaySelect = document.getElementById('schools-pathway');
  const countyInput = document.getElementById('schools-county');
  const typeSelect = document.getElementById('schools-type');
  const genderSelect = document.getElementById('schools-gender');

  if (searchInput) searchInput.value = schoolsState.search || '';
  if (pathwaySelect) pathwaySelect.value = schoolsState.pathway || '';
  if (countyInput) countyInput.value = schoolsState.county || '';
  if (typeSelect) typeSelect.value = schoolsState.schoolType || '';
  if (genderSelect) genderSelect.value = schoolsState.gender || '';
}

function renderSchoolsSummary(total) {
  const summary = document.getElementById('schools-summary');
  if (!summary) return;

  const from = total === 0 ? 0 : ((schoolsState.page - 1) * schoolsState.pageSize) + 1;
  const to = Math.min(schoolsState.page * schoolsState.pageSize, total);
  const mode = schoolsState.pathway
    ? `Filtered by pathway: ${schoolsState.pathway}`
    : 'Showing all schools';

  summary.textContent = `${mode} · Showing ${from}-${to} of ${total}`;
}

function renderSchoolsPagination(totalPages) {
  const container = document.getElementById('schools-pagination');
  if (!container) return;

  if (!totalPages || totalPages <= 1) {
    container.innerHTML = '';
    return;
  }

  const prevDisabled = schoolsState.page <= 1 ? 'disabled' : '';
  const nextDisabled = schoolsState.page >= totalPages ? 'disabled' : '';

  container.innerHTML = `
    <button class="page-btn" ${prevDisabled} onclick="changeSchoolsPage(${schoolsState.page - 1})">< Prev</button>
    <span style="font-size:12px;color:var(--muted);">Page ${schoolsState.page} of ${totalPages}</span>
    <button class="page-btn" ${nextDisabled} onclick="changeSchoolsPage(${schoolsState.page + 1})">Next ></button>
  `;
}

function changeSchoolsPage(nextPage) {
  if (nextPage < 1) return;
  schoolsState.page = nextPage;
  displaySchools();
}

function bindSchoolsControls() {
  const applyBtn = document.getElementById('schools-apply');
  const clearBtn = document.getElementById('schools-clear');
  const searchInput = document.getElementById('schools-search');

  if (applyBtn && !applyBtn.dataset.bound) {
    applyBtn.addEventListener('click', () => {
      schoolsState.page = 1;
      readSchoolsFiltersFromUI();
      displaySchools();
    });
    applyBtn.dataset.bound = '1';
  }

  if (clearBtn && !clearBtn.dataset.bound) {
    clearBtn.addEventListener('click', () => {
      schoolsState.page = 1;
      schoolsState.pathway = '';
      schoolsState.county = '';
      schoolsState.schoolType = '';
      schoolsState.gender = '';
      schoolsState.search = '';
      localStorage.removeItem('selectedPathway');
      syncSchoolsFiltersToUI();
      displaySchools();
    });
    clearBtn.dataset.bound = '1';
  }

  if (searchInput && !searchInput.dataset.bound) {
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        schoolsState.page = 1;
        readSchoolsFiltersFromUI();
        displaySchools();
      }
    });
    searchInput.dataset.bound = '1';
  }
}

async function displaySchools() {
  const list = document.getElementById('schools-list');
  if (!list) return;
  
  list.innerHTML = '<div class="text-center"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Loading schools...</p></div>';

  try {
    const queryParams = new URLSearchParams(window.location.search);
    const pathwayFromUrl = queryParams.get('pathway');
    pathwayChosen = pathwayFromUrl || schoolsState.pathway || '';

    if (!schoolsState.pathway) {
      schoolsState.pathway = pathwayChosen;
    }

    bindSchoolsControls();
    syncSchoolsFiltersToUI();
    readSchoolsFiltersFromUI();

    const params = new URLSearchParams();
    params.set('page', String(schoolsState.page));
    params.set('page_size', String(schoolsState.pageSize));
    if (schoolsState.pathway) params.set('pathway', schoolsState.pathway);
    if (schoolsState.county) params.set('county', schoolsState.county);
    if (schoolsState.schoolType) params.set('school_type', schoolsState.schoolType);
    if (schoolsState.gender) params.set('gender', schoolsState.gender);
    if (schoolsState.search) params.set('q', schoolsState.search);

    const url = `${API_BASE}/schools?${params.toString()}`;

    const response = await fetch(url);
    
    if (response.ok) {
      const data = await response.json();
      const schools = data.schools || [];
      const total = Number(data.total || schools.length || 0);
      const totalPages = Number(data.total_pages || 0);
      
      list.innerHTML = '';
      
      if (schools.length === 0) {
        list.innerHTML = `
          <div class="schools-empty">
            <p>No schools found matching your criteria. Try adjusting pathway, county, or school type filters.</p>
          </div>
        `;
        renderSchoolsSummary(total);
        renderSchoolsPagination(totalPages);
        return;
      }

      schools.forEach(school => {
        const div = document.createElement('div');
        div.className = 'school-card';
        const pathways = Array.isArray(school.pathways_offered)
          ? school.pathways_offered
          : (school.pathways_offered ? [school.pathways_offered] : []);
        const pathwayTags = pathways.map(p => `<span class="school-tag green">${p}</span>`).join('');
        const schoolName = school.name || school.school_name || 'Unnamed School';
        const schoolCounty = school.county || 'Unknown county';
        const schoolType = school.type || school.school_type || 'School';
        const schoolGender = school.gender || 'N/A';
        div.innerHTML = `
          <div class="school-card-name">${schoolName}</div>
          <div class="school-card-meta">
            <span class="school-tag">County: ${schoolCounty}</span>
            <span class="school-tag">Type: ${schoolType}</span>
            <span class="school-tag">Gender: ${schoolGender}</span>
            ${school.accommodation ? `<span class="school-tag">Accommodation: ${school.accommodation}</span>` : ''}
            ${pathwayTags}
          </div>
        `;
        list.appendChild(div);
      });

      renderSchoolsSummary(total);
      renderSchoolsPagination(totalPages);
    } else {
      throw new Error(`Failed to load schools (HTTP ${response.status})`);
    }
  } catch (error) {
    console.error('Schools loading error:', error);
    
    // Show error message instead of mock data
    list.innerHTML = `
      <div class="alert alert-warning">
        <h5>Unable to load school data</h5>
        <p>Please ensure the backend server is running on port 8001.</p>
        <p>If the problem persists, contact support.</p>
      </div>
    `;
  }
}

function getBasePath() {
  const path = window.location.pathname;
  return path.substring(0, path.lastIndexOf('/') + 1);
}

function navigate(page) {
  window.location = getBasePath() + page;
}

function checkAuth() {
  const userId = localStorage.getItem('userId');
  const path = window.location.pathname;
  const isPublic = path.includes('index.html') || 
                   path.includes('login.html') || 
                   path.includes('signup.html') ||
                   path.endsWith('/frontend/') ||
                   path.endsWith('/frontend');
  if (!userId && !isPublic) {
    navigate('login.html');
    return false;
  }
  return true;
}

// Logout
function logout() {
  localStorage.removeItem('userId');
  localStorage.removeItem('userEmail');
  localStorage.removeItem('userName');
  localStorage.removeItem('userProfile');
  localStorage.removeItem('userStage');
  localStorage.removeItem('pendingStageMissing');
  localStorage.removeItem('profileOwnerUserId');
  clearPostLoginRedirect();
  navigate('index.html');
}

// ============================================================
// SIDEBAR RENDERER
// ============================================================
function renderSidebar() {
  const sidebar = document.getElementById('app-sidebar');
  if (!sidebar) return;

  const page = window.location.pathname.split('/').pop() || 'index.html';
  const userName = localStorage.getItem('userName') || localStorage.getItem('userEmail') || 'Student';
  const initials = userName.substring(0, 2).toUpperCase();

  const navItems = [
    { href: 'dashboard.html', label: 'Dashboard', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>' },
    { href: 'chat.html',      label: 'Chat',      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>' },
    { href: 'schools.html',   label: 'Find Schools', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>' },
    { href: 'pathway.html',   label: 'Pathways',  icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>' },
    { href: 'profile.html',   label: 'My Profile', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>' },
  ];

  const links = navItems.map(item =>
    `<a href="${item.href}" class="sidebar-link ${page === item.href ? 'active' : ''}">${item.icon}<span>${item.label}</span></a>`
  ).join('');

  sidebar.innerHTML = `
    <div class="sidebar-header">
      <a href="dashboard.html" class="sidebar-brand">
        <div class="sidebar-brand-icon">CG</div>
        <span>CBC Guide</span>
      </a>
    </div>
    <div class="sidebar-nav">
      <div class="sidebar-section-label">Navigation</div>
      ${links}
    </div>
    <div class="sidebar-footer">
      <div class="user-badge">
        <div class="user-avatar">${initials}</div>
        <span class="user-name">${userName}</span>
      </div>
      <button type="button" class="sidebar-link theme-toggle-button theme-toggle-sidebar" onclick="toggleTheme()">
        <span class="theme-toggle-icon">◐</span>
        <span class="theme-toggle-text">Dark mode</span>
      </button>
      <button class="sidebar-link" onclick="logout()" style="color:rgba(255,255,255,0.55);">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        <span>Log out</span>
      </button>
    </div>
  `;

  // Mobile toggle
  const toggle = document.getElementById('sidebar-toggle');
  const overlay = document.getElementById('sidebar-overlay');
  if (toggle) {
    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      if (overlay) overlay.classList.toggle('show');
    });
  }
  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.remove('show');
    });
  }

  updateThemeToggleLabels();
}

function initializeThemeControls() {
  const navWrap = document.querySelector('.ix-nav-wrap');
  if (navWrap && !navWrap.querySelector('.ix-theme-toggle')) {
    const desktopToggle = document.createElement('button');
    desktopToggle.type = 'button';
    desktopToggle.className = 'ix-btn ix-btn-outline ix-theme-toggle theme-toggle-button';
    desktopToggle.innerHTML = '<span class="theme-toggle-icon">◐</span><span class="theme-toggle-text">Dark mode</span>';
    desktopToggle.addEventListener('click', toggleTheme);

    const loginLink = navWrap.querySelector('.ix-nav-login');
    if (loginLink) {
      navWrap.insertBefore(desktopToggle, loginLink);
    } else {
      navWrap.appendChild(desktopToggle);
    }
  }

  const mobilePanel = document.querySelector('.ix-mobile-panel');
  if (mobilePanel && !mobilePanel.querySelector('.ix-mobile-theme-toggle')) {
    const mobileToggle = document.createElement('button');
    mobileToggle.type = 'button';
    mobileToggle.className = 'ix-mobile-theme-toggle theme-toggle-button';
    mobileToggle.innerHTML = '<span class="theme-toggle-icon">◐</span><span class="theme-toggle-text">Dark mode</span>';
    mobileToggle.addEventListener('click', toggleTheme);
    mobilePanel.appendChild(mobileToggle);
  }

  const authPage = document.querySelector('.auth-page');
  if (authPage && !document.querySelector('.auth-theme-toggle')) {
    const authToggle = document.createElement('button');
    authToggle.type = 'button';
    authToggle.className = 'auth-theme-toggle theme-toggle-button';
    authToggle.innerHTML = '<span class="theme-toggle-icon">◐</span><span class="theme-toggle-text">Dark mode</span>';
    authToggle.addEventListener('click', toggleTheme);
    document.body.appendChild(authToggle);
  }

  updateThemeToggleLabels();
}

function initializeIndexAnimations() {
  const landing = document.querySelector('.ix-page');
  if (!landing) return;

  const targets = landing.querySelectorAll('.ix-reveal-target');
  if (!targets.length) return;

  targets.forEach((el, index) => {
    el.style.transitionDelay = `${Math.min(index * 70, 320)}ms`;
  });

  if (!('IntersectionObserver' in window)) {
    targets.forEach((el) => el.classList.add('ix-visible'));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('ix-visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.15, rootMargin: '0px 0px -8% 0px' });

  targets.forEach((el) => observer.observe(el));
}

function initializeHeroImageInteractivity() {
  const wrap = document.querySelector('.ix-hero-image-wrap');
  if (!wrap) return;

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const coarsePointer = window.matchMedia('(pointer: coarse)').matches;

  const resetTransform = () => {
    wrap.style.setProperty('--ix-tilt-x', '0deg');
    wrap.style.setProperty('--ix-tilt-y', '0deg');
    wrap.style.setProperty('--ix-float-y', '0px');
  };

  resetTransform();

  const hidden = window.getComputedStyle(wrap).display === 'none';

  if (reduceMotion || coarsePointer || hidden) {
    return;
  }

  let rafId = 0;

  const updateTilt = (clientX, clientY) => {
    const rect = wrap.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const relX = (clientX - rect.left) / rect.width;
    const relY = (clientY - rect.top) / rect.height;

    const tiltX = (relX - 0.5) * 8;
    const tiltY = (0.5 - relY) * 6;

    wrap.style.setProperty('--ix-tilt-x', `${tiltX.toFixed(2)}deg`);
    wrap.style.setProperty('--ix-tilt-y', `${tiltY.toFixed(2)}deg`);
  };

  const onMouseMove = (event) => {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(() => updateTilt(event.clientX, event.clientY));
  };

  wrap.addEventListener('mouseenter', () => {
    wrap.classList.add('is-interactive');
  });

  wrap.addEventListener('mousemove', onMouseMove);

  wrap.addEventListener('mouseleave', () => {
    wrap.classList.remove('is-interactive');
    resetTransform();
  });
}

// Initialize
window.onload = function() {
console.log('Page loaded, checking auth...');

applyTheme(getPreferredTheme(), false);

const isAppLayoutPage = Boolean(document.querySelector('.app-layout'));
if (isAppLayoutPage) {
  document.body.style.overflow = 'hidden';
  document.body.style.height = '100dvh';
} else {
  document.body.style.overflow = '';
  document.body.style.height = '';
}

// Render sidebar on app pages
renderSidebar();
initializeThemeControls();

// Check authentication for protected pages
if (window.location.pathname.includes('dashboard') || 
window.location.pathname.includes('chat') || 
window.location.pathname.includes('schools') ||
window.location.pathname.includes('pathway') ||
window.location.pathname.includes('stage') ||
window.location.pathname.includes('profile')) {
console.log('Protected page detected, checking auth...');
checkAuth();
}

if (window.location.pathname.includes('profile')) {
  displayProfileInfo();
  initializeStageSpecificProfileForm();
}

if (window.location.pathname.includes('dashboard')) {
  // Show greeting
  const greetEl = document.getElementById('dash-greeting');
  if (greetEl) {
    const name = localStorage.getItem('userName');
    if (name) greetEl.textContent = `Welcome back, ${name}! Here's your guidance hub.`;
  }
  const userId = localStorage.getItem('userId');
  if (userId) {
    loadAndMergeProfile(userId).then((profile) => {
      renderStageProgressPanel(profile || getStoredProfile());
    });
  } else {
    renderStageProgressPanel(getStoredProfile());
  }
}

// Show empty state on chat page
if (window.location.pathname.includes('chat')) {
  renderChat();
}

// Load schools if on schools page
if (window.location.pathname.includes('schools')) {
console.log('Schools page detected, loading schools...');
displaySchools();
}

initializeIndexAnimations();
initializeHeroImageInteractivity();
};
