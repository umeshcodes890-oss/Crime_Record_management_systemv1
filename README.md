# Crime Record Management System

A MySQL-backed desktop application for managing crime records: FIR filing, investigation
tracking, suspects, victims, witnesses, evidence, arrests, court proceedings, convictions,
and an analytics dashboard.

**Stack:** Python 3.12 · CustomTkinter (desktop UI) · MySQL 8.0 · mysql-connector-python

---

## Setup

### 1. Install dependencies

```cmd
cd /d D:\CrimeRecordManagementSystem
python -m pip install -r requirements.txt
```

> Use `python`, not `py` — on this machine `py` points at Python 3.14 while the
> project packages are installed under Python 3.12.

### 2. Configure the database connection

```cmd
copy config.ini.template config.ini
notepad config.ini
```

Put your MySQL root password in the `password` field. `config.ini` is git-ignored, so
the password never reaches the repository.

### 3. Create the database

```cmd
python scripts\setup_db.py
```

This creates the `crime_records` database, all 15 tables, 7 views, the stored procedures,
triggers and indexes, and loads the reference data: 8 police stations, 8 officers and
33 offence sections from the BNS and IPC.

### 4. Run

```cmd
python main.py
```

Default login: `admin` / `admin123` (change it from the Users screen after signing in).

---

## Demo data

The reference data alone leaves every register empty, so there is a script that seeds a
sample caseload — 12 cases spread across 2026, with suspects, victims, witnesses,
evidence, arrests, court hearings and convictions:

```cmd
python scripts\demo_data.py
```

To wipe the operational records and start again (the reference data and the admin
account are kept):

```cmd
python scripts\demo_data.py --clear
```

---

## Verifying the install

```cmd
python scripts\selftest.py
```

Runs 58 checks against a live MySQL server: schema and permissions, the role matrix,
the case status machine, and the triggers that maintain suspect status, the offence
counter and the status history.

---

## Roles

| Screen | admin | officer | viewer |
| --- | --- | --- | --- |
| Dashboard, cases, suspects, victims, witnesses, evidence, court | yes | yes | yes |
| Stations, officers, offence sections, users | yes | no | no |
| Create / edit records | yes | yes | no |
| Delete records | yes | yes | no |
| Delete master data and user accounts | yes | no | no |

Permissions are enforced in the repository layer, not in the UI, so a restricted role
cannot write even if it reaches the screen.

---

## Documentation

- Design spec: [`docs/superpowers/specs/2026-11-02-crime-record-management-system-design.md`](docs/superpowers/specs/2026-11-02-crime-record-management-system-design.md)
