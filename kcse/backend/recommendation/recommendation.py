# Refactored: Import split modules for recommendations (absolute imports)
from backend.recommendation.conversation_context import update_conversation_context, get_conversation_context
from backend.recommendation.llm_utils import rerank_with_llm, explain_recommendation
from backend.recommendation.formatting import format_semantic_results
from backend.recommendation.core import evaluate_course, calculate_score, get_recommendations, get_alternative_pathways
