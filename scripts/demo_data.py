"""Fill the database with a demo caseload.

    py scripts\\demo_data.py          seed the demo records
    py scripts\\demo_data.py --clear  remove every operational record

Reference data (stations, officers, offence sections) is left alone; the
script only touches cases and the records filed under them.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.connection import Database  # noqa: E402
from app.db.repositories import Repositories  # noqa: E402

USER_ID = 1

# -- the caseload -------------------------------------------------------
# (occurrence, category, offence_type, station, place, sections, path, verdict)
CASES = [
    ("2026-01-08 21:40:00", "theft", "House burglary", 1, "14 Nehru Street, Secunderabad",
     ["380"], ["under_investigation", "charges_filed", "trial"], "guilty"),
    ("2026-01-22 11:15:00", "fraud", "Cheating by personation", 2, "Booth No. 4, Secunderabad",
     ["419"], ["under_investigation", "charges_filed", "trial"], "guilty"),
    ("2026-02-14 19:05:00", "assault", "Voluntarily causing hurt", 3, "Bus stop, Kukatpally",
     ["323"], ["under_investigation", "charges_filed", "trial"], None),
    ("2026-03-05 16:30:00", "cyber", "Identity theft", 6, "Online banking, Begumpet",
     ["419"], ["under_investigation"], None),
    ("2026-04-11 23:55:00", "homicide", "Murder", 5, "Open land behind LB Nagar",
     ["302"], ["under_investigation", "charges_filed", "trial"], "guilty"),
    ("2026-05-02 13:20:00", "missing_person", "Kidnapping", 8, "Gachibowli, Hyderabad",
     ["359"], ["under_investigation", "charges_filed"], None),
    ("2026-06-19 22:10:00", "theft", "Motor vehicle theft", 7, "Nizampet parking area",
     ["379"], ["under_investigation", "charges_filed", "closed_untraceable"], None),
    ("2026-07-07 09:45:00", "drugs", "Possession of narcotic substances", 2, "Old city, Hyderabad",
     ["379"], ["under_investigation"], None),
    ("2026-08-23 02:15:00", "arson", "Arson", 4, "Warehouse, Chanchalguda",
     ["452"], ["under_investigation", "charges_filed"], None),
    ("2026-09-15 18:00:00", "fraud", "Forgery of a valuable security", 1, "Bank, Banjara Hills",
     ["419"], ["under_investigation", "charges_filed", "trial"], None),
    ("2026-10-09 20:25:00", "assault", "Voluntarily causing grievous hurt", 3, "Amberpet, Hyderabad",
     ["325"], ["under_investigation", "charges_filed", "trial"], "acquitted"),
    ("2026-10-28 17:35:00", "theft", "Snatching a mobile phone", 4, "Begumpet bus stop",
     ["379"], [], None),
]

SUSPECTS = [
    ("Ramesh Yadav", "Ramu", "male", "1994-03-11", "wanted"),
    ("Sunil Kamble", None, "male", "1988-07-24", "arrested"),
    ("Prakash Reddy", "P.J.", "male", "1991-12-02", "in_custody"),
    ("Anil Joseph", None, "male", "1996-05-19", "wanted"),
    ("Faheem Sheikh", "Fame", "male", "1993-09-08", "convicted"),
    ("Vikram Naidu", None, "male", "1985-01-30", "in_custody"),
    ("Deepak Rao", "Rocky", "male", "1999-11-13", "arrested"),
    ("Imran Ali", None, "male", "1992-02-26", "wanted"),
    ("Suresh Naik", None, "male", "1987-06-14", "wanted"),
    ("Mahesh Goud", None, "male", "1990-04-21", "wanted"),
    ("Arun Kumar", "Bunny", "male", "1995-08-05", "acquitted"),
    ("Jagan Rao", None, "male", "1983-10-17", "wanted"),
]

VICTIMS = [
    ("Lakshmi Devi", 54, "female", "grievous"),
    ("Ravi Teja", 41, "male", "none"),
    ("Sridevi", 33, "female", "minor"),
    ("Nagaraju", 62, "male", "none"),
    ("Kiran Kumar", 28, "male", "fatal"),
    ("Anitha Reddy", 26, "female", "minor"),
    ("Satish Babu", 47, "male", "none"),
    ("Pavithra", 31, "female", "none"),
]

WITNESSES = [
    ("Ravi Shankar", "9848012345", True),
    ("Padma Jyothi", "9848077889", True),
    ("Mohan Das", "9848033445", False),
    ("Surekha Rani", "9848099887", True),
]

EVIDENCE = [
    ("physical", "Recovered crowbar with traces of blood", "Almirah 4, Rack B"),
    ("documentary", "Original property deed", "Evidence bag 18"),
    ("digital", "Mobile phone with call records", "Cyber vault 2"),
    ("documentary", "Bank passbook and statements", "Almirah 4, Rack B"),
    ("physical", "Blood stained knife", "Malkajgiri morgue"),
    ("testimonial", "Statement of the reporting witness", "File room"),
    ("forensic", "Finger print card", "Forensic lab, Saifabad"),
]

COURTS = [
    "City Civil Court, Secunderabad",
    "Sessions Court, Hyderabad",
    "Magistrate Court, Kukatpally",
    "Juvenile Justice Court, Hyderabad",
]

JUDGES = [
    "Justice R. Venkateswarlu",
    "Justice S. Padmavathi",
    "Justice M. Prasad",
    "Justice A. Fatima",
]


def admin_actor(db: Database) -> dict:
    repos = Repositories(db)
    row = next((u for u in repos.users.list_all() if u["role"] == "admin"), None)
    if row is None:
        raise SystemExit("No admin account found. Run py scripts\\setup_db.py first.")
    return {"user_id": row["user_id"], "username": row["username"], "role": "admin"}


def clear(db: Database) -> None:
    db.execute("DELETE FROM crime_cases")
    db.execute("DELETE FROM users WHERE username <> 'admin'")
    print("Operational records removed.")


def seed(db: Database) -> None:
    actor = admin_actor(db)
    repos = Repositories(db, actor)
    user_id = actor["user_id"]

    stations = repos.stations.list_all()
    officers = repos.officers.options()
    sections = {s["section_no"]: s["section_id"] for s in repos.offences.list_all()}

    station_ids = [s["station_id"] for s in stations]
    officer_by_station = {}
    for officer in officers:
        officer_by_station.setdefault(officer["station_id"], officer)

    def station_for(index: int) -> int:
        return station_ids[index % len(station_ids)]

    for index, (when, category, offence_type, station_index, place,
                 section_nos, path, verdict) in enumerate(CASES):
        station = station_for(station_index - 1)
        officer = officer_by_station.get(station, officers[0])

        result = repos.cases.file_case(
            station_id=station,
            officer_id=officer["officer_id"],
            user_id=user_id,
            category=category,
            offence_type=offence_type,
            occurrence_datetime=when,
            reporting_datetime=when,
            place_of_occurrence=place,
            description=f"{offence_type} reported at {place}. Investigating officer "
                        f"{officer['name']}.",
            section_ids=[sections[no] for no in section_nos if no in sections],
        )
        case_id = result["case_id"]

        for status in path:
            repos.cases.update_status(case_id, status, user_id,
                                       f"Moved to {status.replace('_', ' ')}")

        suspect_id = None
        if index < len(SUSPECTS):
            name, alias, gender, dob, _status = SUSPECTS[index]
            suspect_id = repos.suspects.create(
                case_id, name, alias=alias, date_of_birth=dob, gender=gender,
                address=f"{place}, Hyderabad", phone=f"98480{index:05d}",
                identifying_marks="Scarring on the right forearm",
                status="wanted",
            )

        if index < len(VICTIMS):
            name, age, gender, injury = VICTIMS[index]
            repos.victims.create(
                case_id, name, age=age, gender=gender,
                phone=f"98490{index:05d}", address=f"{place}, Hyderabad",
                injury_level=injury,
                statement=f"The complainant {name} gave a written statement.",
            )

        witness = WITNESSES[index % len(WITNESSES)]
        repos.witnesses.create(
            case_id, witness[0], phone=witness[1], address=f"{place}, Hyderabad",
            statement="Witnessed the incident and confirmed the sequence of events.",
            is_reliable=witness[2],
        )

        kind, description, storage = EVIDENCE[index % len(EVIDENCE)]
        repos.evidence.create(
            case_id, kind, description, officer["officer_id"], when,
            seized_under=f"Section {section_nos[0]}",
            storage_location=storage,
            chain_of_custody_datetime=when,
        )

        if suspect_id is not None and len(path) >= 2:
            repos.arrests.record(
                case_id, suspect_id, officer["officer_id"], when, place,
                remand_status="judicial_remand" if index % 2 == 0 else "bail",
                bail_amount=5000.0 if index % 2 else None,
            )

        if len(path) >= 2:
            repos.proceedings.create(
                case_id, COURTS[index % len(COURTS)], when,
                stage="first_hearing", judge_name=JUDGES[index % len(JUDGES)],
                next_hearing_datetime=when, remarks="First hearing listed.",
            )
            repos.proceedings.create(
                case_id, COURTS[index % len(COURTS)], when,
                stage="verdict", judge_name=JUDGES[index % len(JUDGES)],
                remarks="Arguments concluded.",
            )

        if verdict and suspect_id is not None:
            repos.convictions.record(
                case_id, suspect_id, user_id, COURTS[index % len(COURTS)],
                verdict,
                sentence_type="imprisonment" if verdict == "guilty" else "none",
                imprisonment_years=3.0 + (index % 4) if verdict == "guilty" else None,
                fine_amount=10000.0 if verdict == "guilty" else None,
                sentence_start=when, release_expected=when,
            )

    print(f"Seeded {len(CASES)} cases.")


def main() -> int:
    db = Database()
    try:
        if "--clear" in sys.argv:
            clear(db)
        else:
            seed(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
