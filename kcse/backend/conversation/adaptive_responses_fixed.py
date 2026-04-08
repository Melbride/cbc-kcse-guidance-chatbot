"""
Adaptive Response Generator for intelligent KCSE conversation system
Generates contextual, natural responses without hardcoding patterns
"""
from typing import Dict, List, Optional, Any
from .conversation_manager import ConversationManager, ConversationPhase, UserConfidence
import json

class AdaptiveResponseGenerator:
    """Generates intelligent, context-aware responses"""
    
    def __init__(self, conversation_manager: ConversationManager):
        self.conv_manager = conversation_manager
        
    def generate_response(self, user_id: str, message: str, user_profile: Dict = None) -> str:
        """Generate adaptive response based on conversation context"""
        
        # Update conversation state
        conv_state = self.conv_manager.update_conversation_state(user_id, message, user_profile)
        context = self.conv_manager.get_conversation_context(user_id)
        
        # Generate response based on intent and context
        intent = conv_state.last_intent
        
        if intent == "profile_update":
            return self._handle_profile_update(context)
        elif intent == "career_exploration":
            return self._handle_career_exploration(context)
        elif intent == "specific_interest":
            return self._handle_specific_interest(context)
        elif intent == "comparison":
            return self._handle_comparison(context)
        elif intent == "clarification":
            return self._handle_clarification(context)
        else:
            return self._handle_general_query(context)
    
    def _handle_profile_update(self, context: Dict) -> str:
        """Handle profile update requests with contextual awareness"""
        user_profile = context.get("user_profile", {})
        has_interests = bool(user_profile.get("interests", "").strip())
        has_goals = bool(user_profile.get("career_goals", "").strip())
        has_subjects = bool(user_profile.get("subjects", []))
        
        confidence = context.get("user_confidence", "medium")
        
        if has_interests and has_goals:
            return (
                f"I can see you already have interests and career goals in your profile. "
                f"Are you looking to update them or add more information? "
                f"You can edit your profile by clicking the profile button, or if you are happy with your current profile, "
                f"I can provide career guidance based on what you have shared."
            )
        elif has_interests or has_goals:
            missing = "career goals" if has_interests else "interests"
            return (
                f"I can see you have some profile information. "
                f"You can add your {missing} by clicking the profile button. "
                f"This will help me give you more personalized career guidance."
            )
        else:
            return (
                f"Great idea! Building your profile will help me provide personalized career guidance. "
                f"Click the profile button to add your interests, career goals, and academic information. "
                f"Once you have updated it, come back here and I will give you tailored recommendations!"
            )
    
    def _handle_career_exploration(self, context: Dict) -> str:
        """Handle career exploration with adaptive responses"""
        user_profile = context.get("user_profile", {})
        confidence = context.get("user_confidence", "medium")
        message_count = context.get("message_count", 1)
        
        has_interests = bool(user_profile.get("interests", "").strip())
        has_goals = bool(user_profile.get("career_goals", "").strip())
        has_subjects = bool(user_profile.get("subjects", []))
        
        # Adaptive response based on profile completeness and confidence
        if confidence == "uncertain" or message_count <= 2:
            return self._generate_uncertain_explorer_response(user_profile, context)
        elif has_interests and has_goals:
            return self._generate_complete_profile_guidance(user_profile, context)
        elif has_interests or has_goals:
            return self._generate_partial_profile_guidance(user_profile, context)
        else:
            return self._generate_new_user_guidance(user_profile, context)
    
    def _generate_uncertain_explorer_response(self, user_profile: Dict, context: Dict) -> str:
        """Generate response for uncertain users"""
        name = user_profile.get("name", "Student")
        subjects = user_profile.get("subjects", [])
        mean_grade = user_profile.get("mean_grade", "")
        
        response = (
            f"That is completely normal! Many students feel unsure about their next steps. "
            f"Let me help you explore this step by step.\n\n"
        )
        
        if subjects:
            response += f"I can see you have subjects like {', '.join(subjects[:3])}. "
            response += "That gives us a good starting point.\n\n"
        
        if mean_grade:
            response += f"With your mean grade of {mean_grade}, you have some solid options.\n\n"
        
        response += (
            f"To help me give you the best guidance, it would help to know:\n"
            f"• What subjects do you enjoy most?\n"
            f"• What kind of work interests you?\n"
            f"• Are there any fields you are curious about?\n\n"
            f"Do not worry about having all the answers right now - we can explore together!"
        )
        
        return response
    
    def _generate_complete_profile_guidance(self, user_profile: Dict, context: Dict) -> str:
        """Generate personalized guidance for complete profiles"""
        name = user_profile.get("name", "Student")
        interests = user_profile.get("interests", "")
        goals = user_profile.get("career_goals", "")
        mean_grade = user_profile.get("mean_grade", "")
        
        # Map interests to career fields
        career_suggestions = self._map_interests_to_careers(interests)
        
        response = (
            f"Perfect! I can see you are interested in {interests} and your goal is {goals}. "
            f"That is an excellent combination with your mean grade of {mean_grade}!\n\n"
            f"Based on your profile, here is what I recommend:\n\n"
        )
        
        if career_suggestions:
            response += f"**Career Paths to Consider:**\n"
            for i, career in enumerate(career_suggestions[:3], 1):
                response += f"• {career} - Aligns with your interests in {interests}\n"
        else:
            response += f"**Career Path to Consider:**\n"
            response += f"• {goals.title()} - Direct path to your stated goal\n"
            response += f"• Related fields in {interests} - Build on your natural interests\n"
        
        response += (
            f"\n**Next Steps:**\n"
            f"• Focus on subjects that support {goals}\n"
            f"• Look for internships or projects in {interests}\n"
            f"• Consider specific programmes I found that match your profile\n\n"
            f"Would you like me to show you specific programmes for any of these career paths?"
        )
        
        return response
    
    def _generate_partial_profile_guidance(self, user_profile: Dict, context: Dict) -> str:
        """Generate guidance for partial profiles"""
        name = user_profile.get("name", "Student")
        interests = user_profile.get("interests", "")
        goals = user_profile.get("career_goals", "")
        
        missing = "career goals" if interests else "interests"
        
        return (
            f"I can see you are interested in {interests or 'various fields'}"
            f" and {'have career goals' if goals else \"haven't specified career goals yet\"}. "
            f"To give you more targeted guidance, could you share your {missing}? "
            f"This will help me provide recommendations that align with both your interests and aspirations."
        )
    
    def _generate_new_user_guidance(self, user_profile: Dict, context: Dict) -> str:
        """Generate guidance for new users"""
        name = user_profile.get("name", "Student")
        subjects = user_profile.get("subjects", [])
        mean_grade = user_profile.get("mean_grade", "")
        
        response = (
            f"Hi {name}! I would be happy to help you explore career options. "
            f"I can see you have a mean grade of {mean_grade or 'not specified yet'}"
        )
        
        if subjects:
            subject_strengths = self._identify_strengths(subjects)
            if subject_strengths:
                response += f" and strengths in {', '.join(subject_strengths[:3])}"
        
        response += (
            ".\n\n"
            f"To give you the most personalized guidance, it would help to know:\n"
            f"• What subjects or activities do you enjoy?\n"
            f"• What kind of work do you see yourself doing in the future?\n"
            f"• Are there any specific fields you are curious about?\n\n"
            f"You can share this information by updating your profile, or just tell me what interests you right now!"
        )
        
        return response
    
    def _handle_specific_interest(self, context: Dict) -> str:
        """Handle specific interest inquiries"""
        topic = context.get("current_topic", "")
        user_profile = context.get("user_profile", {})
        
        response = f"Great choice! {topic.title()} is an excellent field with strong career prospects in Kenya.\n\n"
        
        # Add context about user's profile
        if user_profile.get("mean_grade"):
            response += f"With your mean grade, you should be eligible for several {topic} programmes.\n\n"
        
        response += (
            f"Let me search for {topic} options for you. "
            f"I will look at universities, TVET institutions, and diploma programmes that match your profile.\n\n"
            f"While I am searching, could you tell me:\n"
            f"• What specifically about {topic} interests you most?\n"
            f"• Are you looking for degree, diploma, or certificate level?\n"
            f"• Any preference for location or institution type?\n\n"
            f"Once I understand your preferences better, I can provide a more targeted comparison!"
        )
        
        return response
    
    def _handle_comparison(self, context: Dict) -> str:
        """Handle comparison requests"""
        previous_topics = context.get("previous_topics", [])
        current_topic = context.get("current_topic", "")
        
        if len(previous_topics) >= 1:
            response = f"Good question! Let me compare {previous_topics[-1]} and {current_topic} for you.\n\n"
        else:
            response = f"I would be happy to help you explore options in {current_topic}.\n\n"
        
        response += (
            f"To give you the most helpful comparison, it would help to know:\n"
            f"• What factors are most important to you? (career prospects, course duration, costs, etc.)\n"
            f"• Are you looking for practical vs theoretical focus?\n"
            f"• Any specific institutions you are considering?\n\n"
            f"Once I understand your preferences better, I can provide a more targeted comparison!"
        )
        
        return response
    
    def _handle_clarification(self, context: Dict) -> str:
        """Handle clarification requests"""
        confidence = context.get("user_confidence", "medium")
        
        if confidence == "uncertain":
            return (
                f"I am sorry if my previous response was confusing! Let me try a different approach.\n\n"
                f"Could you tell me in your own words what you are looking for? "
                f"Sometimes it helps to start with what subjects you enjoy most or what kind of work interests you."
            )
        else:
            return (
                f"Good question! Let me clarify that for you.\n\n"
                f"What specific aspect would you like me to explain more? "
                f"For example, are you asking about:\n"
                f"• Course requirements and entry criteria?\n"
                f"• Career prospects and job opportunities?\n"
                f"• Specific institutions or programmes?\n"
                f"• Application processes or deadlines?\n\n"
                f"The more specific you can be, the better I can help!"
            )
    
    def _handle_general_query(self, context: Dict) -> str:
        """Handle general queries"""
        return (
            f"I am here to help you explore career and course options!\n\n"
            f"You can ask me about:\n"
            f"• Specific subjects or fields (e.g., computer science, engineering, medicine)\n"
            f"• Career guidance based on your profile\n"
            f"• Course requirements and entry criteria\n"
            f"• Comparison between different options\n\n"
            f"What would you like to explore today?"
        )
    
    def _map_interests_to_careers(self, interests: str) -> List[str]:
        """Map interests to career fields"""
        interest_keywords = interests.lower().split()
        
        career_mapping = {
            'technology': ['Computer Science', 'Software Development', 'Data Science', 'Cybersecurity'],
            'business': ['Business Administration', 'Finance', 'Marketing', 'Entrepreneurship'],
            'medical': ['Medicine', 'Nursing', 'Pharmacy', 'Public Health'],
            'teaching': ['Education', 'Teaching', 'Educational Administration'],
            'engineering': ['Engineering', 'Technical Fields', 'Architecture'],
            'science': ['Research', 'Laboratory Science', 'Environmental Science']
        }
        
        suggested_careers = []
        for keyword, careers in career_mapping.items():
            if any(keyword in interest_keywords for keyword in [keyword] + careers):
                suggested_careers.extend(careers[:2])  # Avoid duplicates
        
        return list(set(suggested_careers))  # Remove duplicates
    
    def _identify_strengths(self, subjects: List) -> List[str]:
        """Identify subject strengths from grades"""
        # This is a simplified version - in real implementation, 
        # we would analyze actual grades from user profile
        strong_subjects = []
        
        for subject in subjects:
            if isinstance(subject, str) and ':' in subject:
                subject_name, grade = subject.split(':', 1)
                if grade and grade[0].strip().upper() in ['A', 'A-', 'B+', 'B']:
                    strong_subjects.append(subject_name.strip())
        
        return strong_subjects
