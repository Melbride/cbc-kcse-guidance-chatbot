-- Fix column sizes for mean_grade fields
ALTER TABLE artisan_programmes ALTER COLUMN mean_grade TYPE VARCHAR(50);
ALTER TABLE diploma_programs ALTER COLUMN mean_grade TYPE VARCHAR(50);
ALTER TABLE degree_cutoffs ALTER COLUMN minimum_mean_grade TYPE VARCHAR(50);
