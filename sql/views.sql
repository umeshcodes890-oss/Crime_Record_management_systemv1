-- =====================================================================
-- Reporting views
-- =====================================================================

-- One row per case with everything the list and detail screens need.
CREATE OR REPLACE VIEW v_case_overview AS
SELECT
    c.case_id,
    c.case_no,
    c.category,
    c.offence_type,
    c.status,
    c.occurrence_datetime,
    c.reporting_datetime,
    c.closed_datetime,
    c.place_of_occurrence,
    c.description,
    c.summary,
    c.offence_count,
    s.station_id,
    s.name            AS station_name,
    s.district,
    o.officer_id,
    o.name            AS investigating_officer,
    o.badge_no,
    u.username        AS filed_by,
    u.full_name       AS filed_by_name,
    (SELECT COUNT(*) FROM suspects   su WHERE su.case_id = c.case_id)  AS suspect_count,
    (SELECT COUNT(*) FROM victims    v  WHERE v.case_id  = c.case_id)  AS victim_count,
    (SELECT COUNT(*) FROM witnesses  w  WHERE w.case_id  = c.case_id)  AS witness_count,
    (SELECT COUNT(*) FROM evidence   e  WHERE e.case_id  = c.case_id)  AS evidence_count,
    (SELECT COUNT(*) FROM arrests    a  WHERE a.case_id  = c.case_id)  AS arrest_count,
    (SELECT COUNT(*) FROM convictions cv WHERE cv.case_id = c.case_id) AS conviction_count,
    DATEDIFF(NOW(), c.occurrence_datetime) AS age_days,
    CASE WHEN c.closed_datetime IS NOT NULL
         THEN DATEDIFF(c.closed_datetime, c.occurrence_datetime) END AS days_to_close,
    (SELECT GROUP_CONCAT(CONCAT(sec.section_no, ' ', sec.offence_name) SEPARATOR ' | ')
       FROM case_offences co
       JOIN offence_sections sec ON sec.section_id = co.section_id
      WHERE co.case_id = c.case_id) AS offence_summary
FROM crime_cases c
JOIN police_stations s ON s.station_id = c.station_id
JOIN officers         o ON o.officer_id = c.investigating_officer_id
JOIN users            u ON u.user_id    = c.filed_by_user_id;

-- Per-officer caseload, used by the Officers screen and the workload chart.
CREATE OR REPLACE VIEW v_officer_workload AS
SELECT
    o.officer_id,
    o.name,
    o.badge_no,
    o.rank,
    o.is_active,
    ps.station_id,
    ps.name       AS station_name,
    ps.district,
    COUNT(c.case_id) AS total_cases,
    SUM(CASE WHEN c.status IN ('registered','under_investigation','charges_filed','trial')
             THEN 1 ELSE 0 END) AS open_cases,
    SUM(CASE WHEN c.status = 'closed_convicted'   THEN 1 ELSE 0 END) AS convicted_cases,
    SUM(CASE WHEN c.status = 'closed_acquitted'   THEN 1 ELSE 0 END) AS acquitted_cases,
    SUM(CASE WHEN c.status = 'closed_untraceable' THEN 1 ELSE 0 END) AS untraceable_cases,
    ROUND(AVG(CASE WHEN c.closed_datetime IS NOT NULL
                    THEN DATEDIFF(c.closed_datetime, c.occurrence_datetime) END), 1)
        AS avg_days_to_close
FROM officers o
JOIN police_stations ps ON ps.station_id = o.station_id
LEFT JOIN crime_cases c ON c.investigating_officer_id = o.officer_id
GROUP BY o.officer_id, o.name, o.badge_no, o.rank, o.is_active,
         ps.station_id, ps.name, ps.district;

-- Per-station performance including a clearance rate.
CREATE OR REPLACE VIEW v_station_statistics AS
SELECT
    s.station_id,
    s.name  AS station_name,
    s.district,
    COUNT(c.case_id) AS total_cases,
    SUM(CASE WHEN c.status IN ('registered','under_investigation','charges_filed','trial')
             THEN 1 ELSE 0 END) AS open_cases,
    SUM(CASE WHEN c.status = 'closed_convicted'   THEN 1 ELSE 0 END) AS convicted_cases,
    SUM(CASE WHEN c.status = 'closed_acquitted'   THEN 1 ELSE 0 END) AS acquitted_cases,
    SUM(CASE WHEN c.status = 'closed_untraceable' THEN 1 ELSE 0 END) AS untraceable_cases,
    ROUND(100.0 * SUM(CASE WHEN c.status = 'closed_convicted' THEN 1 ELSE 0 END)
          / NULLIF(SUM(CASE WHEN c.status LIKE 'closed%' THEN 1 ELSE 0 END), 0), 1)
        AS clearance_rate
FROM police_stations s
LEFT JOIN crime_cases c ON c.station_id = s.station_id
GROUP BY s.station_id, s.name, s.district;

-- Which offences are being charged, and how often.
CREATE OR REPLACE VIEW v_offence_statistics AS
SELECT
    sec.section_id,
    sec.law_code,
    sec.section_no,
    sec.offence_name,
    sec.category,
    sec.severity,
    COUNT(co.case_id) AS case_count,
    COUNT(DISTINCT co.case_id) AS distinct_case_count
FROM offence_sections sec
LEFT JOIN case_offences co ON co.section_id = sec.section_id
GROUP BY sec.section_id, sec.law_code, sec.section_no, sec.offence_name,
         sec.category, sec.severity;

-- Monthly caseload for the trend chart.
CREATE OR REPLACE VIEW v_monthly_caseload AS
SELECT
    DATE_FORMAT(occurrence_datetime, '%Y-%m') AS month,
    COUNT(*) AS cases_registered,
    SUM(CASE WHEN status LIKE 'closed%' THEN 1 ELSE 0 END) AS cases_closed,
    SUM(CASE WHEN status = 'closed_convicted' THEN 1 ELSE 0 END) AS cases_convicted
FROM crime_cases
GROUP BY DATE_FORMAT(occurrence_datetime, '%Y-%m');

-- Suspect roll-up for the suspects screen and the repeat-offender check.
CREATE OR REPLACE VIEW v_suspect_summary AS
SELECT
    su.suspect_id,
    su.name,
    su.gender,
    su.status,
    su.phone,
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
JOIN crime_cases c ON c.case_id = su.case_id;

-- Hearings that are due, used by the dashboard.
CREATE OR REPLACE VIEW v_upcoming_hearings AS
SELECT
    p.proceeding_id,
    p.case_id,
    c.case_no,
    c.status AS case_status,
    s.name   AS station_name,
    p.court_name,
    p.hearing_datetime,
    p.next_hearing_datetime,
    p.stage,
    p.judge_name,
    DATEDIFF(p.next_hearing_datetime, NOW()) AS days_until
FROM court_proceedings p
JOIN crime_cases c     ON c.case_id = p.case_id
JOIN police_stations s ON s.station_id = c.station_id
WHERE p.next_hearing_datetime IS NOT NULL
  AND c.status NOT LIKE 'closed%'
ORDER BY p.next_hearing_datetime;
