-- =====================================================================
-- Reference data
-- Stations, one officer per station, and the law library.
-- The offence rows ship with the Indian Penal Code (IPC, 1860)
-- numbering, which is stable and verifiable. BNS 2023 rows can be
-- added from the Offence Sections screen - the schema supports both
-- law codes side by side.
-- =====================================================================

INSERT IGNORE INTO police_stations (name, district, address, phone) VALUES
    ('Central Police Station',        'Central', 'Church Road, Central District',      '040-27001101'),
    ('North Police Station',           'North',   'Begum Bazaar, North District',        '040-27002202'),
    ('South Police Station',           'South',   'Kukatpally, South District',          '040-27003303'),
    ('East Police Station',            'East',    'Nachapur, East District',             '040-27004404'),
    ('West Police Station',            'West',    'Balanagar, West District',             '040-27005505'),
    ('Cyber Crime Police Station',     'Central', 'IT Hub, Raidurgam, Central District',  '040-27006606'),
    ('Traffic Police Station',         'Central', 'Sardar Patel Road, Central District', '040-27007707'),
    ('Women & Child Protection Cell',  'South',   'Madhapur, South District',            '040-27008808');

-- One officer per station so the officer pickers and the station in-charge
-- field have something to offer from the first run.
INSERT IGNORE INTO officers (badge_no, name, `rank`, station_id, phone, join_date)
SELECT t.badge_no, t.name, t.officer_rank, s.station_id, t.phone, '2020-06-01'
FROM (
    SELECT 'HYD-001' AS badge_no, 'Anil Verma'   AS name, 'Sub-Inspector' AS officer_rank,
           '040-27001101' AS phone, 'Central Police Station' AS station
    UNION ALL SELECT 'HYD-002', 'Bhavna Iyer',   'Inspector',     '040-27002202', 'North Police Station'
    UNION ALL SELECT 'HYD-003', 'Ravi Shankar', 'Sub-Inspector', '040-27003303', 'South Police Station'
    UNION ALL SELECT 'HYD-004', 'Meera Nair',    'Inspector',     '040-27004404', 'East Police Station'
    UNION ALL SELECT 'HYD-005', 'Suresh Kumar',  'Constable',     '040-27005505', 'West Police Station'
    UNION ALL SELECT 'HYD-006', 'Nisha Menon',   'Inspector',     '040-27006606', 'Cyber Crime Police Station'
    UNION ALL SELECT 'HYD-007', 'Prakash Rao',   'Sub-Inspector', '040-27007707', 'Traffic Police Station'
    UNION ALL SELECT 'HYD-008', 'Asha Qureshi',  'Inspector',     '040-27008808', 'Women & Child Protection Cell'
) t
JOIN police_stations s ON s.name = t.station;

INSERT IGNORE INTO offence_sections
    (law_code, section_no, offence_name, category, severity,
     min_imprisonment_yrs, max_imprisonment_yrs, fine_cap, description) VALUES
-- Offences against the human body
('IPC', '302', 'Punishment for murder',                        'cognizable',    'grave',  0.0, 25.0,  50000.00, 'Imprisonment for life or death, and fine.'),
('IPC', '304', 'Culpable homicide not amounting to murder',    'cognizable',    'high',   0.0, 10.0,  10000.00, 'Causing death by an act done with the intention of causing death or grievous hurt.'),
('IPC', '307', 'Attempt to murder',                            'cognizable',    'grave',  7.0, 25.0,  50000.00, 'Imprisonment up to ten years, or life imprisonment, and fine.'),
('IPC', '323', 'Voluntarily causing hurt',                    'non_cognizable','medium', 0.0,  1.0,   1000.00, 'Simple hurt; imprisonment up to one year or fine.'),
('IPC', '324', 'Voluntarily causing hurt by dangerous weapons or means', 'cognizable', 'high', 0.0, 7.0, 10000.00, 'Hurt caused with a dangerous weapon or means.'),
('IPC', '325', 'Voluntarily causing grievous hurt',           'cognizable',    'high',   0.0,  7.0,  10000.00, 'Grievous hurt; imprisonment up to seven years and fine.'),
('IPC', '326', 'Voluntarily causing grievous hurt by dangerous weapons or means', 'cognizable', 'grave', 0.0, 10.0, 20000.00, 'Grievous hurt caused with a dangerous weapon or means.'),
('IPC', '336', 'Causing death by negligent act not amounting to culpable homicide', 'non_cognizable', 'medium', 0.0, 2.0, 2000.00, 'Causing death by a negligent act.'),
('IPC', '337', 'Causing death by negligent act',              'non_cognizable','high',   0.0,  7.0,  10000.00, 'Causing death of a person by a negligent act not amounting to culpable homicide.'),
('IPC', '340', 'Wrongful restraint',                          'non_cognizable','medium', 0.0,  1.0,   1000.00, 'Wrongfully restraining any person.'),
('IPC', '341', 'Punishment for wrongful confinement',         'non_cognizable','medium', 0.0,  1.0,   1000.00, 'Imprisonment up to three months or fine.'),
('IPC', '342', 'Punishment for wrongful confinement',         'cognizable',    'high',   0.0,  3.0,   5000.00, 'Imprisonment up to three years and fine.'),
('IPC', '359', 'Kidnapping',                                  'cognizable',    'high',   0.0,  7.0,  10000.00, 'Kidnapping or abduction of a person.'),
('IPC', '376', 'Rape',                                        'cognizable',    'grave',  0.0, 25.0,  50000.00, 'Imprisonment up to twenty years, or life imprisonment, and fine.'),
('IPC', '379', 'Theft',                                       'non_cognizable','medium', 0.0,  3.0,   5000.00, 'Dishonestly taking any property out of the possession of another.'),
('IPC', '380', 'Theft in dwelling house',                     'non_cognizable','medium', 0.0,  7.0,  10000.00, 'Theft in a dwelling house.'),
('IPC', '390', 'Robbery',                                     'cognizable',    'high',   0.0, 14.0,  20000.00, 'Robbery.'),
('IPC', '392', 'Punishment for robbery',                      'cognizable',    'grave',  0.0, 25.0,  50000.00, 'Imprisonment up to fourteen years, or life imprisonment, and fine.'),
('IPC', '403', 'Dishonest misappropriation of property',      'non_cognizable','medium', 0.0,  2.0,   2000.00, 'Dishonestly misappropriating movable property.'),
('IPC', '415', 'Cheating',                                    'non_cognizable','medium', 0.0,  1.0,   1000.00, 'Cheating and thereby dishonestly inducing to deliver property.'),
('IPC', '419', 'Cheating by personation',                     'cognizable',    'high',   0.0,  3.0,   5000.00, 'Cheating by pretending to be another person.'),
('IPC', '420', 'Cheating and dishonestly inducing to deliver property', 'cognizable', 'high', 0.0, 7.0, 10000.00, 'Cheating a person and thereby inducing him to deliver property.'),
('IPC', '441', 'Criminal trespass',                           'non_cognizable','low',    0.0,  1.0,   1000.00, 'Entering or remaining in a property without permission.'),
('IPC', '445', 'House-trespass',                              'non_cognizable','low',    0.0,  1.0,   1000.00, 'House-trespass.'),
('IPC', '447', 'Punishment for criminal trespass',            'non_cognizable','medium', 0.0,  3.0,   5000.00, 'Imprisonment up to three months or fine, or both.'),
('IPC', '452', 'House-trespass after preparation for hurt, assault or wrongful restraint', 'cognizable', 'high', 0.0, 7.0, 10000.00, 'House-trespass with preparation for hurt or assault.'),
('IPC', '494', 'Bigamy',                                      'non_cognizable','medium', 0.0,  7.0,  10000.00, 'Marrying a second husband or wife while the first marriage subsists.'),
('IPC', '498A', 'Cruelty by husband or relatives',            'cognizable',    'high',   0.0,  3.0,   5000.00, 'Cruelty by husband or relatives.'),
('IPC', '503', 'Criminal intimidation',                       'cognizable',    'medium', 0.0,  2.0,   2000.00, 'Threatening a person with injury.'),
('IPC', '506', 'Punishment for criminal intimidation',       'cognizable',    'high',   0.0,  2.0,   2000.00, 'Imprisonment up to two years or fine, or both.'),
('IPC', '509', 'Word, gesture or act intended to insult the modesty of a woman', 'cognizable', 'medium', 0.0, 1.0, 1000.00, 'Insulting the modesty of a woman.'),
('IPC', '511', 'Preparing to commit offences punishable with imprisonment', 'cognizable', 'low', 0.0, 3.0, 5000.00, 'Preparing to commit an offence punishable with imprisonment.'),
('IPC', '108', 'Abetment of an offence',                      'cognizable',    'grave',  0.0, 25.0,  50000.00, 'Abetting the commission of an offence.');
