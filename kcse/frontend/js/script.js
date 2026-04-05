const API_BASE = "http://localhost:8000";

const state = {
  user: JSON.parse(localStorage.getItem("user")) || null,
  chats: JSON.parse(localStorage.getItem("chats")) || [],
  currentChatId: localStorage.getItem("currentChatId") || null
};

const STARTER_PROMPTS = [
  "What can I study with my grades?",
  "computer science",
  "what are the requirements?",
  "I want career guidance based on my profile"
];

// Elements
const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatList = document.getElementById("chat-list");
const newChatBtn = document.getElementById("new-chat-btn");
const searchInput = document.getElementById("search-input");
const profileBtn = document.getElementById("profile-btn");
const profileMenu = document.getElementById("profile-menu");
const sidebarSectionTitle = document.querySelector(".sidebar-section-title");

function saveState() {
  localStorage.setItem("user", JSON.stringify(state.user));
  localStorage.setItem("chats", JSON.stringify(state.chats));
  localStorage.setItem("currentChatId", state.currentChatId);
}

function getUserInitial() {
  const name = state.user?.name || state.user?.email || "User";
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 1)
    .toUpperCase() || "U";
}

function updateProfileButton() {
  const initial = getUserInitial();
  profileBtn.style.setProperty("--profile-initial", `"${initial}"`);
}

async function apiRequest(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Error");
  return data;
}

function appendMessage(role, text) {
  const msg = document.createElement("div");
  msg.className = `chat-msg-row ${role}`;

  // Remove asterisks and clean up text
  let cleanText = text.replace(/\*/g, '').trim();
  
  // Convert multiple spaces to single space
  cleanText = cleanText.replace(/  +/g, ' ');
  
  // Preserve paragraph breaks (double newlines)
  cleanText = cleanText.replace(/\n\n+/g, '</p><p>');
  
  // Convert single newlines to line breaks
  cleanText = cleanText.replace(/\n/g, '<br>');

  msg.innerHTML = `
    <div class="chat-msg-text">${cleanText}</div>
  `;

  chatWindow.appendChild(msg);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return msg;
}

function renderEmptyState() {
  chatWindow.innerHTML = `
    <section class="chat-empty">
      </div>
      <h3>KCSE Guidance Assistant</h3>
      <p>Ask me about university courses, career paths, programme requirements, and options that match your grades.</p>
      <div class="starter-grid">
        ${STARTER_PROMPTS.map(prompt => `<button class="starter-chip" type="button">${prompt}</button>`).join("")}
      </div>
    </section>
  `;

  chatWindow.querySelectorAll(".starter-chip").forEach((button) => {
    button.addEventListener("click", () => {
      chatInput.value = button.textContent;
      chatInput.focus();
    });
  });
}

function createNewChat() {
  const userKey = state.user?.user_id || state.user?.email || "anon";
  const chat = { id: `${userKey}-${Date.now()}`, messages: [], title: null };
  state.chats.push(chat);
  state.currentChatId = chat.id;
  saveState();
  renderChatList();
  renderMessages();
}

function renderChatList() {
  chatList.innerHTML = "";

  state.chats
    .filter(chat => chat.messages.length > 0 || chat.id === state.currentChatId)
    .forEach(chat => {
      const div = document.createElement("div");
      div.className = "chat-item";
      if (chat.id === state.currentChatId) {
        div.classList.add("active");
      }
      div.textContent = chat.title || "New chat";

      div.onclick = () => {
        state.currentChatId = chat.id;
        saveState();
        renderChatList();
        renderMessages();
      };

      chatList.appendChild(div);
    });
}

function renderMessages() {
  chatWindow.innerHTML = "";
  const chat = state.chats.find(item => item.id === state.currentChatId);
  if (!chat) return;

  if (!chat.messages.length) {
    renderEmptyState();
    return;
  }

  chat.messages.forEach(message => appendMessage(message.role, message.text));
}

function formatSearchReply(data) {
  if (data.message) {
    return data.message;
  }

  if (typeof data.reranked === "string") {
    return data.reranked;
  }

  if (Array.isArray(data.reranked)) {
    return data.reranked.map(item => item.title || item).join("\n");
  }

  if (Array.isArray(data.results) && data.results.length > 0) {
    return data.results
      .slice(0, 5)
      .map(item => {
        const row = item.data || [];
        const institution = row[1] || "Unknown institution";
        const programme = row[2] || "Programme";
        return `[${item.source}] ${institution} - ${programme}`;
      })
      .join("\n");
  }

  return "No response.";
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const msg = chatInput.value.trim();
  if (!msg) return;

  let chat = state.chats.find(item => item.id === state.currentChatId);
  if (!chat) {
    createNewChat();
    chat = state.chats.find(item => item.id === state.currentChatId);
  }

  chat.messages.push({ role: "user", text: msg });
  if (!chat.title) chat.title = msg.slice(0, 30);

  appendMessage("user", msg);
  chatInput.value = "";
  renderChatList();

  const loading = appendMessage("bot", "Thinking...");

  try {
    const data = await apiRequest("/search", {
      query: msg,
      user_profile: JSON.stringify(state.user),
      conversation_id: chat.id,
      history: chat.messages
    });

    loading.remove();

    const reply = formatSearchReply(data);
    chat.messages.push({ role: "bot", text: reply });

    appendMessage("bot", reply);
    saveState();
    renderChatList();
  } catch (error) {
    loading.remove();
    appendMessage("bot", error.message || "Server error.");
  }
});

newChatBtn.onclick = () => {
  createNewChat();
};

searchInput.addEventListener("input", () => {
  const q = searchInput.value.toLowerCase();

  document.querySelectorAll(".chat-item").forEach(item => {
    item.style.display = item.textContent.toLowerCase().includes(q) ? "block" : "none";
  });
});

profileBtn.onclick = (e) => {
  e.stopPropagation();
  profileMenu.classList.toggle("show");
};

document.addEventListener("click", (e) => {
  if (!profileBtn.contains(e.target) && !profileMenu.contains(e.target)) {
    profileMenu.classList.remove("show");
  }
});

profileMenu.addEventListener("click", (e) => {
  e.stopPropagation();
});

sidebarSectionTitle.onclick = () => {
  const chatListElement = document.getElementById("chat-list");
  const chevron = sidebarSectionTitle.querySelector(".bi-chevron-down");
  const isHidden = chatListElement.style.display === "none";
  
  chatListElement.style.display = isHidden ? "block" : "none";
  
  if (isHidden) {
    chevron.classList.remove("rotated");
  } else {
    chevron.classList.add("rotated");
  }
};

document.getElementById("logout").onclick = () => {
  localStorage.clear();
  window.location.href = "signin.html";
};

document.getElementById("view-profile").onclick = () => {
  window.location.href = "profile.html";
};

window.onload = () => {
  if (!state.user) {
    window.location.href = "signin.html";
    return;
  }

  updateProfileButton();

  if (!state.currentChatId || !state.chats.find(chat => chat.id === state.currentChatId)) {
    createNewChat();
  }

  renderChatList();
  renderMessages();
  chatInput.focus();
};
