-- Users table
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    mean_grade VARCHAR(10),
    interests TEXT,
    career_goals TEXT,
    extra_data JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Feedback table
CREATE TABLE IF NOT EXISTS recommendation_feedback (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255),
    recommendation_id VARCHAR(255),
    feedback_text TEXT,
    rating INTEGER,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Announcements table
CREATE TABLE IF NOT EXISTS announcements (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

-- Support content table
CREATE TABLE IF NOT EXISTS support_content (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    content TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Question logs table
CREATE TABLE IF NOT EXISTS question_logs (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    question TEXT NOT NULL,
    response TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    topic VARCHAR(100),
    reviewed BOOLEAN DEFAULT false,
    review_note TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Conversation context table
CREATE TABLE IF NOT EXISTS conversation_context (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    user_input TEXT,
    system_response TEXT,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Career/education tables (from original schema)
CREATE TABLE IF NOT EXISTS degree_cutoffs (
    id SERIAL PRIMARY KEY,
    prog_code VARCHAR(50),
    institution_name TEXT,
    programme_name TEXT,
    cutoff_2018 VARCHAR(20),
    cutoff_2019 VARCHAR(20),
    cutoff_2020 VARCHAR(20),
    cutoff_2021 VARCHAR(20),
    cutoff_2022 VARCHAR(20),
    cutoff_2023 VARCHAR(20),
    cutoff_2024 VARCHAR(20),
    qualification_type VARCHAR(50),
    minimum_mean_grade VARCHAR(10),
    subject_requirements TEXT,
    cluster_or_points_info TEXT,
    course_description TEXT,
    career_paths TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS diploma_programs (
    id SERIAL PRIMARY KEY,
    programme_code VARCHAR(50),
    institution_name TEXT,
    programme_name TEXT,
    mean_grade VARCHAR(10),
    subject_requirements TEXT
);

CREATE TABLE IF NOT EXISTS artisan_programmes (
    id SERIAL PRIMARY KEY,
    level VARCHAR(50),
    institution TEXT,
    programme TEXT,
    mean_grade VARCHAR(10),
    requirements TEXT
);

CREATE TABLE IF NOT EXISTS skillbuilding (
    id SERIAL PRIMARY KEY,
    company TEXT,
    programme_name TEXT,
    pathway TEXT,
    duration TEXT,
    cost TEXT,
    link TEXT
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);
CREATE INDEX IF NOT EXISTS idx_user_profiles_created_at ON user_profiles(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_user_id ON recommendation_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_announcements_created_at ON announcements(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_support_content_status ON support_content(status);
CREATE INDEX IF NOT EXISTS idx_question_logs_conversation_id ON question_logs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_question_logs_status ON question_logs(status);
CREATE INDEX IF NOT EXISTS idx_conversation_context_conversation_id ON conversation_context(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_context_timestamp ON conversation_context(timestamp DESC);
