const API_BASE = "https://kcse-backend.onrender.com";
const GRADE_POINTS = {
  "A": 12,
  "A-": 11,
  "B+": 10,
  "B": 9,
  "B-": 8,
  "C+": 7,
  "C": 6,
  "C-": 5,
  "D+": 4,
  "D": 3,
  "D-": 2,
  "E": 1
};

function inferMeanGrade(subjects) {
  if (!Array.isArray(subjects) || subjects.length === 0) return "";

  const points = subjects
    .map((entry) => {
      const parts = String(entry).split(":");
      const grade = (parts[1] || "").trim().toUpperCase();
      return GRADE_POINTS[grade];
    })
    .filter((value) => typeof value === "number");

  if (points.length === 0) return "";

  const average = points.reduce((sum, value) => sum + value, 0) / points.length;
  return Object.entries(GRADE_POINTS).reduce((closest, current) => {
    return Math.abs(current[1] - average) < Math.abs(closest[1] - average) ? current : closest;
  })[0];
}

document.querySelectorAll(".password-toggle").forEach((button) => {
  button.addEventListener("click", () => {
    const targetId = button.getAttribute("data-target");
    const passwordInput = document.getElementById(targetId);
    const showingPassword = passwordInput.type === "text";

    passwordInput.type = showingPassword ? "password" : "text";
    button.setAttribute("aria-label", showingPassword ? "Show password" : "Hide password");
    button.setAttribute("aria-pressed", String(!showingPassword));
    button.querySelector(".password-eye-open").classList.toggle("d-none", !showingPassword);
    button.querySelector(".password-eye-closed").classList.toggle("d-none", showingPassword);
  });
});

// --- API ---
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

// --- Signin Form Handler ---
document.getElementById("signin-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const email = document.getElementById("signin-email").value;
  const password = document.getElementById("signin-password").value;
  const msgElement = document.getElementById("signin-msg");

  try {
    const signinResult = await apiRequest("/signin", { email, password });
    
    // Fetch complete user data from backend
    let userData = { email };
    try {
      const userProfile = await fetch(`${API_BASE}/user/profile?email=${email}`)
        .then(res => res.json());
      
      // Extract subjects from extra_data if available
      let subjects = [];
      if (userProfile.extra_data && userProfile.extra_data.subjects) {
        subjects = userProfile.extra_data.subjects;
      }
      
      userData = {
        user_id: signinResult.user_id,
        email: email,
        name: userProfile.name || "",
        mean_grade: userProfile.mean_grade || inferMeanGrade(subjects),
        interests: userProfile.interests || "",
        career_goals: userProfile.career_goals || "",
        subjects: subjects
      };
    } catch (profileErr) {
      console.log("Could not fetch full profile, using basic data");
    }
    
    // Save user data to localStorage
    localStorage.setItem("user", JSON.stringify(userData));
    
    // Redirect to main page
    window.location.href = "/kcse/frontend/index.html";
    
  } catch (err) {
    msgElement.textContent = err.message;
    msgElement.style.display = "block";
  }
});

// Clear message when user starts typing
document.getElementById("signin-email").addEventListener("input", () => {
  document.getElementById("signin-msg").style.display = "none";
});

document.getElementById("signin-password").addEventListener("input", () => {
  document.getElementById("signin-msg").style.display = "none";
});
