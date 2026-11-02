-- =====================================================================
-- Crime Record Management System - Schema
-- Target: MySQL 8.0+
-- Run via: py scripts\setup_db.py   (do not pipe this file through the CLI;
--         the installer splits statements itself so it stays idempotent)
-- =====================================================================

CREATE DATABASE IF NOT EXISTS crime_records
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE crime_records;

-- ---------------------------------------------------------------------
-- case_sequences : per-year counter used to build a unique case_no
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_sequences (
    yr         INT      NOT NULL,
    last_seq   INT      NOT NULL DEFAULT 0,
    PRIMARY KEY (yr)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- police_stations
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS police_stations (
    station_id         INT          NOT NULL AUTO_INCREMENT,
    name               VARCHAR(120) NOT NULL,
    district           VARCHAR(60)  NOT NULL,
    address            VARCHAR(255) NULL,
    phone              VARCHAR(20)  NULL,
    incharge_officer_id INT         NULL,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (station_id),
    UNIQUE KEY uq_station_name (name),
    KEY idx_station_district (district)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- officers
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS officers (
    officer_id  INT          NOT NULL AUTO_INCREMENT,
    badge_no    VARCHAR(20)  NOT NULL,
    name        VARCHAR(120) NOT NULL,
    -- RANK is reserved in MySQL 8.0, so it always needs backticks.
    `rank`      VARCHAR(40)  NOT NULL,
    station_id  INT          NOT NULL,
    phone       VARCHAR(20)  NULL,
    join_date   DATE         NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    PRIMARY KEY (officer_id),
    UNIQUE KEY uq_officer_badge (badge_no),
    KEY idx_officer_station (station_id),
    KEY idx_officer_name (name),
    CONSTRAINT fk_officer_station FOREIGN KEY (station_id)
        REFERENCES police_stations (station_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE = InnoDB;

-- police_stations -> officers (added after officers exists: circular reference)
SET @fk_exists := (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE()
      AND TABLE_NAME = 'police_stations'
      AND CONSTRAINT_NAME = 'fk_station_incharge'
);
SET @ddl := IF(@fk_exists = 0,
    'ALTER TABLE police_stations
     ADD CONSTRAINT fk_station_incharge FOREIGN KEY (incharge_officer_id)
     REFERENCES officers (officer_id)
     ON UPDATE CASCADE ON DELETE SET NULL',
    'DO 0');
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ---------------------------------------------------------------------
-- offence_sections : the law library (BNS / IPC)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS offence_sections (
    section_id            INT           NOT NULL AUTO_INCREMENT,
    law_code              ENUM('BNS','IPC') NOT NULL,
    section_no            VARCHAR(20)   NOT NULL,
    offence_name          VARCHAR(200)  NOT NULL,
    category              ENUM('cognizable','non_cognizable') NOT NULL,
    severity              ENUM('low','medium','high','grave') NOT NULL,
    min_imprisonment_yrs  DECIMAL(4,1)  NULL,
    max_imprisonment_yrs  DECIMAL(4,1)  NULL,
    fine_cap              DECIMAL(12,2) NULL,
    description           TEXT          NULL,
    PRIMARY KEY (section_id),
    UNIQUE KEY uq_offence_law_section (law_code, section_no),
    KEY idx_offence_category (category),
    KEY idx_offence_severity (severity),
    CONSTRAINT chk_offence_sentence_range CHECK (
        min_imprisonment_yrs IS NULL OR max_imprisonment_yrs IS NULL
        OR min_imprisonment_yrs <= max_imprisonment_yrs
    )
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- users : application logins
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id        INT          NOT NULL AUTO_INCREMENT,
    username       VARCHAR(50)  NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           ENUM('admin','officer','viewer') NOT NULL DEFAULT 'viewer',
    officer_id     INT          NULL,
    full_name      VARCHAR(120) NULL,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at  DATETIME     NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_user_username (username),
    KEY idx_user_role (role),
    KEY idx_user_officer (officer_id),
    CONSTRAINT fk_user_officer FOREIGN KEY (officer_id)
        REFERENCES officers (officer_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- crime_cases : the hub table
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crime_cases (
    case_id                  INT          NOT NULL AUTO_INCREMENT,
    case_no                  VARCHAR(25)  NOT NULL,
    station_id               INT          NOT NULL,
    investigating_officer_id INT          NOT NULL,
    filed_by_user_id         INT          NOT NULL,
    category                 VARCHAR(60)  NOT NULL,
    offence_type             VARCHAR(120) NULL,
    occurrence_datetime      DATETIME     NOT NULL,
    reporting_datetime       DATETIME     NOT NULL,
    place_of_occurrence      VARCHAR(255) NULL,
    description              TEXT         NULL,
    status                   ENUM('registered','under_investigation','charges_filed','trial',
                                 'closed_convicted','closed_acquitted','closed_untraceable')
                            NOT NULL DEFAULT 'registered',
    closed_datetime          DATETIME     NULL,
    summary                  TEXT         NULL,
    offence_count            INT          NOT NULL DEFAULT 0,
    created_at               TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id),
    UNIQUE KEY uq_case_no (case_no),
    KEY idx_case_status (status),
    KEY idx_case_station (station_id),
    KEY idx_case_officer (investigating_officer_id),
    KEY idx_case_filed_by (filed_by_user_id),
    KEY idx_case_occurrence (occurrence_datetime),
    KEY idx_case_category (category),
    KEY idx_case_reporting (reporting_datetime),
    CONSTRAINT fk_case_station FOREIGN KEY (station_id)
        REFERENCES police_stations (station_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_case_officer FOREIGN KEY (investigating_officer_id)
        REFERENCES officers (officer_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_case_filed_by FOREIGN KEY (filed_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_case_dates CHECK (occurrence_datetime <= reporting_datetime),
    CONSTRAINT chk_case_closed CHECK (
        (status IN ('closed_convicted','closed_acquitted','closed_untraceable')
            AND closed_datetime IS NOT NULL)
        OR
        (status NOT IN ('closed_convicted','closed_acquitted','closed_untraceable')
            AND closed_datetime IS NULL)
    )
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- case_status_history : append-only, written by triggers only
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_status_history (
    history_id       INT          NOT NULL AUTO_INCREMENT,
    case_id          INT          NOT NULL,
    old_status       VARCHAR(30)  NULL,
    new_status       VARCHAR(30)  NOT NULL,
    changed_by_user_id INT        NOT NULL,
    remark           VARCHAR(255) NULL,
    changed_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (history_id),
    KEY idx_history_case (case_id),
    KEY idx_history_changed_at (changed_at),
    KEY idx_history_user (changed_by_user_id),
    CONSTRAINT fk_history_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_history_user FOREIGN KEY (changed_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- case_offences : M:N between a case and the sections charged
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_offences (
    case_id       INT          NOT NULL,
    section_id    INT          NOT NULL,
    accused_role  ENUM('primary','secondary') NOT NULL DEFAULT 'primary',
    added_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (case_id, section_id),
    KEY idx_case_offences_section (section_id),
    CONSTRAINT fk_case_offences_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_case_offences_section FOREIGN KEY (section_id)
        REFERENCES offence_sections (section_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- suspects / victims / witnesses : children of a case
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suspects (
    suspect_id        INT         NOT NULL AUTO_INCREMENT,
    case_id           INT         NOT NULL,
    name              VARCHAR(120) NOT NULL,
    alias             VARCHAR(120) NULL,
    date_of_birth     DATE        NULL,
    gender            ENUM('male','female','other','unknown') NOT NULL DEFAULT 'unknown',
    address           VARCHAR(255) NULL,
    phone             VARCHAR(20)  NULL,
    identifying_marks VARCHAR(255) NULL,
    status            ENUM('wanted','arrested','in_custody','bailed','released',
                          'convicted','acquitted','untraceable') NOT NULL DEFAULT 'wanted',
    created_at        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (suspect_id),
    KEY idx_suspect_case (case_id),
    KEY idx_suspect_status (status),
    KEY idx_suspect_name (name),
    CONSTRAINT fk_suspect_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS victims (
    victim_id    INT         NOT NULL AUTO_INCREMENT,
    case_id      INT         NOT NULL,
    name         VARCHAR(120) NOT NULL,
    age          INT         NULL,
    gender       ENUM('male','female','other','unknown') NOT NULL DEFAULT 'unknown',
    phone        VARCHAR(20)  NULL,
    address      VARCHAR(255) NULL,
    injury_level ENUM('none','minor','moderate','grievous','fatal') NOT NULL DEFAULT 'none',
    statement    TEXT        NULL,
    created_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (victim_id),
    KEY idx_victim_case (case_id),
    KEY idx_victim_name (name),
    CONSTRAINT fk_victim_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_victim_age CHECK (age IS NULL OR (age >= 0 AND age <= 120))
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS witnesses (
    witness_id   INT         NOT NULL AUTO_INCREMENT,
    case_id      INT         NOT NULL,
    name         VARCHAR(120) NOT NULL,
    phone        VARCHAR(20)  NULL,
    address      VARCHAR(255) NULL,
    statement    TEXT        NULL,
    is_reliable  BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (witness_id),
    KEY idx_witness_case (case_id),
    KEY idx_witness_name (name),
    CONSTRAINT fk_witness_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- evidence
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id              INT          NOT NULL AUTO_INCREMENT,
    case_id                  INT          NOT NULL,
    type                     ENUM('physical','documentary','digital','forensic','testimonial')
                             NOT NULL,
    description              VARCHAR(255) NOT NULL,
    collected_by_officer_id  INT          NOT NULL,
    collected_datetime       DATETIME     NOT NULL,
    seized_under              VARCHAR(120) NULL,
    storage_location         VARCHAR(120) NULL,
    chain_of_custody_datetime DATETIME    NULL,
    created_at               TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (evidence_id),
    KEY idx_evidence_case (case_id),
    KEY idx_evidence_type (type),
    KEY idx_evidence_officer (collected_by_officer_id),
    CONSTRAINT fk_evidence_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_evidence_officer FOREIGN KEY (collected_by_officer_id)
        REFERENCES officers (officer_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- arrests / court_proceedings / convictions
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS arrests (
    arrest_id              INT          NOT NULL AUTO_INCREMENT,
    case_id                INT          NOT NULL,
    suspect_id             INT          NOT NULL,
    arrested_by_officer_id INT          NOT NULL,
    arrest_datetime        DATETIME     NOT NULL,
    place_of_arrest        VARCHAR(255) NULL,
    remand_status          ENUM('not_remanded','police_remand','judicial_remand','bail')
                           NOT NULL DEFAULT 'not_remanded',
    bail_amount            DECIMAL(12,2) NULL,
    created_at             TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (arrest_id),
    KEY idx_arrest_case (case_id),
    KEY idx_arrest_suspect (suspect_id),
    KEY idx_arrest_officer (arrested_by_officer_id),
    CONSTRAINT fk_arrest_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_arrest_suspect FOREIGN KEY (suspect_id)
        REFERENCES suspects (suspect_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_arrest_officer FOREIGN KEY (arrested_by_officer_id)
        REFERENCES officers (officer_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_bail_amount CHECK (bail_amount IS NULL OR bail_amount >= 0)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS court_proceedings (
    proceeding_id     INT          NOT NULL AUTO_INCREMENT,
    case_id           INT          NOT NULL,
    court_name        VARCHAR(160) NOT NULL,
    hearing_datetime  DATETIME     NOT NULL,
    stage             ENUM('first_hearing','charge_frame','evidence','arguments','verdict')
                      NOT NULL DEFAULT 'first_hearing',
    judge_name        VARCHAR(120) NULL,
    next_hearing_datetime DATETIME  NULL,
    remarks           VARCHAR(500) NULL,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (proceeding_id),
    KEY idx_proceeding_case (case_id),
    KEY idx_proceeding_hearing (hearing_datetime),
    KEY idx_proceeding_next_hearing (next_hearing_datetime),
    CONSTRAINT fk_proceeding_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS convictions (
    conviction_id   INT          NOT NULL AUTO_INCREMENT,
    case_id         INT          NOT NULL,
    suspect_id      INT          NOT NULL,
    court_name      VARCHAR(160) NOT NULL,
    verdict         ENUM('guilty','acquitted','case_dismissed') NOT NULL,
    sentence_type   ENUM('none','fine','imprisonment','community_service','life_imprisonment')
                     NOT NULL DEFAULT 'none',
    imprisonment_years DECIMAL(4,1) NULL,
    fine_amount     DECIMAL(12,2) NULL,
    sentence_start  DATE         NULL,
    release_expected DATE        NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conviction_id),
    KEY idx_conviction_case (case_id),
    KEY idx_conviction_suspect (suspect_id),
    KEY idx_conviction_verdict (verdict),
    CONSTRAINT fk_conviction_case FOREIGN KEY (case_id)
        REFERENCES crime_cases (case_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_conviction_suspect FOREIGN KEY (suspect_id)
        REFERENCES suspects (suspect_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT chk_conviction_fine CHECK (fine_amount IS NULL OR fine_amount >= 0),
    CONSTRAINT chk_conviction_years CHECK (
        imprisonment_years IS NULL OR imprisonment_years >= 0
    )
) ENGINE = InnoDB;
