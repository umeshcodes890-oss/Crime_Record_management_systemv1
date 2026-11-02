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
py -m pip install -r requirements.txt
```

### 2. Configure the database connection

```cmd
copy config.ini.template config.ini
notepad config.ini
```

Put your MySQL root password in the `password` field.

### 3. Create the database

```cmd
py scripts\setup_db.py
```

This creates the `crime_records` database, all 13 tables, views, stored procedures,
triggers and indexes, and loads the reference data (police stations, offence sections,
the default admin account).

### 4. Run

```cmd
py main.py
```

Default login: `admin` / `admin123` (change it from the Users screen after signing in).

---

## Documentation

- Design spec: [`docs/superpowers/specs/2026-11-02-crime-record-management-system-design.md`](docs/superpowers/specs/2026-11-02-crime-record-management-system-design.md)
