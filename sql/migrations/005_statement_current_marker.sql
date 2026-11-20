-- =====================================================================
-- witness_statements.active_marker : invert the marker
--
-- Migration 002 introduced the column as
--     COALESCE(superseded_at, CAST('9999-12-31 00:00:00' AS DATETIME))
-- which is the right shape for "a witness has at most one current
-- version", but it collided in practice: two versions of one witness's
-- statement superseded within the same second were stamped with the same
-- second-precision timestamp, and uq_statement_current then rejected the
-- insert with a duplicate-key error.
--
-- Inverting it removes the dependence on clock precision. A current
-- version carries the marker; a superseded one carries NULL, and a MySQL
-- unique index accepts any number of NULLs. What the index now enforces
-- is exactly the rule that was wanted: no witness can have two
-- un-superseded statements, however many earlier versions it keeps.
-- =====================================================================

CALL sp_modify_column(
    'witness_statements',
    'active_marker',
    'DATETIME AS (CASE WHEN superseded_at IS NULL
                          THEN CAST(''9999-12-31 00:00:00'' AS DATETIME)
                      ELSE NULL
                 END) STORED'
);
