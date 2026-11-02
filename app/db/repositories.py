"""A single place to reach every repository."""

from __future__ import annotations

from app.db.auth import UserRepository
from app.db.cases import CaseRepository
from app.db.connection import Database
from app.db.evidence import EvidenceRepository
from app.db.legal import ArrestRepository, ConvictionRepository, ProceedingRepository
from app.db.masters import OfficerRepository, OffenceRepository, StationRepository
from app.db.persons import SuspectRepository, VictimRepository, WitnessRepository
from app.db.reports import ReportRepository


class Repositories:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.stations = StationRepository(db)
        self.officers = OfficerRepository(db)
        self.offences = OffenceRepository(db)
        self.cases = CaseRepository(db)
        self.suspects = SuspectRepository(db)
        self.victims = VictimRepository(db)
        self.witnesses = WitnessRepository(db)
        self.evidence = EvidenceRepository(db)
        self.arrests = ArrestRepository(db)
        self.proceedings = ProceedingRepository(db)
        self.convictions = ConvictionRepository(db)
        self.reports = ReportRepository(db)
