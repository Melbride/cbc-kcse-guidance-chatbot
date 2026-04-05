from typing import List, Dict, Optional
from models.request_models import UserProfile

class PathwayRecommender:
    def __init__(self):
        self.score_weights = {
            'STEM': {'math': 0.3, 'science': 0.3, 'english': 0.2, 'kiswahili': 0.1, 'social_studies': 0.1},
            'Social Sciences': {'math': 0.2, 'science': 0.1, 'english': 0.3, 'kiswahili': 0.3, 'social_studies': 0.1},
            'Arts & Sports': {'math': 0.1, 'science': 0.1, 'english': 0.2, 'kiswahili': 0.2, 'social_studies': 0.4}
        }
    
    def recommend(self, user_profile: UserProfile) -> Dict:
        """Generate pathway recommendation based on user profile"""

        # Prefer persisted official CBC pathway score snapshot when available.
        if any([
            user_profile.stem_score is not None,
            user_profile.social_sciences_score is not None,
            user_profile.arts_sports_score is not None,
        ]):
            return self._recommend_from_cbc_score_snapshot(user_profile)
        
        # Check if user has any meaningful data
        has_academic_data = any([
            user_profile.mathematics_avg,
            user_profile.science_avg,
            user_profile.english_avg,
            user_profile.kiswahili_avg,
            user_profile.social_studies_avg,
            user_profile.business_studies_avg
        ])
        
        has_interest_data = any([
            user_profile.interest_stem,
            user_profile.interest_arts,
            user_profile.interest_social,
            user_profile.interest_creative,
            user_profile.interest_sports,
            user_profile.interest_dance,
            user_profile.interest_visual_arts,
            user_profile.interest_music,
            user_profile.interest_writing,
            user_profile.interest_technology,
            user_profile.interest_business,
            user_profile.interest_agriculture,
            user_profile.interest_healthcare,
            user_profile.interest_media
        ])
        
        # If user has CBC results, use those
        if hasattr(user_profile, 'cbc_results') and user_profile.cbc_results:
            return self._recommend_from_cbc_results(user_profile.cbc_results)
        
        # If no data available, return neutral recommendation
        elif not has_academic_data and not has_interest_data:
            return self._recommend_neutral()
        
        # Otherwise use estimates
        else:
            return self._recommend_from_estimates(user_profile)

    def _recommend_from_cbc_score_snapshot(self, user_profile: UserProfile) -> Dict:
        """Recommend from persisted official CBC pathway scores in user profile."""
        stem_score = user_profile.stem_score or 0
        social_score = user_profile.social_sciences_score or 0
        arts_score = user_profile.arts_sports_score or 0

        scores = {
            "STEM": stem_score,
            "Social Sciences": social_score,
            "Arts & Sports": arts_score
        }
        best_pathway = max(scores, key=scores.get)
        best_score = scores[best_pathway]

        score_diff = best_score - min(scores.values())
        if score_diff > 5:
            confidence = "HIGH"
        elif score_diff > 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        reasoning = f"Based on official CBC pathway scores, {best_pathway} has the highest score ({best_score})."
        if user_profile.knec_recommended_pathway:
            reasoning += f" KNEC recommendation: {user_profile.knec_recommended_pathway}."

        return {
            "pathway": best_pathway,
            "confidence": f"{confidence} (Official CBC Results)",
            "scores": scores,
            "reasoning": reasoning,
            "basis": "official_results"
        }
    
    def _recommend_from_cbc_results(self, cbc_results) -> Dict:
        """Recommend based on official CBC results"""
        stem_score = cbc_results.stem_pathway_score or 0
        social_score = cbc_results.social_sciences_pathway_score or 0
        arts_score = cbc_results.arts_sports_pathway_score or 0
        scores = {
            "STEM": stem_score,
            "Social Sciences": social_score,
            "Arts & Sports": arts_score
        }
        best_pathway = max(scores, key=scores.get)
        best_score = scores[best_pathway]
        
        #Calculate confidence
        score_diff = best_score - min(scores.values())
        if score_diff > 5:
            confidence = "HIGH"
        elif score_diff > 2:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        return {
            "pathway": best_pathway,
            "confidence": f"{confidence} (Official CBC Results)",
            "scores": scores,
            "reasoning": f"Based on official CBC results, {best_pathway} has the highest score ({best_score})",
            "basis": "official_results"
        }
    def _recommend_from_estimates(self, user_profile: UserProfile) -> Dict:
        """Recommend based on self-reported estimates"""
        
        #calculate pathway scores from subject averages, interests, and competencies (only use available data)
        stem_factors = []
        if user_profile.mathematics_avg:
            stem_factors.append(user_profile.mathematics_avg * 0.25)
        if user_profile.science_avg:
            stem_factors.append(user_profile.science_avg * 0.25)
        if user_profile.interest_stem:
            stem_factors.append(user_profile.interest_stem * 0.15)
        if user_profile.interest_technology:
            stem_factors.append(user_profile.interest_technology * 0.1)
        if user_profile.interest_agriculture:
            stem_factors.append(user_profile.interest_agriculture * 0.1)
        if user_profile.problem_solving_level:
            stem_factors.append(user_profile.problem_solving_level * 0.1)
        if user_profile.scientific_reasoning_level:
            stem_factors.append(user_profile.scientific_reasoning_level * 0.05)
        stem_score = sum(stem_factors) if stem_factors else 0
        
        social_factors = []
        if user_profile.english_avg:
            social_factors.append(user_profile.english_avg * 0.2)
        if user_profile.kiswahili_avg:
            social_factors.append(user_profile.kiswahili_avg * 0.2)
        if user_profile.social_studies_avg:
            social_factors.append(user_profile.social_studies_avg * 0.15)
        if user_profile.interest_social:
            social_factors.append(user_profile.interest_social * 0.1)
        if user_profile.interest_business:
            social_factors.append(user_profile.interest_business * 0.1)
        if user_profile.interest_media:
            social_factors.append(user_profile.interest_media * 0.05)
        if user_profile.collaboration_level:
            social_factors.append(user_profile.collaboration_level * 0.1)
        if user_profile.communication_level:
            social_factors.append(user_profile.communication_level * 0.1)
        social_score = sum(social_factors) if social_factors else 0
        
        arts_factors = []
        if user_profile.interest_arts:
            arts_factors.append(user_profile.interest_arts * 0.2)
        if user_profile.interest_creative:
            arts_factors.append(user_profile.interest_creative * 0.15)
        if user_profile.interest_sports:
            arts_factors.append(user_profile.interest_sports * 0.15)
        if user_profile.interest_dance:
            arts_factors.append(user_profile.interest_dance * 0.1)
        if user_profile.interest_visual_arts:
            arts_factors.append(user_profile.interest_visual_arts * 0.1)
        if user_profile.interest_music:
            arts_factors.append(user_profile.interest_music * 0.1)
        if user_profile.interest_writing:
            arts_factors.append(user_profile.interest_writing * 0.1)
        if user_profile.communication_level:
            arts_factors.append(user_profile.communication_level * 0.1)
        arts_score = sum(arts_factors) if arts_factors else 0
        
        scores = {
            "STEM": stem_score,
            "Social Sciences": social_score,
            "Arts & Sports": arts_score
        } 
        
        # Only recommend if we have meaningful data
        if all(score == 0 for score in scores.values()):
            return self._recommend_neutral()
        
        best_pathway = max(scores, key=scores.get)
        best_score = scores[best_pathway]
        return {
            "pathway": best_pathway,
            "confidence": "MEDIUM (Based on Estimates)",
            "scores": scores,
            "reasoning": f"Based on your available data, {best_pathway} appears to be your strongest area",
            "basis": "self_reported"
        }
    
    def _recommend_neutral(self) -> Dict:
        """Return neutral recommendation when no data is available"""
        return {
            "pathway": "Undetermined",
            "confidence": "LOW (No Data Available)",
            "scores": {
                "STEM": 0.0,
                "Social Sciences": 0.0,
                "Arts & Sports": 0.0
            },
            "reasoning": "No academic or interest data available. Please complete your profile to get personalized pathway recommendations.",
            "basis": "no_data"
        }
