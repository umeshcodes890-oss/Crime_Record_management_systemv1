-- =====================================================================
-- Migration 002 - Witness Management
--
-- Widens witnesses and adds the statement, interview and protection
-- registers. Two things are deliberate:
--
-- 1. witnesses.statement is kept. Existing rows hold real statements
--    and v1 screens read the column, so it stays as a mirror of the
--    current version in witness_statements rather than being dropped.
--
-- 2. witnesses.is_reliable stays a human decision. The new columns
--    record who made that decision, when, and why - nothing here
--    computes or suggests credibility.
-- =====================================================================

-- ---------------------------------------------------------------------
-- witnesses : personal detail
-- ---------------------------------------------------------------------
CALL sp_add_column('witnesses', 'date_of_birth', 'DATE NULL');
CALL sp_add_column('witnesses', 'gender',
    "ENUM('male','female','other','unknown') NOT NULL DEFAULT 'unknown'");
CALL sp_add_column('witnesses', 'email', 'VARCHAR(160) NULL');
CALL sp_add_column('witnesses', 'occupation', 'VARCHAR(120) NULL');
CALL sp_add_column('witnesses', 'witness_type',
    "ENUM('eyewitness','expert','character','medical','police','other') NOT NULL DEFAULT 'eyewitness'");
CALL sp_add_column('witnesses', 'relationship_to_victim', 'VARCHAR(120) NULL');
CALL sp_add_column('witnesses', 'relationship_to_accused', 'VARCHAR(120) NULL');

-- ---------------------------------------------------------------------
-- witnesses : what they observed
-- ---------------------------------------------------------------------
CALL sp_add_column('witnesses', 'observation_datetime', 'DATETIME NULL');
CALL sp_add_column('witnesses', 'observation_location', 'VARCHAR(255) NULL');
CALL sp_add_column('witnesses', 'statement_language', 'VARCHAR(60) NOT NULL DEFAULT ''en''');

-- ---------------------------------------------------------------------
-- witnesses : availability, protection and privacy
-- ---------------------------------------------------------------------
CALL sp_add_column('witnesses', 'availability_status',
    "ENUM('available','unavailable','deceased','relocated','unknown') NOT NULL DEFAULT 'unknown'");
CALL sp_add_column('witnesses', 'protection_required', 'BOOLEAN NOT NULL DEFAULT FALSE');
CALL sp_add_column('witnesses', 'confidentiality_level',
    "ENUM('public','internal','confidential','restricted') NOT NULL DEFAULT 'internal'");

-- ---------------------------------------------------------------------
-- witnesses : the reliability decision, attributed
-- ---------------------------------------------------------------------
CALL sp_add_column('witnesses', 'reliability_remark', 'VARCHAR(500) NULL');
CALL sp_add_column('witnesses', 'assessed_by_user_id', 'INT NULL');
CALL sp_add_column('witnesses', 'assessed_at', 'DATETIME NULL');
CALL sp_add_column('witnesses', 'updated_at',
    'TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP');

CALL sp_add_index('witnesses', 'idx_witness_assessed_by',
    'INDEX idx_witness_assessed_by (assessed_by_user_id)');
CALL sp_add_index('witnesses', 'idx_witness_type',
    'INDEX idx_witness_type (witness_type)');
CALL sp_add_index('witnesses', 'idx_witness_availability',
    'INDEX idx_witness_availability (availability_status)');
CALL sp_add_index('witnesses', 'idx_witness_confidentiality',
    'INDEX idx_witness_confidentiality (confidentiality_level)');
CALL sp_add_index('witnesses', 'idx_witness_protection',
    'INDEX idx_witness_protection (protection_required)');

SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'witnesses'
        AND CONSTRAINT_NAME = 'fk_witness_assessed_by') = 0,
    'ALTER TABLE witnesses ADD CONSTRAINT fk_witness_assessed_by FOREIGN KEY (assessed_by_user_id)
     REFERENCES users (user_id) ON UPDATE CASCADE ON DELETE SET NULL',
    'DO 0');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------
-- witness_statements : versioned, append-only
--
-- A new version never removes the old one. active_marker turns
-- "exactly one current version per witness" into a database
-- constraint rather than a convention the application hopes to keep.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS witness_statements (
    statement_id         INT          NOT NULL AUTO_INCREMENT,
    witness_id           INT          NOT NULL,
    version              INT          NOT NULL,
    statement_body       TEXT         NOT NULL,
    language             VARCHAR(60)  NOT NULL DEFAULT 'en',
    recorded_by_user_id  INT          NOT NULL,
    recorded_at          DATETIME     NOT NULL,
    superseded_at        DATETIME     NULL,
    remark               VARCHAR(500) NULL,
    created_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_marker        DATETIME
        AS (COALESCE(superseded_at, CAST('9999-12-31 00:00:00' AS DATETIME))) STORED NOT NULL,
    PRIMARY KEY (statement_id),
    UNIQUE KEY uq_statement_version (witness_id, version),
    UNIQUE KEY uq_statement_current (witness_id, active_marker),
    KEY idx_ws_witness (witness_id),
    KEY idx_ws_recorded_by (recorded_by_user_id),
    CONSTRAINT fk_ws_witness FOREIGN KEY (witness_id)
        REFERENCES witnesses (witness_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ws_user FOREIGN KEY (recorded_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_ws_version CHECK (version >= 1)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- witness_interviews : scheduling and outcome
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS witness_interviews (
    interview_id         INT          NOT NULL AUTO_INCREMENT,
    witness_id           INT          NOT NULL,
    scheduled_datetime   DATETIME     NOT NULL,
    held_datetime        DATETIME     NULL,
    location             VARCHAR(255) NULL,
    interviewer_officer_id INT        NULL,
    duration_minutes     INT          NULL,
    outcome              ENUM('scheduled','completed','adjourned','witness_absent',
                              'refused','other') NOT NULL DEFAULT 'scheduled',
    notes                TEXT         NULL,
    recorded_by_user_id  INT          NOT NULL,
    created_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (interview_id),
    KEY idx_wi_witness (witness_id),
    KEY idx_wi_scheduled (scheduled_datetime),
    KEY idx_wi_interviewer (interviewer_officer_id),
    KEY idx_wi_recorded_by (recorded_by_user_id),
    CONSTRAINT fk_wi_witness FOREIGN KEY (witness_id)
        REFERENCES witnesses (witness_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_wi_officer FOREIGN KEY (interviewer_officer_id)
        REFERENCES officers (officer_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_wi_user FOREIGN KEY (recorded_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_wi_duration CHECK (duration_minutes IS NULL OR duration_minutes >= 0)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- witness_protection : measures taken for a witness's safety
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS witness_protection (
    protection_id        INT          NOT NULL AUTO_INCREMENT,
    witness_id           INT          NOT NULL,
    measure              VARCHAR(200) NOT NULL,
    basis                VARCHAR(500) NOT NULL,
    start_date           DATE         NOT NULL,
    end_date             DATE         NULL,
    status               ENUM('active','revoked','completed','expired')
                         NOT NULL DEFAULT 'active',
    review_datetime      DATETIME     NULL,
    authorised_by_user_id INT         NOT NULL,
    remarks              VARCHAR(500) NULL,
    created_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (protection_id),
    KEY idx_wp_witness (witness_id),
    KEY idx_wp_status (status),
    KEY idx_wp_authorised_by (authorised_by_user_id),
    CONSTRAINT fk_wp_witness FOREIGN KEY (witness_id)
        REFERENCES witnesses (witness_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_wp_user FOREIGN KEY (authorised_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_wp_dates CHECK (end_date IS NULL OR end_date >= start_date)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- Backfill: every statement already on a witness becomes version 1.
-- Recorded against the user who filed the case, because that is the
-- only attribution the v1 data actually supports.
-- Re-runnable: only fills witnesses that have no versions yet.
-- ---------------------------------------------------------------------
INSERT INTO witness_statements
    (witness_id, version, statement_body, language, recorded_by_user_id, recorded_at)
SELECT
    w.witness_id,
    1,
    w.statement,
    'en',
    (SELECT c.filed_by_user_id FROM crime_cases c WHERE c.case_id = w.case_id),
    COALESCE(w.created_at, NOW())
FROM witnesses w
WHERE w.statement IS NOT NULL
  AND TRIM(w.statement) <> ''
  AND NOT EXISTS (
        SELECT 1 FROM witness_statements s WHERE s.witness_id = w.witness_id
  );
