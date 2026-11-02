-- =====================================================================
-- Triggers - automatic behaviour that belongs in the database
-- =====================================================================

DELIMITER $$

-- ---------------------------------------------------------------------
-- trg_cases_before_insert : assign a sequential, human-readable case_no
-- Format: CR/<year>/<4-digit sequence>, unique per year.
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_cases_before_insert $$
CREATE TRIGGER trg_cases_before_insert
BEFORE INSERT ON crime_cases
FOR EACH ROW
BEGIN
    DECLARE v_year INT;
    DECLARE v_seq  INT;

    SET v_year = YEAR(COALESCE(NEW.occurrence_datetime, NOW()));

    INSERT INTO case_sequences (yr, last_value)
    VALUES (v_year, 1)
    ON DUPLICATE KEY UPDATE last_value = last_value + 1;

    SELECT last_value INTO v_seq FROM case_sequences WHERE yr = v_year;

    SET NEW.case_no = CONCAT('CR/', v_year, '/', LPAD(v_seq, 4, '0'));
END $$

-- ---------------------------------------------------------------------
-- trg_cases_after_insert : write the opening status-history row
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_cases_after_insert $$
CREATE TRIGGER trg_cases_after_insert
AFTER INSERT ON crime_cases
FOR EACH ROW
BEGIN
    INSERT INTO case_status_history (
        case_id, old_status, new_status, changed_by_user_id, remark
    ) VALUES (
        NEW.case_id, NULL, NEW.status, NEW.filed_by_user_id, 'Case registered'
    );
END $$

-- ---------------------------------------------------------------------
-- trg_cases_after_status_update : append to the status history
-- @actor_user_id is set by sp_update_case_status so the change can be
-- attributed to the logged-in user rather than the filing officer.
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_cases_after_status_update $$
CREATE TRIGGER trg_cases_after_status_update
AFTER UPDATE ON crime_cases
FOR EACH ROW
BEGIN
    IF NOT (NEW.status <=> OLD.status) THEN
        INSERT INTO case_status_history (
            case_id, old_status, new_status, changed_by_user_id, remark
        ) VALUES (
            NEW.case_id,
            OLD.status,
            NEW.status,
            COALESCE(@actor_user_id, NEW.filed_by_user_id),
            CASE WHEN @actor_user_id IS NULL THEN 'Status updated by system process' ELSE NULL END
        );
    END IF;
END $$

-- ---------------------------------------------------------------------
-- trg_suspects_after_arrest : an arrest changes the suspect's status
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_suspects_after_arrest $$
CREATE TRIGGER trg_suspects_after_arrest
AFTER INSERT ON arrests
FOR EACH ROW
BEGIN
    UPDATE suspects
       SET status = CASE WHEN NEW.remand_status = 'bail' THEN 'bailed' ELSE 'arrested' END
     WHERE suspect_id = NEW.suspect_id;
END $$

-- ---------------------------------------------------------------------
-- trg_suspects_after_conviction : a verdict changes the suspect's status
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_suspects_after_conviction $$
CREATE TRIGGER trg_suspects_after_conviction
AFTER INSERT ON convictions
FOR EACH ROW
BEGIN
    UPDATE suspects
       SET status = CASE WHEN NEW.verdict = 'guilty' THEN 'convicted' ELSE 'acquitted' END
     WHERE suspect_id = NEW.suspect_id;
END $$

-- ---------------------------------------------------------------------
-- trg_case_offences_after_insert / _after_delete : keep the cached
-- offence count on crime_cases in step with the real rows.
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_case_offences_after_insert $$
CREATE TRIGGER trg_case_offences_after_insert
AFTER INSERT ON case_offences
FOR EACH ROW
BEGIN
    UPDATE crime_cases
       SET offence_count = offence_count + 1
     WHERE case_id = NEW.case_id;
END $$

DROP TRIGGER IF EXISTS trg_case_offences_after_delete $$
CREATE TRIGGER trg_case_offences_after_delete
AFTER DELETE ON case_offences
FOR EACH ROW
BEGIN
    UPDATE crime_cases
       SET offence_count = GREATEST(offence_count - 1, 0)
     WHERE case_id = OLD.case_id;
END $$

-- ---------------------------------------------------------------------
-- trg_evidence_after_insert : stamp chain of custody when it is missing
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_evidence_after_insert $$
CREATE TRIGGER trg_evidence_after_insert
AFTER INSERT ON evidence
FOR EACH ROW
BEGIN
    IF NEW.chain_of_custody_datetime IS NULL THEN
        UPDATE evidence
           SET chain_of_custody_datetime = NEW.collected_datetime
         WHERE evidence_id = NEW.evidence_id;
    END IF;
END $$

DELIMITER ;
