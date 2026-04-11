-- Create tables for KCSE guidance system
-- Execute this in your Supabase SQL editor

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

CREATE TABLE IF NOT EXISTS conversation_context (
    id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(255) NOT NULL,
    user_input TEXT,
    system_response TEXT,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Create index for better performance on conversation_id queries
CREATE INDEX IF NOT EXISTS idx_conversation_context_conversation_id ON conversation_context(conversation_id);
-- Create index for timestamp queries (sorting)
CREATE INDEX IF NOT EXISTS idx_conversation_context_timestamp ON conversation_context(timestamp DESC);
