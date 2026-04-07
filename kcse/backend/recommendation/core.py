"""
Core recommendation logic: evaluation, scoring, and generation of recommendations and alternatives.
"""
from results import GRADE_POINTS, fetch_courses, fetch_requirements, fetch_institutions, get_db_connection
import logging

logger = logging.getLogger("kcse_search")

def evaluate_course(user, course, requirements):
	"""
	Checks if a student qualifies for a course.
	Returns:
		(True/False, reasons[])
	"""
	user_mean = GRADE_POINTS[user["mean_grade"]]
	course_mean = GRADE_POINTS[course["min_mean_grade"]]
	reasons = []
	qualifies = True
	#Check mean grade
	if user_mean < course_mean:
		qualifies = False
		reasons.append(f"Mean grade too low (need {course['min_mean_grade']})")
	#Check each subject requirement
	for req in requirements:
		subject = req["subject"]
		required_points = GRADE_POINTS[req["min_grade"]]
		#If subject missing
		if subject not in user["subjects"]:
			qualifies = False
			reasons.append(f"Missing required subject: {subject}")
			continue
		user_points = GRADE_POINTS[user["subjects"][subject]]
		#If subject meets requirement
		if user_points >= required_points:
			reasons.append(f"{subject} OK")
		else:
			qualifies = False
			reasons.append(f"{subject} too low (need {req['min_grade']})")
	return qualifies, reasons

def calculate_score(user, requirements):
	"""
	Score shows how much the student exceeds requirements.
	Higher = better match
	"""
	score = 0
	for req in requirements:
		subject = req["subject"]
		if subject in user["subjects"]:
			user_points = GRADE_POINTS[user["subjects"][subject]]
			required_points = GRADE_POINTS[req["min_grade"]]
			score += (user_points - required_points)
	return score

def get_recommendations(user):
	recommendations = []
	#Connect to database
	with get_db_connection() as conn:
		with conn.cursor() as cur:
			#Get all courses
			courses = fetch_courses(cur)
			for course in courses:
				#Get requirements for each course
				requirements = fetch_requirements(cur, course["id"])
				#Check qualification
				qualifies, reasons = evaluate_course(user, course, requirements)
				# 4. Calculate score
				score = calculate_score(user, requirements)
				#Get institutions offering the course
				institutions = fetch_institutions(cur, course["id"])
				if qualifies:
					# Add explanation
					if score > 0:
						reasons.append("Exceeds requirements")
					else:
						reasons.append("Meets minimum requirements")
					recommendations.append({
						"course": course["name"],
						"level": course["level"],
						"score": score,
						"reasons": reasons,
						"institutions": institutions
					})
	# If no university recommendations, add alternative pathways
	if not recommendations:
		recommendations = get_alternative_pathways(user)
	#Sort best courses first
	recommendations.sort(key=lambda x: x["score"], reverse=True)
	return recommendations

def get_alternative_pathways(user):
	"""Generate alternative pathways for students who don't qualify for university"""
	alternatives = []
	user_mean = GRADE_POINTS[user["mean_grade"]]
	# Query database for TVET/Diploma programs
	try:
		with get_db_connection() as conn:
			with conn.cursor() as cur:
				# Get TVET and Diploma courses (lower requirements)
				cur.execute("""
					SELECT DISTINCT c.name, c.level, i.name as institution
					FROM courses c
					JOIN course_institutions ci ON c.id = ci.course_id
					JOIN institutions i ON ci.institution_id = i.id
					WHERE c.level IN ('Diploma', 'Certificate')
					AND c.min_mean_grade <= %s
					ORDER BY c.min_mean_grade ASC
					LIMIT 10
				""", (user_mean,))
				tvet_courses = cur.fetchall()
				# Add TVET options
				for course in tvet_courses:
					alternatives.append({
						"course": course[0],  # course name
						"level": course[1],  # course level
						"score": 0,
						"reasons": ["Meets minimum requirements"],
						"institutions": [course[2]],  # institution name
						"pathway_type": "TVET"
					})
				# Add digital skills platforms from database
				try:
					cur.execute("""
						SELECT DISTINCT 'Digital Skills Program' as course_name, 
						   'Certificate' as level,
						   array_agg(i.name) as institutions
						FROM institutions i
						WHERE i.name ILIKE ANY (ARRAY['%Digital%', '%ALX%', '%Moringa%', '%Coursera%'])
						LIMIT 5
					""")
					digital_platforms = cur.fetchall()
					for platform in digital_platforms:
						alternatives.append({
							"course": platform[0],
							"level": "Certificate",
							"score": 0,
							"reasons": ["No minimum grade requirements", "Self-paced learning"],
							"institutions": platform[1] if platform[1] else ["Various Online Platforms"],
							"pathway_type": "Digital Skills"
						})
				except Exception as e:
					logger.error(f"Error fetching digital platforms: {e}")
				# Add entrepreneurship programs from database
				try:
					cur.execute("""
						SELECT DISTINCT 'Entrepreneurship Training' as course_name,
						   'Certificate' as level,
						   array_agg(i.name) as institutions
						FROM institutions i
						WHERE i.name ILIKE ANY (ARRAY['%Youth%', '%Enterprise%', '%Business%'])
						LIMIT 5
					""")
					entrepreneurship_programs = cur.fetchall()
					for program in entrepreneurship_programs:
						alternatives.append({
							"course": program[0],
							"level": "Certificate",
							"score": 0,
							"reasons": ["Open to all KCSE grades", "Business startup focus"],
							"institutions": program[1] if program[1] else ["Various Business Support Organizations"],
							"pathway_type": "Entrepreneurship"
						})
				except Exception as e:
					logger.error(f"Error fetching entrepreneurship programs: {e}")
	except Exception as e:
		logger.error(f"Error in alternative pathways: {e}")
		# No fallback: return empty list if DB fails
		alternatives = []
	return alternatives
