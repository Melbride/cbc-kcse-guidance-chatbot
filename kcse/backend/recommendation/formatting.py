"""
Formatting utilities for semantic search results for chatbot display.
"""
def format_semantic_results(results):
	"""
	Takes a list of dicts with 'source' and 'data' from search.semantic_search.py and returns a user-friendly summary for the chatbot.
	"""
	formatted = []
	for item in results:
		label = item.get('source', 'Unknown')
		data = item.get('data', [])
		if label == 'Degree':
			# (prog_code, institution_name, programme_name, cutoff_2024, similarity)
			formatted.append(f"[Degree] {data[2]} at {data[1]} (Code: {data[0]}, Cutoff: {data[3]}, Similarity: {round(data[4], 3)})")
		elif label == 'Diploma':
			# (programme_code, institution_name, programme_name, mean_grade, subject_requirements, similarity)
			formatted.append(f"[Diploma] {data[2]} at {data[1]} (Code: {data[0]}, Mean Grade: {data[3]}, Requirements: {data[4]}, Similarity: {round(data[5], 3)})")
		elif label == 'Artisan':
			# (level, institution, programme, mean_grade, requirements, similarity)
			formatted.append(f"[Artisan] {data[2]} at {data[1]} (Level: {data[0]}, Mean Grade: {data[3]}, Requirements: {data[4]}, Similarity: {round(data[5], 3)})")
		elif label == 'SkillBuilding':
			# (company, programme_name, pathway, duration, cost, link, similarity)
			formatted.append(f"[Skill] {data[1]} by {data[0]} (Pathway: {data[2]}, Duration: {data[3]}, Cost: {data[4]}, Link: {data[5]}, Similarity: {round(data[6], 3)})")
		else:
			formatted.append(f"[{label}] {data}")
	return formatted
