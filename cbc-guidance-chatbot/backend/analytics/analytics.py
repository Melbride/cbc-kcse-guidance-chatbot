import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from database.db_manager import DatabaseManager
import json

class AnalyticsManager:
    """Privacy-first analytics for RAG system - no PII stored"""
    
    def __init__(self):
        self.db = DatabaseManager()
    
    def hash_query(self, query: str) -> str:
        """Hash query for anonymization"""
        return hashlib.sha256(query.encode()).hexdigest()
    
    def categorize_topic(self, query: str) -> str:
        """Categorize query into topics without storing full text"""
        query_lower = query.lower()
        
        topics = {
            'pathways': ['pathway', 'stem', 'social sciences', 'arts', 'career path'],
            'schools': ['school', 'admission', 'placement', 'county', 'boarding'],
            'subjects': ['subject', 'mathematics', 'physics', 'chemistry', 'biology', 'english'],
            'grades': ['grade', 'marks', 'score', 'performance', 'cbc'],
            'requirements': ['requirement', 'qualify', 'eligible', 'cutoff'],
            'general': []
        }
        
        for topic, keywords in topics.items():
            if any(keyword in query_lower for keyword in keywords):
                return topic
        return 'general'
    
    def log_query(self, query: str, confidence_score: float, retrieved_docs: int, 
                  response_time_ms: int, was_successful: bool = True, 
                  fallback_triggered: bool = False) -> None:
        """Log query analytics without storing actual question"""
        try:
            query_hash = self.hash_query(query)
            topic = self.categorize_topic(query)
            
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO query_analytics 
                    (query_hash, topic_category, confidence_score, retrieved_documents, 
                     response_time_ms, was_successful, fallback_triggered)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (query_hash, topic, confidence_score, retrieved_docs, 
                      response_time_ms, was_successful, fallback_triggered))
                self.db.conn.commit()
        except Exception as e:
            self.db.conn.rollback()  # ADD THIS
            print(f"Error logging query analytics: {e}")
    
    def log_document_usage(self, document_name: str, confidence_score: float) -> None:
        """Track which documents are being used"""
        try:
            doc_hash = hashlib.sha256(document_name.encode()).hexdigest()
            
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO document_usage 
                    (document_name, document_hash, retrieval_count, avg_confidence_score, last_used_at)
                    VALUES (%s, %s, 1, %s, NOW())
                    ON CONFLICT (document_hash) DO UPDATE SET
                        retrieval_count = document_usage.retrieval_count + 1,
                        avg_confidence_score = (document_usage.avg_confidence_score + EXCLUDED.avg_confidence_score) / 2,
                        last_used_at = NOW()
                """, (document_name, doc_hash, confidence_score))
                self.db.conn.commit()
        except Exception as e:
            self.db.conn.rollback()  # ADD THIS
            print(f"Error logging document usage: {e}")
    
    def log_feedback(self, query: str, feedback_type: str) -> None:
        """Log user feedback (thumbs up/down) without storing query"""
        try:
            query_hash = self.hash_query(query)
            topic = self.categorize_topic(query)
            
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO feedback_analytics 
                    (query_hash, topic_category, feedback_type)
                    VALUES (%s, %s, %s)
                """, (query_hash, topic, feedback_type))
                self.db.conn.commit()
        except Exception as e:
            self.db.conn.rollback()  # ADD THIS
            print(f"Error logging feedback: {e}")
    
    def log_knowledge_gap(self, query: str, fallback_reason: str, 
                         suggested_topic: Optional[str] = None) -> None:
        """Log when bot can't answer - identifies knowledge gaps"""
        try:
            query_hash = self.hash_query(query)
            topic = self.categorize_topic(query)
            
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO knowledge_gap_log 
                    (query_hash, topic_category, fallback_reason, suggested_document_topic, count)
                    VALUES (%s, %s, %s, %s, 1)
                    ON CONFLICT (query_hash) DO UPDATE SET
                        count = knowledge_gap_log.count + 1,
                        last_occurred_at = NOW()
                """, (query_hash, topic, fallback_reason, suggested_topic))
                self.db.conn.commit()
        except Exception as e:
            self.db.conn.rollback()  # ADD THIS
            print(f"Error logging knowledge gap: {e}")
    
    def log_admin_action(self, admin_id: str, action: str, resource_type: str, 
                        resource_id: str, reason: Optional[str] = None, 
                        ip_address: Optional[str] = None) -> None:
        """Audit log for admin actions - ensures accountability"""
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO admin_audit_log 
                    (admin_id, action, resource_type, resource_id, reason, ip_address)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (admin_id, action, resource_type, resource_id, reason, ip_address))
                self.db.conn.commit()
        except Exception as e:
            print(f"Error logging admin action: {e}")
    
    def get_query_analytics(self, days: int = 7) -> Dict:
        """Get aggregated query analytics for dashboard"""
        self.db._reset_failed_transaction()
        try:
            with self.db.conn.cursor() as cur:
                # Total queries by topic
                cur.execute("""
                    SELECT topic_category, COUNT(*) as count, 
                           COALESCE(AVG(confidence_score), 0) as avg_confidence,
                           CASE WHEN COUNT(*) > 0 THEN SUM(CASE WHEN was_successful THEN 1 ELSE 0 END)::float / COUNT(*) ELSE 0 END as success_rate
                    FROM query_analytics
                    WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                    GROUP BY topic_category
                    ORDER BY count DESC
                """, (days,))
                topic_stats = cur.fetchall()
                
                # Fallback triggers
                cur.execute("""
                    SELECT COUNT(*) as fallback_count,
                           CASE WHEN (SELECT COUNT(*) FROM query_analytics WHERE created_at >= NOW() - (%s * INTERVAL '1 day')) > 0 
                                THEN COUNT(*)::float / (SELECT COUNT(*) FROM query_analytics WHERE created_at >= NOW() - (%s * INTERVAL '1 day'))
                                ELSE 0 END as fallback_rate
                    FROM query_analytics
                    WHERE fallback_triggered = TRUE
                    AND created_at >= NOW() - (%s * INTERVAL '1 day')
                """, (days, days, days))
                fallback_stats = cur.fetchone()
                
                # Response time stats
                cur.execute("""
                    SELECT COALESCE(AVG(response_time_ms), 0) as avg_response_time,
                           COALESCE(MAX(response_time_ms), 0) as max_response_time,
                           COALESCE(MIN(response_time_ms), 0) as min_response_time
                    FROM query_analytics
                    WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                """, (days,))
                response_stats = cur.fetchone()
                
                return {
                    'topic_stats': [{'topic_category': row[0], 'count': row[1], 'avg_confidence': float(row[2]), 'success_rate': float(row[3])} for row in topic_stats] if topic_stats else [],
                    'fallback_stats': {'fallback_count': fallback_stats[0] or 0, 'fallback_rate': float(fallback_stats[1] or 0)} if fallback_stats else {},
                    'response_stats': {'avg_response_time': float(response_stats[0] or 0), 'max_response_time': float(response_stats[1] or 0), 'min_response_time': float(response_stats[2] or 0)} if response_stats else {},
                    'period_days': days
                }
        except Exception as e:
            self.db.conn.rollback()
            print(f"Error getting query analytics: {e}")
            return {}
    
    def get_document_analytics(self) -> List[Dict]:
        """Get document usage statistics"""
        self.db._reset_failed_transaction()
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    SELECT document_name, retrieval_count, COALESCE(avg_confidence_score, 0) as avg_confidence_score, last_used_at
                    FROM document_usage
                    ORDER BY retrieval_count DESC
                    LIMIT 20
                """)
                results = cur.fetchall()
                return [{'document_name': row[0], 'retrieval_count': row[1], 'avg_confidence_score': float(row[2]), 'last_used_at': row[3]} for row in results] if results else []
        except Exception as e:
            self.db.conn.rollback()
            print(f"Error getting document analytics: {e}")
            return []
    
    def get_feedback_summary(self, days: int = 7) -> Dict:
        """Get feedback trends by topic"""
        self.db._reset_failed_transaction()
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    SELECT topic_category, feedback_type, COUNT(*) as count
                    FROM feedback_analytics
                    WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                    GROUP BY topic_category, feedback_type
                    ORDER BY topic_category, count DESC
                """, (days,))
                results = cur.fetchall()
                
                feedback_by_topic = {}
                for row in results:
                    topic = row[0]
                    if topic not in feedback_by_topic:
                        feedback_by_topic[topic] = {}
                    feedback_by_topic[topic][row[1]] = row[2]
                
                return feedback_by_topic
        except Exception as e:
            self.db.conn.rollback()
            print(f"Error getting feedback summary: {e}")
            return {}
    
    def get_knowledge_gaps(self, limit: int = 10) -> List[Dict]:
        """Get top knowledge gaps - what the bot can't answer"""
        self.db._reset_failed_transaction()
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    SELECT topic_category, fallback_reason, count, suggested_document_topic, last_occurred_at
                    FROM knowledge_gap_log
                    ORDER BY count DESC, last_occurred_at DESC
                    LIMIT %s
                """, (limit,))
                results = cur.fetchall()
                return [{'topic_category': row[0], 'fallback_reason': row[1], 'count': row[2], 'suggested_document_topic': row[3], 'last_occurred_at': row[4]} for row in results] if results else []
        except Exception as e:
            self.db.conn.rollback()
            print(f"Error getting knowledge gaps: {e}")
            return []
    
    def get_admin_audit_log(self, admin_id: Optional[str] = None, 
                           days: int = 30, limit: int = 100) -> List[Dict]:
        """Get admin action audit log"""
        self.db._reset_failed_transaction()
        try:
            with self.db.conn.cursor() as cur:
                if admin_id:
                    cur.execute("""
                        SELECT admin_id, action, resource_type, resource_id, reason, 
                               ip_address, created_at
                        FROM admin_audit_log
                        WHERE admin_id = %s AND created_at >= NOW() - (%s * INTERVAL '1 day')
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (admin_id, days, limit))
                else:
                    cur.execute("""
                        SELECT admin_id, action, resource_type, resource_id, reason, 
                               ip_address, created_at
                        FROM admin_audit_log
                        WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (days, limit))
                
                results = cur.fetchall()
                return [dict(row) for row in results] if results else []
        except Exception as e:
            self.db.conn.rollback()
            print(f"Error getting audit log: {e}")
            return []
    
    def get_system_health(self, days: int = 7) -> Dict:
        """Get overall system health metrics"""
        self.db._reset_failed_transaction()
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total_queries,
                        COUNT(DISTINCT DATE(created_at)) as active_days,
                        COALESCE(AVG(confidence_score), 0) as avg_confidence,
                        CASE WHEN COUNT(*) > 0 THEN SUM(CASE WHEN was_successful THEN 1 ELSE 0 END)::float / COUNT(*) ELSE 0 END as success_rate,
                        SUM(CASE WHEN fallback_triggered THEN 1 ELSE 0 END) as fallback_count
                    FROM query_analytics
                    WHERE created_at >= NOW() - (%s * INTERVAL '1 day')
                """, (days,))
                
                result = cur.fetchone()
                if result:
                    return {
                        'total_queries': result[0] or 0,
                        'active_days': result[1] or 0,
                        'avg_confidence': float(result[2] or 0),
                        'success_rate': float(result[3] or 0),
                        'fallback_count': result[4] or 0
                    }
                return {}
        except Exception as e:
            self.db.conn.rollback()
            print(f"Error getting system health: {e}")
            return {}
