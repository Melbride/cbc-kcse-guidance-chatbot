#import required libraries for data validation
from pydantic import BaseModel, Field
from typing import Optional, List

class SubjectResult(BaseModel):
    """Individual subject result from CBC Grade 9"""
    subject_code: str  
    subject_name: str  
    performance_level: str  
    points: int  

class CBCResults(BaseModel):
    """Official CBC Grade 9 Results - Phase 1 (what students get first)"""
    
    subjects: List[SubjectResult] = []
    
    stem_pathway_score: Optional[float] = None
    social_sciences_pathway_score: Optional[float] = None
    arts_sports_pathway_score: Optional[float] = None
    
    recommended_pathway: Optional[str] = None  

class SchoolPlacement(BaseModel):
    """School placement - Phase 2 (comes 1 week after results)"""
    
    school_name: str  
    pathway: str  
    reporting_date: Optional[str] = None

class UserCreate(BaseModel):
    """User signup - minimal info needed"""
    name: str
    email: Optional[str] = None
    role: str = "learner"  
    user_type: str = "cbc"  

class UserProfile(BaseModel):
    """Complete learner profile - supports ALL stages"""

    # Official CBC pathway score snapshot (stored in cbc_pathway_scores)
    stem_score: Optional[float] = None
    social_sciences_score: Optional[float] = None
    arts_sports_score: Optional[float] = None
    knec_recommended_pathway: Optional[str] = None
    
    #academic averages
    mathematics_avg: Optional[float] = None
    science_avg: Optional[float] = None
    english_avg: Optional[float] = None
    kiswahili_avg: Optional[float] = None
    social_studies_avg: Optional[float] = None
    business_studies_avg: Optional[float] = None
    
    #official results and placement
    cbc_results: Optional[CBCResults] = None
    school_placement: Optional[SchoolPlacement] = None
    
    #competency levels (1-5 scale)
    problem_solving_level: Optional[int] = 3
    scientific_reasoning_level: Optional[int] = 3
    collaboration_level: Optional[int] = 3
    communication_level: Optional[int] = 3
    
    #interest ratings (1-5 scale)
    interest_stem: Optional[int] = 3
    interest_arts: Optional[int] = 3
    interest_social: Optional[int] = 3
    interest_creative: Optional[int] = 3
    interest_sports: Optional[int] = 3
    interest_dance: Optional[int] = 3
    interest_visual_arts: Optional[int] = 3  # drawing, painting, design
    interest_music: Optional[int] = 3           # music, singing, instruments
    interest_writing: Optional[int] = 3          # creative writing, literature
    interest_technology: Optional[int] = 3        # digital skills, coding
    interest_business: Optional[int] = 3           # entrepreneurship
    interest_agriculture: Optional[int] = 3       # farming, environment
    interest_healthcare: Optional[int] = 3         # medicine, nursing
    interest_media: Optional[int] = 3             # journalism, communications
    
    career_goals: List[str] = []
    journey_stage: Optional[str] = None

class QueryRequest(BaseModel):
    """question with optional user context and stage"""
    question: str = Field(..., min_length=1, max_length=500)
    user_id: Optional[str] = None
    stage: Optional[str] = None

class PersonalizedQueryRequest(BaseModel):
    """question + profile = personalized recommendation"""
    question: str = Field(..., min_length=1, max_length=500)
    user_id: Optional[str] = None
    user_profile: Optional[UserProfile] = None  

class ProfileUpdateRequest(BaseModel):
    """update existing profile"""
    user_id: str
    profile: UserProfile

class ChatCreate(BaseModel):
    """chat history model"""
    user_id: str
    message: str
    response: str
    sources: Optional[str] = None

class HistoryRequest(BaseModel):
    """get past conversations"""
    user_id: str
    limit: int = Field(default=10, ge=1, le=50)
