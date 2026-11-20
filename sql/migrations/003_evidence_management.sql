-- =====================================================================
-- Migration 003 - Evidence Management
--
-- Widens evidence, adds the attachment / custody / forensic registers,
-- and gives every item a unique human-readable reference.
--
-- evidence_ref is added nullable first, backfilled, then tightened to
-- NOT NULL. Doing it in one step would fill existing rows with an empty
-- string, and the unique key would reject the second of them.
--
-- Object order matters here: the append-only guards are triggers on
-- evidence_custody_log, so that table is created before them.
--
-- The custody log is append-only. MySQL does not activate triggers for
-- cascading foreign key actions, so the guard cannot break the existing
-- "delete a case, delete its children" behaviour - scripts/
-- test_migration.py proves that on a copy rather than assuming it.
-- =====================================================================

-- ---------------------------------------------------------------------
-- evidence : identification
-- ---------------------------------------------------------------------
CALL sp_add_column('evidence', 'evidence_ref', 'VARCHAR(30) NULL');
CALL sp_add_column('evidence', 'item_name', 'VARCHAR(160) NULL');
CALL sp_add_column('evidence', 'evidence_category',
    "ENUM('physical','documentary','digital','biological','ballistic','trace','chemical','firearm','other') NOT NULL DEFAULT 'physical'");
CALL sp_add_column('evidence', 'detailed_description', 'TEXT NULL');

-- ---------------------------------------------------------------------
-- evidence : how it was seized and how it is kept
-- ---------------------------------------------------------------------
CALL sp_add_column('evidence', 'collection_location', 'VARCHAR(255) NULL');
CALL sp_add_column('evidence', 'collection_method', 'VARCHAR(120) NULL');
CALL sp_add_column('evidence', 'condition',
    "ENUM('intact','damaged','partial','degraded','unknown') NOT NULL DEFAULT 'unknown'");
CALL sp_add_column('evidence', 'packaging_type', 'VARCHAR(80) NULL');
CALL sp_add_column('evidence', 'seal_number', 'VARCHAR(60) NULL');

-- ---------------------------------------------------------------------
-- evidence : forensic examination summary
--
-- The detail lives in forensic_examinations; these three columns are
-- the current state, kept in step by the repository in one transaction.
-- ---------------------------------------------------------------------
CALL sp_add_column('evidence', 'forensic_status',
    "ENUM('not_required','pending','sent','under_examination','reported') NOT NULL DEFAULT 'not_required'");
CALL sp_add_column('evidence', 'laboratory_name', 'VARCHAR(160) NULL');
CALL sp_add_column('evidence', 'examination_result', 'VARCHAR(500) NULL');

-- ---------------------------------------------------------------------
-- evidence : integrity and lifecycle
-- ---------------------------------------------------------------------
CALL sp_add_column('evidence', 'digital_hash_sha256', 'CHAR(64) NULL');
CALL sp_add_column('evidence', 'evidence_status',
    "ENUM('seized','sealed','in_store','issued_to_court','under_examination','returned','destroyed') NOT NULL DEFAULT 'seized'");
CALL sp_add_column('evidence', 'updated_at',
    'TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP');

-- ---------------------------------------------------------------------
-- Backfill references: EV/<year>/<sequence within that year>
-- ---------------------------------------------------------------------
UPDATE evidence e
JOIN (
    SELECT evidence_id,
           YEAR(collected_datetime) AS ref_year,
           ROW_NUMBER() OVER (
               PARTITION BY YEAR(collected_datetime)
               ORDER BY collected_datetime, evidence_id
           ) AS rn
      FROM evidence
) x ON x.evidence_id = e.evidence_id
   SET e.evidence_ref = CONCAT('EV/', x.ref_year, '/', LPAD(x.rn, 6, '0'))
 WHERE e.evidence_ref IS NULL;

CALL sp_modify_column('evidence', 'evidence_ref', 'VARCHAR(30) NOT NULL');
CALL sp_add_index('evidence', 'uq_evidence_ref',
    'UNIQUE KEY uq_evidence_ref (evidence_ref)');
CALL sp_add_index('evidence', 'uq_evidence_seal',
    'UNIQUE KEY uq_evidence_seal (seal_number)');
CALL sp_add_index('evidence', 'idx_evidence_status',
    'INDEX idx_evidence_status (evidence_status)');
CALL sp_add_index('evidence', 'idx_evidence_forensic_status',
    'INDEX idx_evidence_forensic_status (forensic_status)');
CALL sp_add_index('evidence', 'idx_evidence_hash',
    'INDEX idx_evidence_hash (digital_hash_sha256)');
CALL sp_add_index('evidence', 'idx_evidence_category',
    'INDEX idx_evidence_category (evidence_category)');

SET @ddl := IF(
    (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'evidence'
        AND CONSTRAINT_NAME = 'chk_evidence_hash') = 0,
    "ALTER TABLE evidence ADD CONSTRAINT chk_evidence_hash CHECK (digital_hash_sha256 IS NULL OR CHAR_LENGTH(digital_hash_sha256) = 64)",
    'DO 0');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------
-- evidence_sequences : per-year counter for the reference number,
-- mirroring the proven case_sequences pattern.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_sequences (
    yr        INT NOT NULL,
    last_seq  INT NOT NULL DEFAULT 0,
    PRIMARY KEY (yr)
) ENGINE = InnoDB;

-- The backfill above handed out numbers the counter knows nothing
-- about, so it has to be brought up to the highest sequence already in
-- use per year or the next insert would repeat one.
UPDATE evidence_sequences es
JOIN (
    SELECT CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(evidence_ref, '/', 2), '/', -1) AS UNSIGNED) AS yr,
           CAST(MAX(SUBSTRING_INDEX(evidence_ref, '/', -1)) AS UNSIGNED) AS mx
      FROM evidence
     WHERE evidence_ref LIKE 'EV/%'
     GROUP BY CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(evidence_ref, '/', 2), '/', -1) AS UNSIGNED)
) x ON x.yr = es.yr
   SET es.last_seq = GREATEST(es.last_seq, x.mx);

INSERT INTO evidence_sequences (yr, last_seq)
SELECT x.yr, x.mx
FROM (
    SELECT CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(evidence_ref, '/', 2), '/', -1) AS UNSIGNED) AS yr,
           CAST(MAX(SUBSTRING_INDEX(evidence_ref, '/', -1)) AS UNSIGNED) AS mx
      FROM evidence
     WHERE evidence_ref LIKE 'EV/%'
     GROUP BY CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(evidence_ref, '/', 2), '/', -1) AS UNSIGNED)
) x
WHERE NOT EXISTS (SELECT 1 FROM evidence_sequences es WHERE es.yr = x.yr);

-- ---------------------------------------------------------------------
-- evidence_attachments : files, never overwritten
--
-- stored_path is relative to the uploads directory so a moved install
-- keeps working; sha256 lets the app prove the bytes on disk still match
-- what was recorded.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_attachments (
    attachment_id       INT           NOT NULL AUTO_INCREMENT,
    evidence_id         INT           NOT NULL,
    stored_path         VARCHAR(500)  NOT NULL,
    original_name       VARCHAR(255)  NOT NULL,
    mime_type           VARCHAR(120)  NULL,
    size_bytes          BIGINT        NOT NULL,
    sha256              CHAR(64)      NOT NULL,
    is_original         BOOLEAN       NOT NULL DEFAULT TRUE,
    notes               VARCHAR(500)  NULL,
    uploaded_by_user_id INT           NOT NULL,
    uploaded_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (attachment_id),
    UNIQUE KEY uq_attachment_hash (evidence_id, sha256),
    KEY idx_attach_evidence (evidence_id),
    KEY idx_attach_uploaded_by (uploaded_by_user_id),
    CONSTRAINT fk_attach_evidence FOREIGN KEY (evidence_id)
        REFERENCES evidence (evidence_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_attach_user FOREIGN KEY (uploaded_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_attach_size CHECK (size_bytes >= 0)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- evidence_custody_log : who held the item, and when. Append-only.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_custody_log (
    custody_id          INT          NOT NULL AUTO_INCREMENT,
    evidence_id         INT          NOT NULL,
    sequence_no         INT          NOT NULL,
    event_type          ENUM('collected','stored','transferred','received','issued_to_court','returned','examined')
                        NOT NULL,
    from_officer_id     INT          NULL,
    to_officer_id       INT          NULL,
    purpose             VARCHAR(255) NULL,
    seal_intact         BOOLEAN      NOT NULL DEFAULT TRUE,
    occurred_at         DATETIME     NOT NULL,
    remarks             VARCHAR(500) NULL,
    recorded_by_user_id INT          NOT NULL,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (custody_id),
    UNIQUE KEY uq_custody_sequence (evidence_id, sequence_no),
    KEY idx_custody_evidence (evidence_id),
    KEY idx_custody_occurred (occurred_at),
    KEY idx_custody_from (from_officer_id),
    KEY idx_custody_to (to_officer_id),
    KEY idx_custody_recorded_by (recorded_by_user_id),
    CONSTRAINT fk_custody_evidence FOREIGN KEY (evidence_id)
        REFERENCES evidence (evidence_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_custody_from FOREIGN KEY (from_officer_id)
        REFERENCES officers (officer_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_custody_to FOREIGN KEY (to_officer_id)
        REFERENCES officers (officer_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_custody_user FOREIGN KEY (recorded_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_custody_sequence CHECK (sequence_no >= 1)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- forensic_examinations : one row per request to a laboratory
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forensic_examinations (
    examination_id      INT          NOT NULL AUTO_INCREMENT,
    evidence_id         INT          NOT NULL,
    request_no          VARCHAR(60)  NOT NULL,
    laboratory_name     VARCHAR(160) NOT NULL,
    examiner_name       VARCHAR(120) NULL,
    examination_type    VARCHAR(120) NULL,
    sent_datetime       DATETIME     NOT NULL,
    completed_datetime  DATETIME     NULL,
    result_status       ENUM('pending','inconclusive','exculpatory','incriminating','other')
                        NOT NULL DEFAULT 'pending',
    result_summary      TEXT         NULL,
    report_path         VARCHAR(255) NULL,
    remarks             VARCHAR(500) NULL,
    recorded_by_user_id INT          NOT NULL,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (examination_id),
    UNIQUE KEY uq_forensic_request_no (request_no),
    KEY idx_forensic_evidence (evidence_id),
    KEY idx_forensic_status (result_status),
    KEY idx_forensic_recorded_by (recorded_by_user_id),
    CONSTRAINT fk_forensic_evidence FOREIGN KEY (evidence_id)
        REFERENCES evidence (evidence_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_forensic_user FOREIGN KEY (recorded_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_forensic_dates CHECK (
        completed_datetime IS NULL OR completed_datetime >= sent_datetime
    )
) ENGINE = InnoDB;

DELIMITER $$

-- ---------------------------------------------------------------------
-- trg_evidence_before_insert : assign the unique reference number, the
-- same way trg_cases_before_insert assigns case_no.
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_evidence_before_insert $$
CREATE TRIGGER trg_evidence_before_insert
BEFORE INSERT ON evidence
FOR EACH ROW
BEGIN
    DECLARE v_year INT;
    DECLARE v_seq  INT;

    IF NEW.evidence_ref IS NULL OR NEW.evidence_ref = '' THEN
        SET v_year = YEAR(COALESCE(NEW.collected_datetime, NOW()));

        INSERT INTO evidence_sequences (yr, last_seq)
        VALUES (v_year, 1)
        ON DUPLICATE KEY UPDATE last_seq = last_seq + 1;

        SELECT last_seq INTO v_seq FROM evidence_sequences WHERE yr = v_year;

        SET NEW.evidence_ref = CONCAT('EV/', v_year, '/', LPAD(v_seq, 6, '0'));
    END IF;
END $$

-- ---------------------------------------------------------------------
-- trg_evidence_before_custody : v1 shipped this as an AFTER INSERT
-- trigger that ran UPDATE evidence on the row it had just inserted, and
-- MySQL refuses that with error 1442 - a trigger cannot touch the table
-- whose statement fired it. Recording evidence with a blank chain of
-- custody date therefore failed. triggers.sql holds the corrected
-- BEFORE INSERT version; this recreates it here so a database upgraded
-- by migrate.py alone does not lose the behaviour.
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_evidence_after_insert $$
DROP TRIGGER IF EXISTS trg_evidence_before_custody $$
CREATE TRIGGER trg_evidence_before_custody
BEFORE INSERT ON evidence
FOR EACH ROW
BEGIN
    IF NEW.chain_of_custody_datetime IS NULL THEN
        SET NEW.chain_of_custody_datetime = COALESCE(NEW.collected_datetime, NOW());
    END IF;
END $$

-- ---------------------------------------------------------------------
-- Custody log guards: a mistake is corrected by adding another row,
-- never by rewriting the history of who held what.
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_custody_log_before_update $$
CREATE TRIGGER trg_custody_log_before_update
BEFORE UPDATE ON evidence_custody_log
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Custody log entries are append-only and cannot be edited';
END $$

DROP TRIGGER IF EXISTS trg_custody_log_before_delete $$
CREATE TRIGGER trg_custody_log_before_delete
BEFORE DELETE ON evidence_custody_log
FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Custody log entries are append-only and cannot be deleted';
END $$

DELIMITER ;

-- ---------------------------------------------------------------------
-- Backfill custody history so no item starts its life with a gap.
-- Re-runnable: only items with no log rows get the opening entry.
-- ---------------------------------------------------------------------
INSERT INTO evidence_custody_log
    (evidence_id, sequence_no, event_type, to_officer_id, purpose,
     occurred_at, recorded_by_user_id)
SELECT
    e.evidence_id,
    1,
    'collected',
    e.collected_by_officer_id,
    'Seized at collection',
    e.collected_datetime,
    (SELECT c.filed_by_user_id FROM crime_cases c WHERE c.case_id = e.case_id)
FROM evidence e
WHERE NOT EXISTS (
    SELECT 1 FROM evidence_custody_log l WHERE l.evidence_id = e.evidence_id
);
