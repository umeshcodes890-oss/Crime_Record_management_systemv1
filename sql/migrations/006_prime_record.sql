-- =====================================================================
-- Migration 006 - The prime record of a case
--
-- A case normally has one suspect the investigation runs through, one
-- victim the story is told from and one exhibit that carries the charge.
-- Until now that was held in the memory of whoever was reading the
-- register, so the mark goes onto the record itself.
--
-- The column is only a flag. Two rules are what make it mean something:
--
--   * it moves when a person moves it, through mark_prime/clear_prime in
--     app/db/persons.py and app/db/evidence.py. It is never derived from
--     a sort order, an arrest or a date, and an ordinary profile write
--     cannot set it;
--   * a case has at most one of each kind, and the database enforces it.
--     prime_case_marker holds the case id of a primed row and NULL
--     otherwise, so a unique index over it allows any number of
--     unprimed rows and exactly one primed row per case. This is the
--     same idiom witness_statements.active_marker uses for "one current
--     version of a statement".
--
-- The marker is VIRTUAL where migration 002 made active_marker STORED:
-- MySQL 8.0 refuses to add a stored generated column that reads a column
-- carrying a foreign key - and case_id always carries one - with error
-- 1215, "Cannot add foreign key constraint". A virtual one is accepted,
-- and InnoDB can still put the unique index on it.
--
-- Nothing is dropped and no row is rewritten: every existing record
-- takes DEFAULT FALSE, which is what it already meant. The suspect
-- screen reads through v_suspect_summary, so the view is replaced to
-- carry the new column - a rebuilt view still reads the same rows.
-- =====================================================================

-- suspects : the main suspect of a case
CALL sp_add_column('suspects', 'is_prime', 'BOOLEAN NOT NULL DEFAULT FALSE');
CALL sp_add_column('suspects', 'prime_case_marker',
    'INT AS (CASE WHEN is_prime = 1 THEN case_id ELSE NULL END) VIRTUAL');
CALL sp_add_index('suspects', 'uq_suspect_prime',
    'UNIQUE KEY uq_suspect_prime (prime_case_marker)');

-- victims : the victim the case is told from
CALL sp_add_column('victims', 'is_prime', 'BOOLEAN NOT NULL DEFAULT FALSE');
CALL sp_add_column('victims', 'prime_case_marker',
    'INT AS (CASE WHEN is_prime = 1 THEN case_id ELSE NULL END) VIRTUAL');
CALL sp_add_index('victims', 'uq_victim_prime',
    'UNIQUE KEY uq_victim_prime (prime_case_marker)');

-- evidence : the exhibit the case turns on
CALL sp_add_column('evidence', 'is_prime', 'BOOLEAN NOT NULL DEFAULT FALSE');
CALL sp_add_column('evidence', 'prime_case_marker',
    'INT AS (CASE WHEN is_prime = 1 THEN case_id ELSE NULL END) VIRTUAL');
CALL sp_add_index('evidence', 'uq_evidence_prime',
    'UNIQUE KEY uq_evidence_prime (prime_case_marker)');

CREATE OR REPLACE VIEW v_suspect_summary AS
SELECT
    su.suspect_id,
    su.name,
    su.gender,
    su.status,
    su.phone,
    su.is_prime,
    c.case_id,
    c.case_no,
    c.status       AS case_status,
    c.category     AS case_category,
    c.occurrence_datetime,
    (SELECT COUNT(*) FROM arrests a WHERE a.suspect_id = su.suspect_id) AS arrest_count,
    (SELECT COUNT(*) FROM convictions cv WHERE cv.suspect_id = su.suspect_id) AS conviction_count,
    (SELECT COALESCE(SUM(cv.imprisonment_years), 0)
       FROM convictions cv WHERE cv.suspect_id = su.suspect_id) AS total_sentence_years
FROM suspects su
JOIN crime_cases c ON c.case_id = su.case_id
