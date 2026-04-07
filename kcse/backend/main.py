# --- Get User Profile by Email ---
from fastapi import Query, Request
import traceback
import fastapi
import logging
import json
from collections import Counter
from results import get_db_connection
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from user.database import create_user_profile, get_user_profile_by_email, delete_user_profile, list_all_users, ensure_user_profiles_schema
import bcrypt
from user.feedback import store_feedback, list_feedback
from user.admin_store import create_announcement, list_announcements, list_support_content, create_support_content, delete_support_content, update_support_content, list_question_logs, summarize_question_logs, update_question_review, create_question_log, question_status_summary
from search.search import perform_semantic_search
from career import router as career_router
from recommendation.conversation_context import list_recent_questions, list_top_questions
logging.basicConfig(level=logging.INFO, force=True)
app = FastAPI()
ADMIN_TOKEN = "kcse_admin_token_2024"
ensure_user_profiles_schema()

# Add a global exception handler for better error logging
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("\n--- Exception Occurred ---")
    print(f"URL: {request.url}")
    print(f"Exception: {exc}")
    traceback.print_exc()
    print("--- End Exception ---\n")
    return fastapi.responses.JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )

@app.get("/user/profile")
def get_user_profile(email: str = Query(...)):
    user = get_user_profile_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user
# Add CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or specify your frontend URL instead of "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(career_router)

# --- User Signup ---
class UserSignupRequest(BaseModel):
    name: str
    email: str
    password: str
    mean_grade: str = ""
    interests: str = ""
    career_goals: str = ""
    subjects: list = []
    extra_data: dict = {}

@app.post("/signup")
def signup(request: UserSignupRequest):
    if get_user_profile_by_email(request.email):
        raise HTTPException(status_code=400, detail="Email already registered.")
    user_id = create_user_profile(request)
    return {"user_id": user_id, "message": "Signup successful."}

# --- User Signin ---
class UserSigninRequest(BaseModel):
    email: str
    password: str


@app.post("/signin")
def signin(request: UserSigninRequest):
    user = get_user_profile_by_email(request.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    # Password hash check
    # Fetch hashed password from DB
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password FROM user_profiles WHERE email = %s", (request.email,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="User not found.")
                hashed_password = row[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not verify password.")
    if not bcrypt.checkpw(request.password.encode('utf-8'), hashed_password.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Incorrect password.")
    return {"user_id": user["user_id"], "message": "Signin successful."}

# --- Admin Login ---
class AdminSigninRequest(BaseModel):
    email: str
    password: str

class AnnouncementCreateRequest(BaseModel):
    title: str
    message: str

class SupportContentCreateRequest(BaseModel):
    title: str
    category: str
    content: str
    status: str = "draft"

class QuestionReviewRequest(BaseModel):
    reviewed: bool = True
    review_note: str = ""

def require_admin_token(authorization: str = Header(default="")):
    expected_value = f"Bearer {ADMIN_TOKEN}"
    if authorization != expected_value:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")

def parse_extra_data(extra_data):
    if not extra_data:
        return {}
    if isinstance(extra_data, str):
        try:
            return json.loads(extra_data)
        except Exception:
            return {}
    return extra_data

def bucket_date_strings(values):
    counts = Counter(values)
    return [
        {"label": label, "value": counts[label]}
        for label in sorted(counts.keys())
    ]

def get_usage_timeline():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DATE(timestamp) AS day, COUNT(*)
                    FROM conversation_context
                    GROUP BY DATE(timestamp)
                    ORDER BY day ASC
                    LIMIT 14
                """)
                rows = cur.fetchall()
                return [
                    {"label": row[0].isoformat(), "value": row[1]}
                    for row in rows
                ]
    except Exception:
        return []

@app.post("/admin/login")
def admin_login(request: AdminSigninRequest):
    # Check admin credentials (you can modify these)
    ADMIN_EMAIL = "admin@kcse.com"
    ADMIN_PASSWORD = "admin123"
    
    if request.email != ADMIN_EMAIL:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    
    if request.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    
    # Return admin token and info
    return {
        "token": ADMIN_TOKEN,
        "admin": {
            "email": request.email,
            "name": "KCSE Administrator"
        }
    }

# --- Admin: Delete User ---
@app.delete("/admin/user/{user_id}")
def admin_delete_user(user_id: str, _: None = fastapi.Depends(require_admin_token)):
    delete_user_profile(user_id)
    return {"message": f"User {user_id} deleted."}

# --- Admin: List All Users ---
@app.get("/admin/users")
def admin_list_users(_: None = fastapi.Depends(require_admin_token)):
    users = list_all_users()
    return {"users": users}

@app.get("/admin/stats")
def admin_stats(_: None = fastapi.Depends(require_admin_token)):
    users = list_all_users()
    feedback_items = list_feedback()
    announcements = list_announcements()
    support_items = list_support_content()
    usage_timeline = get_usage_timeline()
    total_chats = sum(item.get("value", 0) for item in usage_timeline)
    return {
        "total_users": len(users),
        "feedback_count": len(feedback_items),
        "announcement_count": len(announcements),
        "support_content_count": len(support_items),
        "total_chats": total_chats,
        "recent_users": users[-5:]
    }

@app.get("/admin/analytics")
def admin_analytics(_: None = fastapi.Depends(require_admin_token)):
    users = list_all_users()
    feedback_items = list_feedback()
    usage_timeline = get_usage_timeline()

    subject_counter = Counter()
    combination_counter = Counter()
    interest_counter = Counter()
    mean_grade_counter = Counter()
    signup_dates = []

    for user in users:
        extra_data = parse_extra_data(user.get("extra_data"))
        subjects = extra_data.get("subjects", [])
        if isinstance(subjects, list):
            cleaned_subjects = [str(subject).strip() for subject in subjects if str(subject).strip()]
            subject_counter.update(cleaned_subjects)
            if cleaned_subjects:
                combination_counter[", ".join(sorted(cleaned_subjects))] += 1

        interests = user.get("interests", "")
        if interests:
            parts = [part.strip() for part in str(interests).replace(";", ",").split(",") if part.strip()]
            if parts:
                interest_counter.update(parts)
            else:
                interest_counter.update([str(interests).strip()])

        mean_grade = str(user.get("mean_grade", "")).strip()
        if mean_grade:
            mean_grade_counter[mean_grade] += 1

        created_at = user.get("created_at")
        if created_at:
            signup_dates.append(str(created_at)[:10])

    return {
        "totals": {
            "users": len(users),
            "feedback": len(feedback_items),
            "subject_entries": sum(subject_counter.values()),
            "signups_timeline_available": len(signup_dates) > 0,
            "usage_timeline_available": len(usage_timeline) > 0
        },
        "top_subjects": [
            {"label": label, "value": value}
            for label, value in subject_counter.most_common(8)
        ],
        "top_subject_combinations": [
            {"label": label, "value": value}
            for label, value in combination_counter.most_common(5)
        ],
        "common_interests": [
            {"label": label, "value": value}
            for label, value in interest_counter.most_common(8)
        ],
        "mean_grade_distribution": [
            {"label": label, "value": value}
            for label, value in mean_grade_counter.most_common()
        ],
        "signups_over_time": bucket_date_strings(signup_dates),
        "usage_trends": usage_timeline
    }

@app.get("/admin/feedback")
def admin_feedback(_: None = fastapi.Depends(require_admin_token)):
    return {"feedback": list_feedback()}

@app.get("/admin/questions")
def admin_questions(
    _: None = fastapi.Depends(require_admin_token),
    status: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    date_from: str | None = Query(default=None)
):
    failed_queries = list_question_logs(status="failed", topic=topic, date_from=date_from)
    no_result_queries = list_question_logs(status="no_result", topic=topic, date_from=date_from)
    combined_failed = sorted(
        failed_queries + no_result_queries,
        key=lambda item: item.get("created_at", ""),
        reverse=True
    )[:20]
    return {
        "recent_questions": list_question_logs(status=status, topic=topic, date_from=date_from)[:20],
        "top_questions": summarize_question_logs(status=status, topic=topic, date_from=date_from),
        "failed_queries": combined_failed,
        "status_summary": question_status_summary(topic=topic, date_from=date_from)
    }

@app.patch("/admin/questions/{item_id}/review")
def admin_review_question(item_id: str, request: QuestionReviewRequest, _: None = fastapi.Depends(require_admin_token)):
    updated = update_question_review(item_id, request.reviewed, request.review_note)
    if not updated:
        raise HTTPException(status_code=404, detail="Question log not found")
    return {"message": "Question review updated.", "item": updated}

@app.get("/admin/questions/export", response_class=PlainTextResponse)
def admin_export_questions(
    _: None = fastapi.Depends(require_admin_token),
    status: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    date_from: str | None = Query(default=None)
):
    items = list_question_logs(status=status, topic=topic, date_from=date_from)
    lines = ["created_at,status,topic,reviewed,question,response"]
    for item in items:
        row = [
            str(item.get("created_at", "")).replace(",", " "),
            str(item.get("status", "")).replace(",", " "),
            str(item.get("topic", "")).replace(",", " "),
            str(item.get("reviewed", False)),
            str(item.get("question", "")).replace(",", " "),
            str(item.get("response", "")).replace(",", " ").replace("\n", " ")
        ]
        lines.append(",".join(row))
    return "\n".join(lines)

@app.get("/admin/announcements")
def admin_get_announcements(_: None = fastapi.Depends(require_admin_token)):
    return {"announcements": list_announcements()}

@app.post("/admin/announcements")
def admin_create_announcement(request: AnnouncementCreateRequest, authorization: str = Header(default="")):
    require_admin_token(authorization)
    created_by = "KCSE Administrator"
    announcement = create_announcement(request.title.strip(), request.message.strip(), created_by)
    return {"message": "Announcement created.", "announcement": announcement}

@app.get("/admin/content")
def admin_get_content(_: None = fastapi.Depends(require_admin_token)):
    return {"items": list_support_content()}

@app.post("/admin/content")
def admin_create_content(request: SupportContentCreateRequest, authorization: str = Header(default="")):
    require_admin_token(authorization)
    item = create_support_content(
        request.title.strip(),
        request.category.strip() or "General",
        request.content.strip(),
        request.status.strip() or "draft",
        "KCSE Administrator"
    )
    return {"message": "Content item created.", "item": item}

@app.delete("/admin/content/{item_id}")
def admin_delete_content(item_id: str, _: None = fastapi.Depends(require_admin_token)):
    deleted = delete_support_content(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Content item not found")
    return {"message": "Content item deleted."}

@app.put("/admin/content/{item_id}")
def admin_update_content(item_id: str, request: SupportContentCreateRequest, _: None = fastapi.Depends(require_admin_token)):
    item = update_support_content(
        item_id,
        request.title.strip(),
        request.category.strip() or "General",
        request.content.strip(),
        request.status.strip() or "draft"
    )
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    return {"message": "Content item updated.", "item": item}

@app.get("/content/published")
def get_published_content():
    items = list_support_content()
    published_items = [
        item for item in items
        if str(item.get("status", "")).lower() == "published"
    ]
    return {"items": published_items}

# --- Feedback ---
class FeedbackRequest(BaseModel):
    user_id: str = ""
    recommendation_id: str = ""
    feedback_text: str = ""
    rating: int = 0

@app.post("/feedback")
def submit_feedback(request: FeedbackRequest):
    store_feedback(request.user_id, request.recommendation_id, request.feedback_text, request.rating)
    return {"message": "Feedback received. Thank you!"}

# --- Search ---
class SearchRequest(BaseModel):
    query: str
    user_profile: str = ""
    conversation_id: str = ""
    history: list = []

@app.post("/search")
def semantic_search(request: SearchRequest):
    try:
        return perform_semantic_search(
            request.query,
            request.user_profile,
            conversation_id=request.conversation_id,
            history=request.history
        )
    except Exception as exc:
        if request.conversation_id and request.query:
            try:
                create_question_log(
                    conversation_id=request.conversation_id,
                    question=request.query,
                    response=str(exc),
                    status="failed",
                    topic="General"
                )
            except Exception:
                pass
        raise

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Server startup
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting KCSE Server on http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
