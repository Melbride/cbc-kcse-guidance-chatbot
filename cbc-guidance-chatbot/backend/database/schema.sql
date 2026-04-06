-- CREATE DATABASE cbc_chatbot;

-- \c cbc_chatbot;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255),
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'student',
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_active TIMESTAMP DEFAULT NOW()
);
-- user profile table
CREATE TABLE user_profiles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) REFERENCES users(user_id) ON DELETE CASCADE,
    -- Basic learner profile fields
    favorite_subject VARCHAR(100),
    interests TEXT,
    strengths TEXT,
    career_interests TEXT,
    learning_style VARCHAR(50),
    explore_goals TEXT,
    placed_school VARCHAR(255),
    placed_pathway VARCHAR(100),

    -- CBC Grades
    mathematics_avg FLOAT,
    science_avg FLOAT,
    english_avg FLOAT,
    kiswahili_avg FLOAT,
    social_studies_avg FLOAT,
    business_studies_avg FLOAT,
    -- Competencies (1-5 scale: 1=Low, 5=High)
    problem_solving_level INT CHECK (problem_solving_level BETWEEN 1 AND 5),
    scientific_reasoning_level INT CHECK (scientific_reasoning_level BETWEEN 1 AND 5),
    collaboration_level INT CHECK (collaboration_level BETWEEN 1 AND 5),
    communication_level INT CHECK (communication_level BETWEEN 1 AND 5),
    
    -- Interests (1-5 scale)
    interest_stem INT CHECK (interest_stem BETWEEN 1 AND 5),
    interest_arts INT CHECK (interest_arts BETWEEN 1 AND 5),
    interest_social INT CHECK (interest_social BETWEEN 1 AND 5),
    interest_creative INT CHECK (interest_creative BETWEEN 1 AND 5),
    interest_sports INT CHECK (interest_sports BETWEEN 1 AND 5),
    interest_dance INT CHECK (interest_dance BETWEEN 1 AND 5),

    -- Career goals (JSON array)
    career_goals JSONB,
    
    -- Overall CBC performance category
    overall_performance VARCHAR(10) CHECK (overall_performance IN ('EE', 'ME', 'AE', 'BE')),

    -- Journey stage
    journey_stage VARCHAR(50),
    
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(user_id)
);

-- Conversation history table
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) REFERENCES users(user_id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    mode VARCHAR(20) CHECK (mode IN ('general', 'personalized')),
    question_embedding VECTOR(384),
    created_at TIMESTAMP DEFAULT NOW(),
    source_folder VARCHAR(100),
    confidence_score FLOAT,
    validated BOOLEAN DEFAULT FALSE,
    from_cache BOOLEAN DEFAULT FALSE,
    recommended_pathway VARCHAR(50),
    match_score FLOAT
);

-- Cached Q&A table
CREATE TABLE cached_qa (
    id SERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    question_embedding VECTOR(384),
    answer TEXT NOT NULL,
    mode VARCHAR(20) DEFAULT 'general',
    -- Metadata
    source_folder VARCHAR(100),
    confidence_score FLOAT,
    validated BOOLEAN DEFAULT TRUE,
    -- Usage stats
    times_requested INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    last_requested_at TIMESTAMP DEFAULT NOW()
);

-- Pathway recommendations history
CREATE TABLE recommendations (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) REFERENCES users(user_id) ON DELETE CASCADE,
    pathway VARCHAR(50),
    match_score FLOAT,
    reasoning TEXT,
    subjects JSONB,  
    careers JSONB,   
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_user_id ON conversations(user_id);
CREATE INDEX idx_created_at ON conversations(created_at);
CREATE INDEX idx_question_embedding ON cached_qa USING ivfflat (question_embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_conversation_embedding ON conversations USING ivfflat (question_embedding vector_cosine_ops) WITH (lists = 100);

-- CBC results and school placement
CREATE TABLE IF NOT EXISTS cbc_subject_results (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) REFERENCES users(user_id),
    subject_code VARCHAR(10),
    subject_name VARCHAR(100),
    performance_level VARCHAR(10),  
    points INT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cbc_pathway_scores (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) REFERENCES users(user_id) UNIQUE,
    stem_score FLOAT,
    social_sciences_score FLOAT,
    arts_sports_score FLOAT,
    knec_recommended_pathway VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS school_placements (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) REFERENCES users(user_id) UNIQUE,
    school_name VARCHAR(200),
    pathway VARCHAR(50),
    reporting_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kenya_senior_schools_pathways (
    id SERIAL PRIMARY KEY,
    region VARCHAR(100),
    county VARCHAR(100),
    sub_county VARCHAR(100),
    knec_code VARCHAR(50),
    school_name VARCHAR(255) NOT NULL,
    cluster VARCHAR(100),
    type VARCHAR(50),
    accomodation VARCHAR(50),
    gender VARCHAR(50),
    pathway_type VARCHAR(50),
    pathways_offered VARCHAR(255),
    combo_pathway VARCHAR(255),
    combo_track VARCHAR(255),
    subject_1 VARCHAR(100),
    subject_2 VARCHAR(100),
    subject_3 VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Update user_profiles for CBC results
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS cbc_results JSONB;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS school_placement JSONB;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS journey_stage VARCHAR(20) CHECK (journey_stage IN ('pre_exam', 'post_results', 'post_placement'));

-- Privacy-First Analytics Tables (No PII stored)
CREATE TABLE IF NOT EXISTS query_analytics (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL,
    topic_category VARCHAR(100),
    confidence_score FLOAT,
    retrieved_documents INT,
    response_time_ms INT,
    was_successful BOOLEAN DEFAULT TRUE,
    fallback_triggered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_usage (
    id SERIAL PRIMARY KEY,
    document_name VARCHAR(255),
    document_hash VARCHAR(64) UNIQUE,
    retrieval_count INT DEFAULT 1,
    avg_confidence_score FLOAT,
    last_used_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    id SERIAL PRIMARY KEY,
    admin_id VARCHAR(100),
    action VARCHAR(100),
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    reason TEXT,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_analytics (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64),
    topic_category VARCHAR(100),
    feedback_type VARCHAR(20) CHECK (feedback_type IN ('thumbs_up', 'thumbs_down', 'neutral')),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_gap_log (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) UNIQUE,
    topic_category VARCHAR(100),
    fallback_reason VARCHAR(100),
    suggested_document_topic VARCHAR(255),
    count INT DEFAULT 1,
    last_occurred_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for analytics performance
CREATE INDEX idx_query_analytics_created ON query_analytics(created_at);
CREATE INDEX idx_query_analytics_topic ON query_analytics(topic_category);
CREATE INDEX idx_document_usage_name ON document_usage(document_name);
CREATE INDEX idx_feedback_analytics_topic ON feedback_analytics(topic_category);
CREATE INDEX idx_knowledge_gap_topic ON knowledge_gap_log(topic_category);
CREATE INDEX idx_admin_audit_created ON admin_audit_log(created_at);

