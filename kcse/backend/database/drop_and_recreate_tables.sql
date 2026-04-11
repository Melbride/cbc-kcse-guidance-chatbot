-- Drop existing tables (in reverse order of dependencies)
DROP TABLE IF EXISTS skillbuilding CASCADE;
DROP TABLE IF EXISTS artisan_programmes CASCADE;
DROP TABLE IF EXISTS diploma_programs CASCADE;
DROP TABLE IF EXISTS degree_cutoffs CASCADE;

-- Recreate tables with correct schema
CREATE TABLE degree_cutoffs (
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

CREATE TABLE diploma_programs (
    id SERIAL PRIMARY KEY,
    programme_code VARCHAR(50),
    institution_name TEXT,
    programme_name TEXT,
    mean_grade VARCHAR(10),
    subject_requirements TEXT
);

CREATE TABLE artisan_programmes (
    id SERIAL PRIMARY KEY,
    level VARCHAR(50),
    institution TEXT,
    programme TEXT,
    mean_grade VARCHAR(10),
    requirements TEXT
);

CREATE TABLE skillbuilding (
    id SERIAL PRIMARY KEY,
    company TEXT,
    programme_name TEXT,
    pathway TEXT,
    duration TEXT,
    cost TEXT,
    link TEXT
);
