"""
Conversation Manager for intelligent, context-aware KCSE guidance system
Handles conversation state, user intent tracking, and adaptive responses
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import json
import time

class ConversationPhase(Enum):
    EXPLORATION = "exploration"
    CLARIFICATION = "clarification"
    DECISION = "decision"
    COMPARISON = "comparison"
    PROFILE_UPDATE = "profile_update"
    FOLLOW_UP = "follow_up"

class UserConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"

@dataclass
class ConversationState:
    """Tracks the current conversation state and context"""
    user_id: str
    current_topic: Optional[str] = None
    previous_topics: List[str] = None
    conversation_phase: ConversationPhase = ConversationPhase.EXPLORATION
    user_confidence: UserConfidence = UserConfidence.HIGH
    last_intent: Optional[str] = None
    message_count: int = 0
    last_activity: float = time.time()
    context_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.previous_topics is None:
            self.previous_topics = []

class ConversationManager:
    """Manages conversation state and intelligent response generation"""
    
    def __init__(self):
        self.active_conversations: Dict[str, ConversationState] = {}
        self.intent_patterns = self._initialize_intent_patterns()
        
    def _initialize_intent_patterns(self) -> Dict[str, List[str]]:
        """Initialize semantic intent patterns without hardcoding every possibility"""
        return {
            "career_exploration": [
                "what can i study", "help me choose", "career options", "guidance", "advice",
                "what should i study", "courses for my grades", "confused about future",
                "don't know what to choose", "need career guidance", "explore options",
                "what subjects should i focus on", "i'm confused", "unsure about career",
                "help me decide", "career path", "what career", "future options"
            ],
            "specific_interest": [
                "computer science", "engineering", "medicine", "nursing", "business",
                "teaching", "accounting", "law", "architecture", "technology",
                "interested in", "want to study", "tell me about", "information about"
            ],
            "profile_update": [
                "update profile", "change interests", "add goals", "edit profile",
                "modify profile", "let me update", "want to update", "going to update",
                "add my interests", "change my career goals", "how do i update",
                "want to add", "need to change", "profile button"
            ],
            "comparison": [
                "which is better", "compare these", "difference between", "versus",
                "or should i", "help me decide", "pros and cons", "vs", "better option",
                "compare engineering and business", "engineering vs business"
            ],
            "clarification": [
                "what do you mean", "explain that", "tell me more", "clarify",
                "didn't understand", "confusing", "what are you saying",
                "explain better", "don't understand", "what does that mean"
            ],
            "profile_inquiry": [
                "my profile", "my interests", "my goals", "my grades",
                "based on my profile", "according to my profile", "my information"
            ],
            "requirements_inquiry": [
                "requirements", "what are the requirements", "entry requirements",
                "what do i need", "qualifications", "eligibility", "cut off"
            ],
            "career_prospects": [
                "career prospects", "job opportunities", "future", "salary",
                "is it a good career", "job market", "employment", "career growth"
            ]
        }
    
    def get_or_create_conversation(self, user_id: str) -> ConversationState:
        """Get existing conversation or create new one"""
        if user_id not in self.active_conversations:
            self.active_conversations[user_id] = ConversationState(user_id=user_id)
        return self.active_conversations[user_id]
    
    def detect_intent(self, message: str, conversation_state: ConversationState) -> str:
        """Detect user intent using semantic matching with enhanced context awareness"""
        message_lower = message.lower().strip()
        
        # Calculate intent scores
        intent_scores = {}
        for intent, patterns in self.intent_patterns.items():
            score = sum(1 for pattern in patterns if pattern in message_lower)
            if score > 0:
                intent_scores[intent] = score
        
        # Enhanced context-aware decisions
        if conversation_state.current_topic and any(word in message_lower for word in ["different", "instead", "rather"]):
            intent_scores["topic_change"] = 3
            
        if any(word in message_lower for word in ["actually", "but", "however", "instead", "rather"]):
            if conversation_state.previous_topics or conversation_state.current_topic:
                intent_scores["mind_change"] = 3
        
        # Check for follow-up patterns
        if any(word in message_lower for word in ["also", "what about", "how about", "additionally"]):
            intent_scores["follow_up"] = 2
            
        # Check for comparison patterns
        if any(word in message_lower for word in ["compare", "versus", "vs", "better", "between"]):
            intent_scores["comparison"] = 3
        
        # Return highest scoring intent
        if intent_scores:
            return max(intent_scores, key=intent_scores.get)
        return "career_exploration"  # default
    
    def analyze_user_confidence(self, message: str) -> UserConfidence:
        """Analyze user confidence level from message"""
        message_lower = message.lower()
        
        uncertainty_indicators = [
            "confused", "don't know", "unsure", "not certain", "maybe",
            "perhaps", "probably", "might", "think", "wondering"
        ]
        
        high_confidence_indicators = [
            "definitely", "certain", "sure", "want to", "decided on",
            "committed to", "focused on"
        ]
        
        if any(indicator in message_lower for indicator in uncertainty_indicators):
            return UserConfidence.UNCERTAIN
        elif any(indicator in message_lower for indicator in high_confidence_indicators):
            return UserConfidence.HIGH
        else:
            return UserConfidence.MEDIUM
    
    def update_conversation_state(self, user_id: str, message: str, user_profile: Dict = None) -> ConversationState:
        """Update conversation state based on new message"""
        conv_state = self.get_or_create_conversation(user_id)
        
        # Detect intent
        intent = self.detect_intent(message, conv_state)
        
        # Analyze confidence
        confidence = self.analyze_user_confidence(message)
        
        # Update state
        conv_state.last_intent = intent
        conv_state.user_confidence = confidence
        conv_state.message_count += 1
        conv_state.last_activity = time.time()
        
        # Enhanced topic handling
        new_topic = self._extract_topic(message)
        
        # Handle topic changes and mind changes
        if intent in ["topic_change", "mind_change"]:
            if new_topic and new_topic != conv_state.current_topic:
                if conv_state.current_topic:
                    conv_state.previous_topics.append(conv_state.current_topic)
                conv_state.current_topic = new_topic
                conv_state.conversation_phase = ConversationPhase.CLARIFICATION
        elif intent == "specific_interest":
            if new_topic and new_topic != conv_state.current_topic:
                if conv_state.current_topic:
                    conv_state.previous_topics.append(conv_state.current_topic)
                conv_state.current_topic = new_topic
        elif intent == "comparison":
            conv_state.conversation_phase = ConversationPhase.COMPARISON
        elif intent == "profile_update":
            conv_state.conversation_phase = ConversationPhase.PROFILE_UPDATE
        elif intent == "follow_up":
            # Keep current phase but acknowledge follow-up
            pass
        
        # Store user profile if provided
        if user_profile:
            conv_state.context_data = user_profile
            
        return conv_state
    
    def _extract_topic(self, message: str) -> Optional[str]:
        """Extract topic from message"""
        topics = [
            "computer science", "engineering", "medicine", "nursing", "business",
            "teaching", "accounting", "law", "architecture", "technology",
            "mathematics", "physics", "chemistry", "biology"
        ]
        
        message_lower = message.lower()
        for topic in topics:
            if topic in message_lower:
                return topic
        return None
    
    def get_conversation_context(self, user_id: str) -> Dict[str, Any]:
        """Get rich context for response generation"""
        conv_state = self.get_or_create_conversation(user_id)
        
        return {
            "current_topic": conv_state.current_topic,
            "previous_topics": conv_state.previous_topics[-3:],  # Last 3 topics
            "conversation_phase": conv_state.conversation_phase.value,
            "user_confidence": conv_state.user_confidence.value,
            "message_count": conv_state.message_count,
            "last_intent": conv_state.last_intent,
            "user_profile": conv_state.context_data or {},
            "time_in_conversation": time.time() - conv_state.last_activity
        }
    
    def should_switch_phase(self, user_id: str, new_phase: ConversationPhase) -> bool:
        """Determine if conversation should switch phases"""
        conv_state = self.get_or_create_conversation(user_id)
        
        # Phase switching logic
        if new_phase == ConversationPhase.PROFILE_UPDATE:
            return conv_state.last_intent in ["profile_update", "profile_inquiry"]
        
        if new_phase == ConversationPhase.CLARIFICATION:
            return conv_state.user_confidence in [UserConfidence.LOW, UserConfidence.UNCERTAIN]
        
        return True  # Allow switching by default
