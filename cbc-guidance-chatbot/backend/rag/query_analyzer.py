"""
query_analyzer.py
-----------------
Analyses user questions and routes them to the correct handler:
  - Pinecone  → curriculum content, career guidance, explanations
  - Database  → school listings, subject combinations
  - Personalized guidance → profile-aware responses

Nothing domain-specific is hardcoded here:
  Keyword routing lists       → config/query_keywords.json
  Subject → pathway weights   → config/pathway_subject_priority.json
  County names                → PostgreSQL schools.county (loaded at startup)
  Subject names               → PostgreSQL schools.subject_1/2/3 (loaded at startup)
"""

import re
import json
import os
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

_groq_client = None
gemini_model_available = True

def get_groq_client():
    global _groq_client
    if _groq_client is not None:
        return _groq_client
    try:
        from groq import Groq
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        return _groq_client
    except Exception as e:
        print(f"Groq client init failed: {e}")
        return None

#Load configs and DB-backed data
from config_loader import (
    QUERY_KEYWORDS          as _KW,
    PATHWAY_SUBJECT_PRIORITY,
    load_counties_from_db,
    load_subjects_from_db,
)

# Lazy-loaded from PostgreSQL 
_COUNTIES: list[str] = []
_ALL_SUBJECTS: list[str] = []

def _ensure_db_data_loaded():
    global _COUNTIES, _ALL_SUBJECTS
    if not _COUNTIES:
        try:
            _COUNTIES = load_counties_from_db()
        except Exception as e:
            print(f"Warning: Could not load counties: {e}")
            _COUNTIES = []
    if not _ALL_SUBJECTS:
        try:
            _ALL_SUBJECTS = load_subjects_from_db()
        except Exception as e:
            print(f"Warning: Could not load subjects: {e}")
            _ALL_SUBJECTS = []

# Build subject → pathway lookup from pathway_subject_priority.json.
# If a subject appears in multiple pathways, highest weight wins.
_SUBJECT_TO_PATHWAY: dict[str, str] = {}
for _pathway, _subjects in PATHWAY_SUBJECT_PRIORITY.items():
    for _subject, _weight in _subjects.items():
        existing = _SUBJECT_TO_PATHWAY.get(_subject)
        if existing is None:
            _SUBJECT_TO_PATHWAY[_subject] = _pathway
        elif _weight > PATHWAY_SUBJECT_PRIORITY[existing].get(_subject, 0):
            _SUBJECT_TO_PATHWAY[_subject] = _pathway

# All STEM subjects from pathway_subject_priority.json for pathway tie-breaking
_STEM_SUBJECTS: set[str] = set(PATHWAY_SUBJECT_PRIORITY.get("stem", {}).keys())

# In-memory continuation context keyed by user_id
_last_pathway_context: Dict[str, Dict[str, Optional[str]]] = {}


#Module helpers 

def _any_kw(text: str, key: str) -> bool:
    return any(kw in text for kw in _KW[key])

def _pinecone_result(query_type: str) -> dict:
    return {"query_type": query_type, "source": "pinecone"}

def _db_result(query_type: str, **kwargs) -> dict:
    return {"query_type": query_type, "source": "database", **kwargs}


#Main class

class QueryAnalyzer:

    def analyze_query(self, question: str, user_id: str = None) -> Dict:
        """
        Analyse a user question and return structured routing metadata.

        Flow:
          1. Rule-based routing (fast, no LLM cost)
          2. Gemini LLM for anything rules don't cover
          3. Simple fallback if LLM is unavailable
          4. Tag as personalized or general
        """
        _ensure_db_data_loaded()  
        requested_count = self._extract_requested_count(question)

        analysis = self._analyze_school_query(question, user_id)
        if analysis:
            analysis.setdefault("reformulated_query", question)
            if requested_count:
                analysis["requested_count"] = requested_count
            if user_id and analysis.get("query_type") == "subjects_by_pathway":
                _last_pathway_context[user_id] = {
                    "pathway":      analysis.get("pathway"),
                    "county":       analysis.get("county"),
                    "track_filter": analysis.get("track_filter"),
                }
        else:
            analysis = self._classify_with_llm(question) or self._classify_by_rules(question)
            analysis.setdefault("reformulated_query", question)

        analysis["type"] = (
            "personalized" if user_id and self._is_personalized_question(question)
            else "general"
        )
        return analysis

    #Rule-based router 

    def _analyze_school_query(self, question: str, user_id: str = None) -> Optional[Dict]:
        q = question.lower()
        has_school_kw = _any_kw(q, "school_listing_keywords")

        result = self._get_pinecone_route(q, has_school_kw, user_id)
        if result:
            return result

        if has_school_kw or self._is_interest_based_school_search(q) or self._is_school_name_search(q):
            return self._get_database_route(question, q)

        return None

    def _get_pinecone_route(self, q: str, has_school_kw: bool, user_id: str = None) -> Optional[Dict]:
        """Return a Pinecone result for curriculum/guidance questions, or None."""

        if _any_kw(q, "career_keywords") and not has_school_kw:
            return _pinecone_result("career_explanation")

        if _any_kw(q, "subject_count_keywords") and not has_school_kw:
            return _pinecone_result("subject_count_query")

        if (_any_kw(q, "cbc_level_tokens") or _any_kw(q, "cbc_level_phrases")) and not has_school_kw:
            return _pinecone_result("cbc_performance_explanation")

        if _any_kw(q, "personalized_keywords") and not has_school_kw:
            return _pinecone_result("personalized_guidance")

        if _any_kw(q, "continuation_keywords") and not has_school_kw:
            result = self._handle_continuation(q, user_id)
            if result:
                return result

        if _any_kw(q, "combination_keywords") and not has_school_kw:
            pathway = self._extract_pathway(q)
            county  = self._extract_county(q)
            if pathway:
                return _db_result("subjects_by_pathway", pathway=pathway, county=county)
            return _pinecone_result("subject_combination_query")

        if (_any_kw(q, "pathway_explanation_triggers")
                and _any_kw(q, "pathway_explanation_targets")
                and not has_school_kw):
            return _pinecone_result("pathway_explanation")

        if (_any_kw(q, "subject_explanation_triggers")
                and not has_school_kw
                and self._extract_subjects(q)):
            return _pinecone_result("subject_explanation")

        if (_any_kw(q, "general_subject_keywords")
                and not self._extract_pathway(q)
                and not has_school_kw):
            return _pinecone_result("general_subject_query")

        return None

    def _get_database_route(self, question: str, q: str) -> Dict:
        """
        Build a DB result for school-listing questions.
        Priority: explicit subjects > pathway > county > name search.
        Counties and subjects come from PostgreSQL — not hardcoded.
        School name searches pass the raw term to the DB.
        """
        subjects = self._extract_subjects(question)
        county   = self._extract_county(q)
        pathway  = self._extract_pathway(q)
        gender   = self._extract_gender(q)

        if subjects:
            return _db_result("schools_by_subjects", subjects=subjects, county=county, gender=gender)
        if pathway:
            return _db_result("schools_by_pathway", pathway=pathway, county=county, gender=gender)
        if county:
            return _db_result("schools_by_county", county=county, gender=gender)

        return _db_result("school_search", search_term=self._extract_search_term(question))

    def _handle_continuation(self, q: str, user_id: str = None) -> Optional[Dict]:
        """Handle 'show more' follow-ups for subject combinations."""
        pathway = self._extract_pathway(q)
        county  = self._extract_county(q)

        # Infer STEM if a STEM track keyword is mentioned without "STEM" explicitly
        if not pathway and _any_kw(q, "stem_track_keywords"):
            pathway = "stem"

        # Reuse last known context for this user
        if not pathway and user_id and user_id in _last_pathway_context:
            ctx     = _last_pathway_context[user_id]
            pathway = ctx.get("pathway")
            county  = county or ctx.get("county")

        if not pathway:
            return None

        track_filter = next(
            (kw for kw in _KW["stem_track_keywords"] if kw in q), None
        )
        if not track_filter and user_id and user_id in _last_pathway_context:
            track_filter = _last_pathway_context[user_id].get("track_filter")

        return _db_result(
            "subjects_by_pathway",
            pathway=pathway,
            county=county,
            expansion_mode="more",
            track_filter=track_filter,
        )

    #Extraction helpers 

    def _extract_pathway(self, question: str) -> Optional[str]:
        """
        Extract pathway from question.
        Exact CBC pathway names checked first (these are fixed Ministry terminology).
        Context keywords come from query_keywords.json — not hardcoded here.
        """
        q = question.lower()

        if "social sciences" in q:
            return "social sciences"
        if "arts & sports" in q or "arts and sports" in q:
            return "arts & sports"
        if "stem" in q:
            return "stem"

        for pathway, keywords in _KW["pathway_context_keywords"].items():
            if any(kw in q for kw in keywords):
                return pathway

        return None

    def _extract_county(self, question: str) -> Optional[str]:
        """
        Extract county from question.
        County list loaded from PostgreSQL at startup — not hardcoded.
        """
        q = question.lower()
        for county in _COUNTIES:
            if county in q:
                return county.title()
        return None

    def _extract_gender(self, question: str) -> Optional[str]:
        """
        Extract gender from question.
        Looks for 'girls', 'boys', 'mixed', 'co-ed', etc.
        """
        q = question.lower()
        if 'girls' in q:
            return 'girls'
        elif 'boys' in q:
            return 'boys'
        elif 'mixed' in q or 'co-ed' in q or 'coed' in q:
            return 'mixed'
        return None

    def _extract_subjects(self, question: str) -> list[str]:
        """
        Extract subjects from question.
        Subject list loaded from PostgreSQL at startup — not hardcoded.
        Sorted longest-first so multi-word subjects match before shorter ones.
        """
        q = question.lower()
        return [s.title() for s in _ALL_SUBJECTS if s in q]

    def _map_subjects_to_pathway(self, subjects: list[str]) -> Optional[str]:
        """
        Map subjects to their most likely pathway.
        Uses _SUBJECT_TO_PATHWAY derived from pathway_subject_priority.json.
        STEM subjects favour STEM when there is a mixed result.
        Subject set comes from JSON config — not hardcoded here.
        """
        if not subjects:
            return None

        counts: dict[str, int] = {}
        for subject in subjects:
            pathway = _SUBJECT_TO_PATHWAY.get(subject.lower())
            if pathway:
                counts[pathway] = counts.get(pathway, 0) + 1

        if not counts:
            return None

        # Favour STEM if any subject belongs to STEM (from pathway_subject_priority.json)
        if any(s.lower() in _STEM_SUBJECTS for s in subjects) and "stem" in counts:
            return "stem"

        return max(counts, key=counts.get)

    def _extract_requested_count(self, question: str) -> Optional[int]:
        """Extract a specific school count from the question."""
        patterns = [
            r'(\d+)\s+schools?',
            r'schools?\s+(\d+)',
            r'give me\s+(\d+)\s+schools?',
            r'show me\s+(\d+)\s+schools?',
            r'(?:need|want)\s+(\d+)\s+schools?',
        ]
        for pattern in patterns:
            match = re.search(pattern, question.lower())
            if match:
                try:
                    count = int(match.group(1))
                    if 1 <= count <= 50:
                        return count
                except ValueError:
                    continue
        return None

    def _extract_search_term(self, question: str) -> str:
        """
        Extract a generic search term when no other signals found.
        Raw term passed to get_db().search_schools() — PostgreSQL handles matching.
        """
        q = question.lower()
        remove_words = ["school", "schools", "in", "that", "are", "offering", "with"]

        if "find" in q:
            term = q.split("find", 1)[1].strip()
        elif "school" in q:
            term = q.split("school", 1)[1].strip()
        else:
            return q.strip()

        for word in remove_words:
            term = term.replace(word, "").strip()
        return term

    #Secondary routing helpers 

    def _is_interest_based_school_search(self, q: str) -> bool:
        return (
            _any_kw(q, "interest_school_keywords")
            and any(kw in q for kw in ["schools", "programs"])
        )

    def _is_school_name_search(self, q: str) -> bool:
        if _any_kw(q, "school_name_keywords"):
            return True
        # Pattern: "find [name] school" or "where is X school"
        if "school" in q and any(kw in q for kw in ["find", "search", "locate", "where is"]):
            return True
        return False

    #LLM classification 

    def _classify_with_llm(self, question: str) -> Dict:
        """Classify query using Groq for questions that didn't match any rule."""
        global gemini_model_available
        if not gemini_model_available:
            return {}

        try:
            client = get_groq_client()
            if not client:
                return {}

            prompt = f"""Classify this user question about CBC education in Kenya:
"{question}"

Return JSON with these fields:
- query_type: one of ["school_search", "pathway_query", "subject_query", "general_info", "career_query"]
- pathway: extract if mentioned (STEM, Social Sciences, Arts & Sports)
- county: extract if mentioned
- subjects: list any subjects mentioned
- confidence: high/medium/low

Return only valid JSON, no extra text."""

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1,
            )
            result = response.choices[0].message.content.strip()
            return json.loads(result)
        except Exception as e:
            error_text = str(e).lower()
            if "quota" in error_text or "429" in error_text:
                gemini_model_available = False
            print(f"LLM classification error: {e}")
            return {}

    def _classify_by_rules(self, question: str) -> Dict:
        """Fallback when LLM is unavailable."""
        if self._is_personalized_question(question):
            return {"query_type": "personalized_guidance", "source": "pinecone", "confidence": "medium"}
        return {"query_type": "general_info", "confidence": "medium"}

    def _is_personalized_question(self, question: str) -> bool:
        return _any_kw(question.lower(), "personal_indicators")