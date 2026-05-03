#import required libraries for fastapi application
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from datetime import datetime
import os
from typing import Optional
import json
from pathlib import Path
from rag.rag_query import query_rag, QueryRequest
from database.db_manager import get_shared_db, close_shared_db
from models.request_models import (
    UserCreate,
    UserProfile,
    ChatCreate,
    CBCResults,
    SchoolPlacement,
    HistoryRequest
)
from recommendations.pathway_recommender import PathwayRecommender
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from analytics.analytics import AnalyticsManager

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

BASE_DIR = Path(__file__).resolve().parent
DOCUMENT_INDEX_PATH = BASE_DIR / "document_index.json"
UPLOADED_DOCUMENTS_DIR = BASE_DIR / "uploaded_documents"


#initialize fastapi application
app = FastAPI(title="CBC/KCSE Guidance Chatbot")

#Middleware must come BEFORE any route definitions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Preload embeddings and Pinecone at startup so first request is fast
@app.on_event("startup")
async def startup_event():
    print("Starting up CBC Guidance Chatbot", flush=True)
    from rag.document_search import get_embeddings, get_vectorstore
    from rag.rag_query import get_groq_client
    get_embeddings()
    get_vectorstore()
    get_groq_client()
    print("Ready. Server accepting requests.", flush=True)


@app.on_event("shutdown")
async def shutdown_event():
    close_shared_db()


#lazy initialization functions
def get_pathway_recommender():
    from rag.rag_query import get_pathway_recommender as _get
    return _get()

def get_analytics():
    from rag.rag_query import get_analytics as _get
    return _get()

def get_db():
    """Get database manager instance"""
    return get_shared_db()

def require_admin(request: Request):
    """Lightweight admin gate based on configured admin users."""
    admin_user_id = request.headers.get("X-Admin-User-Id")
    if not admin_user_id:
        raise HTTPException(status_code=401, detail="Admin access required")

    user = get_db().get_user(admin_user_id)
    if not user or user.get("active") is False:
        raise HTTPException(status_code=403, detail="Admin account is inactive or missing")

    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    return user


#health check endpoint
@app.get("/")  
def health_check():  
    return {"status": "healthy", "service": "CBC/KCSE Guidance Chatbot"}  


#Single /query/ endpoint 
@app.post("/query/")
def query_endpoint(req: QueryRequest):
    """
    Unified RAG endpoint.
    If user_id is provided, personalization is automatically applied inside query_rag.
    """
    #handles the main RAG query endpoint for chatbot responses
    print("=== /query/ endpoint hit ===", flush=True)
    #processes the query using RAG system
    result = query_rag(req)  
    print(f"[QUERY ENDPOINT] Question: {getattr(req, 'question', None)}", flush=True)
    print(f"[QUERY ENDPOINT] Answer: {result.get('answer', None)}", flush=True)
    return result


#Admin Documents Endpoints 
@app.get("/documents")
def list_documents(request: Request, page: int = 1, page_size: int = 20):
    #this code lists all uploaded documents with pagination for admin
    require_admin(request)  
    if not DOCUMENT_INDEX_PATH.exists():
        return {
            "documents": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0,
        }
    try:
        with open(DOCUMENT_INDEX_PATH, "r", encoding="utf-8") as f:
            docs = json.load(f)
        docs = list(reversed(docs))
        safe_page = max(page, 1)
        safe_page_size = max(page_size, 1)
        total = len(docs)
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        paged_docs = docs[start:end]
        total_pages = (total + safe_page_size - 1) // safe_page_size if total else 0
        return {
            "documents": paged_docs,
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": total_pages,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load documents: {str(e)}")

@app.post("/documents")
async def upload_document(request: Request, file: UploadFile = File(...)):
    """Upload a new document and add to index"""
    #Handles document upload and processing for the RAG system and admin accesss
    require_admin(request)  
    try:
        #Imports document loaders
        from rag.document_loader import load_pdf, load_docx  
        
        # Save uploaded file
        UPLOADED_DOCUMENTS_DIR.mkdir(exist_ok=True)  
        file_path = UPLOADED_DOCUMENTS_DIR / file.filename
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Extract text based on file type
        if file.filename.lower().endswith(".pdf"):
            text_content = load_pdf(file_path) 
            doc_type = "pdf"
        elif file.filename.lower().endswith(".docx"):
            text_content = load_docx(file_path)  
            doc_type = "docx"
        else:
            raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")
        
        if not text_content.strip():
            raise HTTPException(status_code=400, detail="Document is empty or unreadable")
        
        # Add to document index
        docs_metadata = []
        if DOCUMENT_INDEX_PATH.exists():
            with open(DOCUMENT_INDEX_PATH, "r", encoding="utf-8") as f:
                docs_metadata = json.load(f)
        
        doc_entry = {
            "title": file.filename.replace(f".{doc_type}", ""),
            "type": doc_type,
            "path": str(file_path),
            "uploaded": datetime.now().isoformat()
        }
        docs_metadata.append(doc_entry)
        
        with open(DOCUMENT_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(docs_metadata, f, indent=2)
        
        #Ingest to Pinecone
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            from langchain_pinecone import PineconeVectorStore
            from langchain.text_splitter import RecursiveCharacterTextSplitter
            from langchain.schema import Document
            
            #Set up the vector embedding and chunking system
            embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
            splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            #splits text into chunks
            chunks = splitter.split_text(text_content)  
            
            docs = [Document(page_content=chunk, metadata={"source": file.filename}) for chunk in chunks]
            
            #creates and stores vectors in Pinecone
            vectorstore = PineconeVectorStore.from_documents(
                documents=docs,
                embedding=embeddings,
                index_name=os.getenv("PINECONE_INDEX_NAME")
            )
        except Exception as e:
            print(f"Warning: Could not ingest to Pinecone: {e}")
        
        return {"success": True, "message": f"Document '{file.filename}' uploaded successfully", "document": doc_entry}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")

@app.delete("/documents/{doc_path:path}")
def delete_document(doc_path: str, request: Request):
    """Delete a document from index"""
    require_admin(request)
    try:
        from urllib.parse import unquote
        doc_path = unquote(doc_path)
        
        # Remove from index
        if not DOCUMENT_INDEX_PATH.exists():
            raise HTTPException(status_code=404, detail="Document not found")
        
        with open(DOCUMENT_INDEX_PATH, "r", encoding="utf-8") as f:
            docs_metadata = json.load(f)
        
        # Find and remove document
        original_count = len(docs_metadata)
        docs_metadata = [d for d in docs_metadata if d.get("path") != doc_path and d.get("title") != doc_path]
        
        if len(docs_metadata) == original_count:
            raise HTTPException(status_code=404, detail="Document not found")
        
        with open(DOCUMENT_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(docs_metadata, f, indent=2)
        
        # Delete physical file if it exists
        try:
            file_to_delete = Path(doc_path)
            if file_to_delete.exists():
                file_to_delete.unlink()
        except Exception as e:
            print(f"Warning: Could not delete file: {e}")
        
        return {"success": True, "message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


#Admin User Management Endpoints 
@app.put("/users/{user_id}/status")
def toggle_user_status(user_id: str, active: bool, request: Request):
    """Activate or deactivate a user"""
    #this code allows admins to activate or deactivate user accounts
    require_admin(request) 
    try:
        db = get_db()  
        with db.conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET active = %s, last_active = %s WHERE user_id = %s",
                (active, datetime.now() if active else None, user_id)
            )
            #saves the changes
            db.conn.commit()  
        return {"success": True, "message": f"User {'activated' if active else 'deactivated'} successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user status: {str(e)}")

@app.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request):
    """Delete a user and all associated data"""
    require_admin(request)
    try:
        db = get_db()
        with db.conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            db.conn.commit()
        return {"success": True, "message": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete user: {str(e)}")


#Admin Stats Endpoint 
@app.get("/admin/stats")
def admin_stats(request: Request):
    require_admin(request)
    stats = get_db().get_pathway_statistics()
    try:
        user_count = len(get_db().get_all_users())
    except Exception:
        user_count = 0
    stats["total_users"] = user_count
    return stats


#Privacy-First Analytics Endpoints
@app.get("/admin/analytics/query-stats")
def get_query_analytics(request: Request, days: int = 7):
    """Get aggregated query analytics - no PII exposed"""
    #provides analytics without exposing personal information
    require_admin(request)  
    return get_analytics().get_query_analytics(days)

@app.get("/admin/analytics/documents")
def get_document_analytics(request: Request):
    """Get document usage statistics"""
    require_admin(request)
    return {"documents": get_analytics().get_document_analytics()}

@app.get("/admin/analytics/feedback")
def get_feedback_analytics(request: Request, days: int = 7):
    """Get feedback trends by topic"""
    require_admin(request)
    return get_analytics().get_feedback_summary(days)

@app.get("/admin/analytics/knowledge-gaps")
def get_knowledge_gaps(request: Request, limit: int = 10):
    """Get top knowledge gaps - what the bot can't answer"""
    require_admin(request)
    return {"gaps": get_analytics().get_knowledge_gaps(limit)}

@app.get("/admin/analytics/system-health")
def get_system_health(request: Request, days: int = 7):
    """Get overall system health metrics"""
    require_admin(request)
    return get_analytics().get_system_health(days)

@app.get("/admin/audit-log")
def get_audit_log(request: Request, admin_id: Optional[str] = None, days: int = 30, limit: int = 100):
    """Get admin action audit log - tracks who accessed what and when"""
    require_admin(request)
    return {"audit_log": get_analytics().get_admin_audit_log(admin_id, days, limit)}


#Recent Questions Endpoint 
@app.get("/recent-questions")
def recent_questions(request: Request, limit: int = 20):
    require_admin(request)
    try:
        db = get_db()
        db._reset_failed_transaction()
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, question, answer, created_at
                FROM conversations
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            questions = []
            for row in rows:
                if isinstance(row, dict):
                    questions.append(row)
                else:
                    questions.append({
                        "user_id": row[0],
                        "question": row[1],
                        "answer": row[2],
                        "created_at": row[3].isoformat() if row[3] else None
                    })
            return {"questions": questions}
    except Exception as e:
        get_db().conn.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to load recent questions: {str(e)}")


#user management endpoints
@app.post("/users/")
def create_user(user: UserCreate):
    #creates a new user in the system
    return get_db().create_user(name=user.name, email=user.email)

@app.get("/users/")
def list_users(request: Request):
    require_admin(request)
    return {"users": get_db().get_all_users()}

@app.get("/users/email/{email}")
def get_user_by_email(email: str):
    """Check if user exists by email"""
    user = get_db().get_user_by_email(email)
    if user:
        return {"exists": True, "user": user}
    else:
        return {"exists": False, "user": None}

@app.get("/user-stage/{user_id}")
def get_user_stage(user_id: str):
    return {"stage": get_db().get_user_stage(user_id)}

@app.post("/user-profile/{user_id}")
def save_user_profile(user_id: str, profile: dict):
    """Save or update user profile from frontend"""
    #save user profile with stage mapping for CBC journey
    stage_mapping = {
        'before_exam': 'pre_exam',
        'after_exam': 'post_results',
        'after_placement': 'post_placement'
    }
    if 'journey_stage' in profile:
        profile['journey_stage'] = stage_mapping.get(profile['journey_stage'], profile['journey_stage'])
    return get_db().save_profile(user_id, profile)

@app.post("/cbc-profile")
def create_profile(profile: UserProfile, user_id: str):
    return get_db().save_profile(user_id, profile.model_dump())

@app.put("/update-profile/{user_id}")
def update_profile(user_id: str, profile: dict):
    """Update user profile with stage mapping"""
    stage_mapping = {
        'before_exam': 'pre_exam',
        'after_exam': 'post_results',
        'after_placement': 'post_placement'
    }
    if 'journey_stage' in profile:
        profile['journey_stage'] = stage_mapping.get(profile['journey_stage'], profile['journey_stage'])
    return get_db().update_profile(user_id, profile)

@app.get("/profiles/{user_id}")
def get_profile(user_id: str):
    profile_data = get_db().get_profile(user_id)
    if profile_data:
        return profile_data
    raise HTTPException(status_code=404, detail="Profile not found")

#cbc results and school placement endpoints
@app.post("/cbc-results/")
def save_cbc_results(user_id: str, cbc_results: CBCResults):
    return get_db().save_cbc_results(user_id, cbc_results.model_dump())

@app.post("/school-placement/")
def save_school_placement(user_id: str, placement: SchoolPlacement):
    return get_db().save_school_placement(user_id, placement.model_dump())

@app.post("/history/")
def get_history(req: HistoryRequest):
    history = get_db().get_user_history(req.user_id, req.limit)
    return {"history": history}

@app.post("/feedback")
def submit_feedback(payload: dict):
    """Capture anonymous thumbs up/down feedback for analytics."""
    question = (payload or {}).get("question", "")
    feedback_type = (payload or {}).get("feedback_type", "")

    if not question or not isinstance(question, str):
        raise HTTPException(status_code=400, detail="question is required")

    allowed_feedback = {"thumbs_up", "thumbs_down", "neutral"}
    if feedback_type not in allowed_feedback:
        raise HTTPException(status_code=400, detail="feedback_type must be thumbs_up, thumbs_down, or neutral")

    get_analytics().log_feedback(question, feedback_type)
    return {"success": True}

@app.get("/schools")
def get_schools(
    pathway: Optional[str] = None,
    county: Optional[str] = None,
    school_type: Optional[str] = None,
    gender: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 30,
):
    """
    List schools with optional pathway/county filters.
    Returns normalized field names expected by frontend.
    """
    try:
        result = get_db().get_schools_catalog(
            pathway=pathway,
            county=county,
            school_type=school_type,
            gender=gender,
            search_query=q,
            page=page,
            page_size=page_size,
        )

        normalized = []
        for school in (result.get("schools") or []):
            pathways = school.get("pathways_offered")
            if pathways is None:
                pathways = []
            elif isinstance(pathways, str):
                pathways = [pathways]

            normalized.append({
                "name": school.get("school_name") or school.get("name"),
                "county": school.get("county"),
                "sub_county": school.get("sub_county"),
                "type": school.get("school_type") or school.get("type"),
                "gender": school.get("gender"),
                "accommodation": school.get("accommodation"),
                "pathways_offered": pathways,
            })

        return {
            "schools": normalized,
            "count": len(normalized),
            "total": result.get("total", 0),
            "page": result.get("page", page),
            "page_size": result.get("page_size", page_size),
            "total_pages": result.get("total_pages", 0),
            "filters": {
                "pathway": pathway,
                "county": county,
                "school_type": school_type,
                "gender": gender,
                "q": q,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load schools: {str(e)}")

#pathway recommendation endpoint
@app.post("/pathway-recommendation/")
def get_pathway_recommendation(request: dict):
    #this code provides personalized pathway recommendations based on user profile
    user_id = request.get("user_id")
    if not user_id:
        return {"error": "user_id is required"}
        #code retrieves user profile
    profile_data = get_db().get_profile(user_id)  
    if not profile_data:
        return {"error": "Profile not found"}
    user_profile = UserProfile(**profile_data)
    #code generates recommendation
    recommendation = get_pathway_recommender().recommend(user_profile)  
    return {
        "user_id": user_id,
        "recommendation": recommendation,
        "timestamp": datetime.now().isoformat()
    }

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    for error in exc.errors():
        if error.get("loc") == ("body", "question") and error.get("type") == "string_too_short":
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Please enter a question so I can help you. (Your message was empty.)"
                },
            )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )

#run the application
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
