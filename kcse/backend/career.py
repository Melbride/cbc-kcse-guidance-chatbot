# career.py
"""
Career exploration logic for undecided students.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class CareerExplorationRequest(BaseModel):
    mean_grade: str
    interests: str = ""
    career_goals: str = ""
    subjects: list = []

GRADE_POINTS = {
    "A": 12, "A-": 11, "B+": 10, "B": 9, "B-": 8, "C+": 7, "C": 6, "C-": 5, "D+": 4, "D": 3, "D-": 2, "E": 1
}

@router.post("/career/explore")
def career_exploration(request: CareerExplorationRequest):
    mean_grade = request.mean_grade.strip().upper()
    interests = request.interests.strip()
    career_goals = request.career_goals.strip()
    if mean_grade not in GRADE_POINTS:
        raise HTTPException(status_code=400, detail="Invalid mean grade")
    if not (7 <= len(request.subjects) <= 8):
        raise HTTPException(status_code=400, detail="Number of subjects must be between 7 and 8.")
    user_mean = GRADE_POINTS[mean_grade]
    pathways = []
    try:
        from results import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, min_grade_requirement FROM career_categories")
        categories = cur.fetchall()
        for cat in categories:
            cat_id, cat_name, min_grade = cat
            cur.execute("SELECT field_name FROM career_fields WHERE category_id = %s", (cat_id,))
            fields = [row[0] for row in cur.fetchall()]
            pathways.append({
                "category": cat_name,
                "fields": fields,
                "description": f"Careers in {cat_name} requiring {user_mean} mean grade or higher",
                "recommended_actions": [
                    f"Research {cat_name.lower()} programs at TVET institutions",
                    f"Talk to career counselors about {cat_name.lower()} paths",
                    f"Join student clubs related to {cat_name.lower()}"
                ],
                "min_grade_requirement": min_grade
            })
        cur.close()
        conn.close()
    except Exception as e:
        pathways = []
    interest_suggestions = []
    if interests:
        interest_suggestions = [
            f"Since you're interested in {interests}, consider exploring:",
            f"• Entry-level positions in {interests} industry",
            f"• Internships or volunteer work in {interests} field",
            f"• Online courses in {interests} (Coursera, edX, ALX)",
            f"• Professional networking in {interests} sector"
        ]
    return {
        "career_pathways": pathways,
        "interest_suggestions": interest_suggestions if interests else ["Consider exploring different fields through internships, career counseling, or skills assessment programs"],
        "next_steps": [
            "Visit a career counselor for personalized guidance",
            "Take career assessment tests to discover your strengths",
            "Research job market trends in Kenya",
            "Connect with professionals in fields of interest"
        ],
        "grade_level": "High potential" if user_mean >= GRADE_POINTS["B+"] else "Moderate potential" if user_mean >= GRADE_POINTS["C"] else "Developing potential"
    }
