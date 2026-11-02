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
    """Every repository, bound to the signed-in user.

    The actor is what makes the role check work: each repository
    re-checks that the signed-in user may perform the write before it
    reaches MySQL.
    """

    def __init__(self, db: Database, actor: dict | None = None) -> None:
        self.db = db
        self.actor = actor
        self.users = UserRepository(db, actor)
        self.stations = StationRepository(db, actor)
        self.officers = OfficerRepository(db, actor)
        self.offences = OffenceRepository(db, actor)
        self.cases = CaseRepository(db, actor)
        self.suspects = SuspectRepository(db, actor)
        self.victims = VictimRepository(db, actor)
        self.witnesses = WitnessRepository(db, actor)
        self.evidence = EvidenceRepository(db, actor)
        self.arrests = ArrestRepository(db, actor)
        self.proceedings = ProceedingRepository(db, actor)
        self.convictions = ConvictionRepository(db, actor)
        self.reports = ReportRepository(db, actor)
