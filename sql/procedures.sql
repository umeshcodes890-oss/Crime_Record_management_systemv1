-- =====================================================================
-- Stored procedures - the business rules live here, not in Python
-- =====================================================================

DELIMITER $$

-- ---------------------------------------------------------------------
-- sp_file_case : register a new case with its offence sections
-- Inserts the case, links the sections and returns the generated case_no.
-- The case_no is assigned by trg_cases_before_insert.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_file_case $$
CREATE PROCEDURE sp_file_case(
    IN  p_station_id            INT,
    IN  p_officer_id            INT,
    IN  p_user_id               INT,
    IN  p_category              VARCHAR(60),
    IN  p_offence_type          VARCHAR(120),
    IN  p_occurrence_datetime   DATETIME,
    IN  p_reporting_datetime    DATETIME,
    IN  p_place_of_occurrence  VARCHAR(255),
    IN  p_description           TEXT,
    IN  p_section_ids_json      JSON
)
proc: BEGIN
    DECLARE v_case_id INT DEFAULT NULL;
    DECLARE v_case_no VARCHAR(25) DEFAULT NULL;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    INSERT INTO crime_cases (
        station_id, investigating_officer_id, filed_by_user_id, category,
        offence_type, occurrence_datetime, reporting_datetime,
        place_of_occurrence, description, status
    ) VALUES (
        p_station_id, p_officer_id, p_user_id, p_category,
        p_offence_type, p_occurrence_datetime, p_reporting_datetime,
        p_place_of_occurrence, p_description, 'registered'
    );

    SET v_case_id = LAST_INSERT_ID();

    IF p_section_ids_json IS NOT NULL
       AND JSON_LENGTH(p_section_ids_json) > 0 THEN
        INSERT INTO case_offences (case_id, section_id, accused_role)
        SELECT v_case_id, jt.section_id, 'primary'
        FROM JSON_TABLE(p_section_ids_json, '$[*]'
               COLUMNS (section_id INT PATH '$')) AS jt
        WHERE jt.section_id IS NOT NULL;
    END IF;

    COMMIT;

    SELECT case_no INTO v_case_no FROM crime_cases WHERE case_id = v_case_id;

    SELECT v_case_id AS case_id, v_case_no AS case_no;
END $$

-- ---------------------------------------------------------------------
-- sp_update_case_status : move a case along the investigation lifecycle
-- Status ranks: registered 1, under_investigation 2, charges_filed 3,
-- trial 4, closed_* 5. Forward moves are allowed; backward moves and
-- changes after closure are refused.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_update_case_status $$
CREATE PROCEDURE sp_update_case_status(
    IN p_case_id    INT,
    IN p_new_status VARCHAR(30),
    IN p_user_id    INT,
    IN p_remark     VARCHAR(255)
)
proc: BEGIN
    DECLARE v_old_status VARCHAR(30);
    DECLARE v_old_rank   INT;
    DECLARE v_new_rank   INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SELECT status INTO v_old_status FROM crime_cases WHERE case_id = p_case_id FOR UPDATE;

    IF v_old_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Case does not exist';
    END IF;

    SET v_old_rank = CASE v_old_status
        WHEN 'registered'          THEN 1
        WHEN 'under_investigation' THEN 2
        WHEN 'charges_filed'       THEN 3
        WHEN 'trial'               THEN 4
        ELSE 5 END;

    SET v_new_rank = CASE p_new_status
        WHEN 'registered'          THEN 1
        WHEN 'under_investigation' THEN 2
        WHEN 'charges_filed'       THEN 3
        WHEN 'trial'               THEN 4
        WHEN 'closed_convicted'    THEN 5
        WHEN 'closed_acquitted'    THEN 5
        WHEN 'closed_untraceable'  THEN 5
        ELSE 0 END;

    IF v_new_rank = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unknown case status';
    END IF;

    IF v_old_rank = 5 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Case is already closed and cannot be reopened';
    END IF;

    IF v_new_rank <= v_old_rank THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'A case cannot move backwards in the investigation lifecycle';
    END IF;

    START TRANSACTION;

    -- The trigger reads @actor_user_id to attribute the history row.
    SET @actor_user_id = p_user_id;

    UPDATE crime_cases
       SET status = p_new_status,
           closed_datetime = CASE WHEN v_new_rank = 5 THEN NOW() ELSE closed_datetime END
     WHERE case_id = p_case_id;

    SET @actor_user_id = NULL;

    COMMIT;

    SELECT p_case_id AS case_id, p_new_status AS status;
END $$

-- ---------------------------------------------------------------------
-- sp_assign_officer : hand a case to another officer at the same station
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_assign_officer $$
CREATE PROCEDURE sp_assign_officer(
    IN p_case_id   INT,
    IN p_officer_id INT,
    IN p_user_id   INT
)
proc: BEGIN
    DECLARE v_case_station   INT;
    DECLARE v_officer_station INT;
    DECLARE v_active BOOLEAN;

    SELECT station_id INTO v_case_station
      FROM crime_cases WHERE case_id = p_case_id FOR UPDATE;

    IF v_case_station IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Case does not exist';
    END IF;

    SELECT station_id, is_active INTO v_officer_station, v_active
      FROM officers WHERE officer_id = p_officer_id;

    IF v_officer_station IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Officer does not exist';
    END IF;

    IF NOT v_active THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'That officer is no longer active';
    END IF;

    IF v_officer_station <> v_case_station THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Officer must be posted at the station handling this case';
    END IF;

    START TRANSACTION;

    SET @actor_user_id = p_user_id;

    UPDATE crime_cases
       SET investigating_officer_id = p_officer_id
     WHERE case_id = p_case_id;

    SET @actor_user_id = NULL;

    COMMIT;

    SELECT p_case_id AS case_id, p_officer_id AS investigating_officer_id;
END $$

-- ---------------------------------------------------------------------
-- sp_search_cases : multi-criteria case search
-- Any parameter left NULL is ignored.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_search_cases $$
CREATE PROCEDURE sp_search_cases(
    IN p_case_no    VARCHAR(50),
    IN p_station_id INT,
    IN p_officer_id INT,
    IN p_status     VARCHAR(30),
    IN p_category   VARCHAR(60),
    IN p_section_id INT,
    IN p_from_date  DATETIME,
    IN p_to_date    DATETIME,
    IN p_text       VARCHAR(120),
    IN p_limit      INT
)
proc: BEGIN
    SELECT *
    FROM v_case_overview v
    WHERE (p_case_no IS NULL OR v.case_no LIKE CONCAT('%', p_case_no, '%'))
      AND (p_station_id IS NULL OR v.station_id = p_station_id)
      AND (p_officer_id IS NULL OR v.officer_id = p_officer_id)
      AND (p_status IS NULL OR v.status = p_status)
      AND (p_category IS NULL OR v.category = p_category)
      AND (p_section_id IS NULL OR EXISTS (
              SELECT 1 FROM case_offences co
               WHERE co.case_id = v.case_id AND co.section_id = p_section_id))
      AND (p_from_date IS NULL OR v.occurrence_datetime >= p_from_date)
      AND (p_to_date IS NULL OR v.occurrence_datetime <= p_to_date)
      AND (p_text IS NULL OR p_text = ''
           OR v.place_of_occurrence LIKE CONCAT('%', p_text, '%')
           OR v.description        LIKE CONCAT('%', p_text, '%')
           OR v.offence_type       LIKE CONCAT('%', p_text, '%')
           OR v.offence_summary    LIKE CONCAT('%', p_text, '%'))
    ORDER BY v.occurrence_datetime DESC
    LIMIT CASE WHEN p_limit IS NULL OR p_limit <= 0 THEN 500 ELSE p_limit END;
END $$

-- ---------------------------------------------------------------------
-- sp_record_arrest : log an arrest and update the suspect's status
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_record_arrest $$
CREATE PROCEDURE sp_record_arrest(
    IN p_case_id     INT,
    IN p_suspect_id  INT,
    IN p_officer_id  INT,
    IN p_datetime    DATETIME,
    IN p_place       VARCHAR(255),
    IN p_remand      VARCHAR(30),
    IN p_bail_amount DECIMAL(12,2)
)
proc: BEGIN
    DECLARE v_arrest_id INT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;

    INSERT INTO arrests (
        case_id, suspect_id, arrested_by_officer_id, arrest_datetime,
        place_of_arrest, remand_status, bail_amount
    ) VALUES (
        p_case_id, p_suspect_id, p_officer_id, p_datetime,
        p_place, COALESCE(p_remand, 'not_remanded'), p_bail_amount
    );

    SET v_arrest_id = LAST_INSERT_ID();

    COMMIT;

    SELECT v_arrest_id AS arrest_id;
END $$

-- ---------------------------------------------------------------------
-- sp_record_conviction : log a court outcome
-- The triggers set the suspect's status; the case status is advanced
-- to its closed state through the same lifecycle rules as the UI.
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_record_conviction $$
CREATE PROCEDURE sp_record_conviction(
    IN p_case_id      INT,
    IN p_suspect_id   INT,
    IN p_user_id      INT,
    IN p_court_name   VARCHAR(160),
    IN p_verdict      VARCHAR(30),
    IN p_sentence_type VARCHAR(30),
    IN p_years        DECIMAL(4,1),
    IN p_fine         DECIMAL(12,2),
    IN p_sentence_start DATE,
    IN p_release_expected DATE
)
proc: BEGIN
    DECLARE v_conviction_id INT;
    DECLARE v_current_status VARCHAR(30);

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SELECT status INTO v_current_status FROM crime_cases WHERE case_id = p_case_id FOR UPDATE;

    IF v_current_status IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Case does not exist';
    END IF;

    START TRANSACTION;

    INSERT INTO convictions (
        case_id, suspect_id, court_name, verdict, sentence_type,
        imprisonment_years, fine_amount, sentence_start, release_expected
    ) VALUES (
        p_case_id, p_suspect_id, p_court_name, p_verdict,
        COALESCE(p_sentence_type, 'none'), p_years, p_fine,
        p_sentence_start, p_release_expected
    );

    SET v_conviction_id = LAST_INSERT_ID();

    IF v_current_status NOT LIKE 'closed%' THEN
        SET @actor_user_id = p_user_id;

        UPDATE crime_cases
           SET status = CASE WHEN p_verdict = 'guilty' THEN 'closed_convicted'
                             ELSE 'closed_acquitted' END,
               closed_datetime = NOW()
         WHERE case_id = p_case_id;

        SET @actor_user_id = NULL;
    END IF;

    COMMIT;

    SELECT v_conviction_id AS conviction_id;
END $$

-- ---------------------------------------------------------------------
-- sp_dashboard_summary : headline counters for the dashboard
-- ---------------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_dashboard_summary $$
CREATE PROCEDURE sp_dashboard_summary()
proc: BEGIN
    SELECT
        COUNT(*) AS total_cases,
        SUM(CASE WHEN status IN ('registered','under_investigation','charges_filed','trial')
                 THEN 1 ELSE 0 END) AS open_cases,
        SUM(CASE WHEN status = 'closed_convicted'   THEN 1 ELSE 0 END) AS convicted_cases,
        SUM(CASE WHEN status = 'closed_acquitted'   THEN 1 ELSE 0 END) AS acquitted_cases,
        SUM(CASE WHEN status = 'closed_untraceable' THEN 1 ELSE 0 END) AS untraceable_cases,
        SUM(CASE WHEN occurrence_datetime >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                 THEN 1 ELSE 0 END) AS cases_last_30_days,
        SUM(CASE WHEN closed_datetime >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                 THEN 1 ELSE 0 END) AS closed_last_30_days,
        ROUND(100.0 * SUM(CASE WHEN status = 'closed_convicted' THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN status LIKE 'closed%' THEN 1 ELSE 0 END), 0), 1)
            AS clearance_rate,
        ROUND(AVG(CASE WHEN closed_datetime IS NOT NULL
                        THEN DATEDIFF(closed_datetime, occurrence_datetime) END), 1)
            AS avg_days_to_close,
        (SELECT COUNT(*) FROM suspects WHERE status = 'wanted')      AS wanted_suspects,
        (SELECT COUNT(*) FROM suspects WHERE status IN ('arrested','in_custody'))
            AS custody_suspects,
        (SELECT COUNT(*) FROM users WHERE is_active = TRUE)          AS active_users
    FROM crime_cases;
END $$

DELIMITER ;
