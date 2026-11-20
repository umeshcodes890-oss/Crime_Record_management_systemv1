-- =====================================================================
-- Migration 001 - Victim Management
--
-- Widens the existing victims table and adds the three registers that
-- hang off a victim. Nothing is dropped and no existing column changes
-- meaning, so every v1 screen and view keeps working.
--
-- 'age' stays a stored, manually entered field: existing rows carry an
-- age but no date of birth, and deriving one from the other would
-- rewrite history. The UI fills age from date of birth when both are
-- known.
-- =====================================================================

-- ---------------------------------------------------------------------
-- victims : personal detail
-- ---------------------------------------------------------------------
CALL sp_add_column('victims', 'date_of_birth', 'DATE NULL');
CALL sp_add_column('victims', 'email', 'VARCHAR(160) NULL');
CALL sp_add_column('victims', 'occupation', 'VARCHAR(120) NULL');
CALL sp_add_column('victims', 'national_id', 'VARCHAR(40) NULL');

-- ---------------------------------------------------------------------
-- victims : emergency contact and relationship
-- ---------------------------------------------------------------------
CALL sp_add_column('victims', 'emergency_contact_name', 'VARCHAR(120) NULL');
CALL sp_add_column('victims', 'emergency_contact_phone', 'VARCHAR(20) NULL');
CALL sp_add_column('victims', 'relationship_to_accused', 'VARCHAR(120) NULL');

-- ---------------------------------------------------------------------
-- victims : the incident as the victim experienced it
-- ---------------------------------------------------------------------
CALL sp_add_column('victims', 'incident_datetime', 'DATETIME NULL');
CALL sp_add_column('victims', 'incident_location', 'VARCHAR(255) NULL');

-- ---------------------------------------------------------------------
-- victims : medical assistance
-- ---------------------------------------------------------------------
CALL sp_add_column('victims', 'medical_assistance_status',
    "ENUM('none','requested','provided','completed','declined') NOT NULL DEFAULT 'none'");
CALL sp_add_column('victims', 'hospital_name', 'VARCHAR(160) NULL');
CALL sp_add_column('victims', 'hospital_reference', 'VARCHAR(60) NULL');
CALL sp_add_column('victims', 'special_assistance', 'VARCHAR(255) NULL');

-- ---------------------------------------------------------------------
-- victims : privacy and bookkeeping
-- ---------------------------------------------------------------------
CALL sp_add_column('victims', 'confidentiality_level',
    "ENUM('public','internal','confidential','restricted') NOT NULL DEFAULT 'internal'");
CALL sp_add_column('victims', 'updated_at',
    'TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP');

CALL sp_add_index('victims', 'idx_victim_incident',
    'INDEX idx_victim_incident (incident_datetime)');
CALL sp_add_index('victims', 'idx_victim_confidentiality',
    'INDEX idx_victim_confidentiality (confidentiality_level)');
CALL sp_add_index('victims', 'idx_victim_medical_status',
    'INDEX idx_victim_medical_status (medical_assistance_status)');

-- ---------------------------------------------------------------------
-- victim_medical_records : one row per episode of treatment
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS victim_medical_records (
    medical_record_id     INT           NOT NULL AUTO_INCREMENT,
    victim_id             INT           NOT NULL,
    facility              VARCHAR(160)  NOT NULL,
    treating_doctor       VARCHAR(120)  NULL,
    treatment_type        VARCHAR(120)  NOT NULL,
    description           TEXT          NULL,
    admitted_datetime     DATETIME      NULL,
    discharged_datetime   DATETIME      NULL,
    cost_incurred         DECIMAL(12,2) NULL,
    medical_report_path   VARCHAR(255)  NULL,
    remarks               VARCHAR(500)  NULL,
    recorded_by_user_id   INT           NOT NULL,
    created_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (medical_record_id),
    KEY idx_vmr_victim (victim_id),
    KEY idx_vmr_recorded_by (recorded_by_user_id),
    KEY idx_vmr_admitted (admitted_datetime),
    CONSTRAINT fk_vmr_victim FOREIGN KEY (victim_id)
        REFERENCES victims (victim_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_vmr_user FOREIGN KEY (recorded_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_vmr_dates CHECK (
        admitted_datetime IS NULL OR discharged_datetime IS NULL
        OR admitted_datetime <= discharged_datetime
    ),
    CONSTRAINT chk_vmr_cost CHECK (cost_incurred IS NULL OR cost_incurred >= 0)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- victim_contacts : every time the case worker reached the victim
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS victim_contacts (
    contact_id           INT          NOT NULL AUTO_INCREMENT,
    victim_id            INT          NOT NULL,
    contact_type         ENUM('phone','visit','email','letter','court_appearance','other')
                         NOT NULL DEFAULT 'phone',
    contact_datetime     DATETIME     NOT NULL,
    made_by_officer_id   INT          NULL,
    purpose              VARCHAR(255) NULL,
    outcome              VARCHAR(500) NULL,
    follow_up_required   BOOLEAN      NOT NULL DEFAULT FALSE,
    follow_up_datetime   DATETIME     NULL,
    created_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (contact_id),
    KEY idx_vc_victim (victim_id),
    KEY idx_vc_officer (made_by_officer_id),
    KEY idx_vc_datetime (contact_datetime),
    CONSTRAINT fk_vc_victim FOREIGN KEY (victim_id)
        REFERENCES victims (victim_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_vc_officer FOREIGN KEY (made_by_officer_id)
        REFERENCES officers (officer_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------
-- victim_compensation : scheme, award and payment tracking
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS victim_compensation (
    compensation_id      INT           NOT NULL AUTO_INCREMENT,
    victim_id            INT           NOT NULL,
    scheme_name          VARCHAR(200)  NOT NULL,
    compensation_type    ENUM('monetary','medical_support','legal_aid','employment','other')
                         NOT NULL DEFAULT 'monetary',
    application_date     DATE          NULL,
    awarded_amount       DECIMAL(12,2) NULL,
    received_amount      DECIMAL(12,2) NULL,
    status               ENUM('not_applied','applied','under_review','approved',
                              'partially_paid','paid','rejected')
                         NOT NULL DEFAULT 'not_applied',
    sanctioning_authority VARCHAR(160) NULL,
    order_reference      VARCHAR(80)   NULL,
    remarks              VARCHAR(500)  NULL,
    recorded_by_user_id  INT           NOT NULL,
    created_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (compensation_id),
    KEY idx_vcomp_victim (victim_id),
    KEY idx_vcomp_status (status),
    KEY idx_vcomp_recorded_by (recorded_by_user_id),
    CONSTRAINT fk_vcomp_victim FOREIGN KEY (victim_id)
        REFERENCES victims (victim_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_vcomp_user FOREIGN KEY (recorded_by_user_id)
        REFERENCES users (user_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT chk_vcomp_awarded CHECK (awarded_amount IS NULL OR awarded_amount >= 0),
    CONSTRAINT chk_vcomp_received CHECK (received_amount IS NULL OR received_amount >= 0),
    CONSTRAINT chk_vcomp_application_date CHECK (
        application_date IS NULL OR application_date >= '1900-01-01'
    )
) ENGINE = InnoDB;
