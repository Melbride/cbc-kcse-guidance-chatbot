# --- User Profile Context Helpers (moved from rag_query.py) ---
def build_profile_context(profile: dict) -> str:
	context_parts = []
	if profile.get('favorite_subject'):
		context_parts.append(f"User's favorite subject: {profile['favorite_subject']}")
	if profile.get('interests'):
		context_parts.append(f"User's interests: {profile['interests']}")
	if profile.get('strengths'):
		context_parts.append(f"User's strengths: {profile['strengths']}")
	if profile.get('career_interests'):
		context_parts.append(f"User's career interests: {profile['career_interests']}")
	if profile.get('learning_style'):
		context_parts.append(f"User's learning style: {profile['learning_style']}")
	if profile.get('mathematics_avg') and profile.get('mathematics_avg', 0) > 70:
		context_parts.append("User is strong in Mathematics")
	if profile.get('science_avg') and profile.get('science_avg', 0) > 70:
		context_parts.append("User is strong in Science")
	if profile.get('english_avg') and profile.get('english_avg', 0) > 70:
		context_parts.append("User is strong in English")
	competencies = []
	if profile.get('problem_solving_level') is not None and profile.get('problem_solving_level', 0) >= 4:
		competencies.append("Problem Solving")
	if profile.get('scientific_reasoning_level') is not None and profile.get('scientific_reasoning_level', 0) >= 4:
		competencies.append("Scientific Reasoning")
	if profile.get('collaboration_level') is not None and profile.get('collaboration_level', 0) >= 4:
		competencies.append("Collaboration")
	if profile.get('communication_level') is not None and profile.get('communication_level', 0) >= 4:
		competencies.append("Communication")
	if competencies:
		context_parts.append(f"Strong competencies: {', '.join(competencies)}")
	interests = []
	if profile.get('interest_stem') is not None and profile.get('interest_stem', 0) >= 3:
		interests.append("STEM")
	if profile.get('interest_arts') is not None and profile.get('interest_arts', 0) >= 3:
		interests.append("Arts")
	if profile.get('interest_social') is not None and profile.get('interest_social', 0) >= 3:
		interests.append("Social Sciences")
	if profile.get('interest_visual_arts') is not None and profile.get('interest_visual_arts', 0) >= 3:
		interests.append("Visual Arts")
	if profile.get('interest_music') is not None and profile.get('interest_music', 0) >= 3:
		interests.append("Music")
	if profile.get('interest_writing') is not None and profile.get('interest_writing', 0) >= 3:
		interests.append("Writing")
	if profile.get('interest_technology') is not None and profile.get('interest_technology', 0) >= 3:
		interests.append("Technology")
	if profile.get('interest_business') is not None and profile.get('interest_business', 0) >= 3:
		interests.append("Business")
	if profile.get('interest_agriculture') is not None and profile.get('interest_agriculture', 0) >= 3:
		interests.append("Agriculture")
	if profile.get('interest_healthcare') is not None and profile.get('interest_healthcare', 0) >= 3:
		interests.append("Healthcare")
	if profile.get('interest_media') is not None and profile.get('interest_media', 0) >= 3:
		interests.append("Media")
	if interests:
		context_parts.append(f"Your interests: {', '.join(interests)}")
	return "\n".join(context_parts) if context_parts else ""

def build_recent_history_context(get_db, user_id: str | None, limit: int = 3) -> str:
	if not user_id:
		return ""
	try:
		history = get_db().get_user_history(user_id, limit)
		if not history:
			return ""
		lines = []
		for item in reversed(history):
			question = str(item.get("question", "")).strip()
			answer = str(item.get("answer", "")).strip()
			if question:
				lines.append(f"User: {question}")
			if answer:
				lines.append(f"Assistant: {answer[:220]}")
		if not lines:
			return ""
		return "\n".join(lines)
	except Exception as history_error:
		print(f"Warning: failed to load recent history context: {history_error}")
		return ""
