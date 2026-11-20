"""Evidence: the register, its chain of custody, forensics and filed files.

Three things shape this module.

*   Every item carries a reference number the database issues, so the
    paper trail in a court room and the row on screen name the same thing.
*   The custody log is append-only. A mistake is corrected by adding
    another entry, never by rewriting who held the item, so the
    repository has no update or delete for it at all.
*   A movement of an item and the entry that records it are one unit of
    work. A log saying the laptop went to court while the item still
    reads "in store" is exactly the gap a defence advocate looks for.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.db import storage
from app.db.auth import Repository
from app.db.connection import Database, DatabaseError

# What the person recording an item may fill in. The reference number is
# issued by the database, and where the item stands in its life is moved
# by a custody entry or a forensic request rather than by editing the
# item, so none of those columns appear here.
EVIDENCE_PROFILE = frozenset({
    "item_name", "type", "description", "detailed_description",
    "evidence_category", "collection_location", "collection_method",
    "collected_by_officer_id", "collected_datetime", "seized_under",
    "storage_location", "condition", "packaging_type", "seal_number",
    "chain_of_custody_datetime", "digital_hash_sha256",
})

# Written only by the forensic methods, so an item and its examination
# requests cannot drift apart.
FORENSIC_SYNC = frozenset({"forensic_status", "laboratory_name", "examination_result"})

FORENSIC_REQUEST_FIELDS = frozenset({
    "laboratory_name", "examiner_name", "examination_type", "sent_datetime", "remarks",
})

FORENSIC_RESULT_FIELDS = frozenset({
    "examiner_name", "examination_type", "completed_datetime", "result_status",
    "result_summary", "report_path", "remarks",
})

CUSTODY_FIELDS = frozenset({
    "event_type", "from_officer_id", "to_officer_id", "purpose", "seal_intact",
    "occurred_at", "remarks",
})


class EvidenceRepository(Repository):
    """The evidence register, its custody chain, forensics and attachments."""

    def __init__(self, db: Database, actor: dict | None = None, *,
                 files_dir: str | Path | None = None,
                 allowed_extensions: frozenset[str] = storage.ALLOWED_EXTENSIONS,
                 max_file_bytes: int = storage.MAX_FILE_BYTES) -> None:
        super().__init__(db, actor)
        self.files_dir = storage.evidence_root(files_dir)
        self.allowed_extensions = allowed_extensions
        self.max_file_bytes = max_file_bytes

    # -- reading ------------------------------------------------------
    def for_case(self, case_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT e.*, o.name AS collected_by_name, c.case_no
            FROM evidence e
            JOIN officers o    ON o.officer_id = e.collected_by_officer_id
            JOIN crime_cases c ON c.case_id = e.case_id
            WHERE e.case_id = %s
            ORDER BY e.collected_datetime DESC
            """,
            (case_id,),
        )

    def list_all(self, evidence_type: str | None = None, search: str | None = None, *,
                 case_id: int | None = None, category: str | None = None,
                 status: str | None = None,
                 forensic_status: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if evidence_type:
            clauses.append("e.type = %s")
            params.append(evidence_type)
        for column, value in (("case_id", case_id), ("evidence_category", category),
                              ("evidence_status", status),
                              ("forensic_status", forensic_status)):
            if value:
                clauses.append(f"e.{column} = %s")
                params.append(value)
        if search:
            columns = ["e.item_name", "e.description", "e.detailed_description",
                       "e.evidence_ref", "e.storage_location", "e.seal_number",
                       "c.case_no"]
            clauses.append("(" + " OR ".join(f"{column} LIKE %s" for column in columns) + ")")
            params.extend([f"%{search}%"] * len(columns))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.db.query(
            f"""
            SELECT e.*, o.name AS collected_by_name, c.case_no, c.status AS case_status
            FROM evidence e
            JOIN officers o     ON o.officer_id = e.collected_by_officer_id
            JOIN crime_cases c  ON c.case_id = e.case_id
            {where}
            ORDER BY e.collected_datetime DESC
            """,
            params,
        )

    def get(self, evidence_id: int) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM evidence WHERE evidence_id = %s", (evidence_id,))

    def _require_item(self, evidence_id: int) -> dict:
        item = self.get(evidence_id)
        if item is None:
            raise DatabaseError("That evidence item no longer exists.")
        return item

    # -- the profile --------------------------------------------------
    def create(self, case_id: int, evidence_type: str, description: str,
               collected_by_officer_id: int, collected_datetime: str,
               seized_under: str | None = None, storage_location: str | None = None,
               chain_of_custody_datetime: str | None = None, *,
               item_name: str | None = None, **profile) -> int:
        """Record an item and open its chain of custody.

        The five positional arguments are what the register asked for
        before the module was extended; the rest are the detail the
        evidence room keeps.
        """
        values = dict(profile)
        if item_name is not None:
            values["item_name"] = item_name
        self.guard_fields(EVIDENCE_PROFILE, values, "evidence")

        fixed: dict[str, Any] = {
            "case_id": case_id,
            "type": evidence_type,
            "description": description.strip(),
            "collected_by_officer_id": collected_by_officer_id,
            "collected_datetime": collected_datetime,
        }
        for column, value in (("seized_under", seized_under),
                              ("storage_location", storage_location),
                              ("chain_of_custody_datetime", chain_of_custody_datetime)):
            if value is not None:
                fixed[column] = value

        user_id = self.user_id()
        with self.db.transaction():
            item_id = self.insert_row("evidence", {**fixed, **values})
            reference = self.scalar(
                "SELECT evidence_ref FROM evidence WHERE evidence_id = %s", (item_id,))
            self.insert_row("evidence_custody_log", {
                "evidence_id": item_id,
                "sequence_no": 1,
                "event_type": "collected",
                "to_officer_id": collected_by_officer_id,
                "purpose": "Recorded on seizure",
                "occurred_at": fixed.get("chain_of_custody_datetime") or collected_datetime,
                "recorded_by_user_id": user_id,
            })
            self.log("evidence", item_id, "create",
                     f"Recorded {reference or 'evidence'}: "
                     f"{values.get('item_name') or fixed['description']}",
                     case_id=case_id)
        return item_id

    def update(self, evidence_id: int, **fields) -> None:
        """Edit what was recorded about an item, and log the change."""
        case_id = self.parent_case("evidence", "evidence_id", evidence_id)
        self.edit_record("evidence", "evidence", "evidence_id", evidence_id,
                         EVIDENCE_PROFILE, fields, case_id=case_id)

    def delete(self, evidence_id: int) -> None:
        """Remove an item from the register.

        The attachment rows go with it, but the filed copies stay on disk:
        deleting a record is not the same as destroying evidence.
        """
        item = self._require_item(evidence_id)
        self.remove_record(
            "evidence", "evidence", "evidence_id", evidence_id,
            summary=f"Deleted {item['evidence_ref']}: "
                    f"{item['item_name'] or item['description']}",
            case_id=item["case_id"])

    # -- chain of custody ---------------------------------------------
    def custody_history(self, evidence_id: int) -> list[dict]:
        """Every link in the chain, oldest first."""
        return self.db.query(
            """
            SELECT l.*, held.name AS from_officer_name, given.name AS to_officer_name,
                   u.username AS recorded_by_username
            FROM evidence_custody_log l
            LEFT JOIN officers held  ON held.officer_id = l.from_officer_id
            LEFT JOIN officers given ON given.officer_id = l.to_officer_id
            LEFT JOIN users u        ON u.user_id = l.recorded_by_user_id
            WHERE l.evidence_id = %s
            ORDER BY l.sequence_no
            """,
            (evidence_id,),
        )

    def record_transfer(self, evidence_id: int, *, occurred_at: str,
                        event_type: str = "transferred", to_officer_id: int | None = None,
                        purpose: str | None = None, seal_intact: bool = True,
                        remarks: str | None = None,
                        status: str | None = None) -> int:
        """Append one link to the chain, and move the item if told to.

        The officer giving the item up is whoever holds the last entry, so
        the chain stays connected without the user retyping it.
        """
        item = self._require_item(evidence_id)
        holder = self.db.query_one(
            "SELECT to_officer_id FROM evidence_custody_log WHERE evidence_id = %s"
            " ORDER BY sequence_no DESC LIMIT 1",
            (evidence_id,),
        )
        from_officer_id = (holder or {}).get("to_officer_id")
        if from_officer_id is None:
            from_officer_id = item["collected_by_officer_id"]
        sequence_no = int(self.scalar(
            "SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM evidence_custody_log"
            " WHERE evidence_id = %s", (evidence_id,)))

        with self.db.transaction():
            custody_id = self.insert_row("evidence_custody_log", {
                "evidence_id": evidence_id,
                "sequence_no": sequence_no,
                "event_type": event_type,
                "from_officer_id": from_officer_id,
                "to_officer_id": to_officer_id,
                "purpose": purpose,
                "seal_intact": bool(seal_intact),
                "occurred_at": occurred_at,
                "remarks": remarks,
                "recorded_by_user_id": self.user_id(),
            })
            if status:
                self.update_row("evidence", "evidence_id", evidence_id,
                                {"evidence_status"}, {"evidence_status": status})
            self.log("evidence", evidence_id, "status_change",
                     f"{event_type}{' to ' + status if status else ''}"
                     f"{': ' + purpose if purpose else ''}",
                     case_id=item["case_id"])
        return custody_id

    # -- forensic examination -----------------------------------------
    def examinations(self, evidence_id: int) -> list[dict]:
        return self.db.query(
            """
            SELECT f.*, u.username AS recorded_by_username
            FROM forensic_examinations f
            LEFT JOIN users u ON u.user_id = f.recorded_by_user_id
            WHERE f.evidence_id = %s
            ORDER BY f.examination_id
            """,
            (evidence_id,),
        )

    def send_to_forensics(self, evidence_id: int, *, laboratory_name: str,
                          sent_datetime: str, examination_type: str | None = None,
                          request_no: str | None = None,
                          remarks: str | None = None) -> int:
        """Open an examination request, and log the item leaving for it."""
        item = self._require_item(evidence_id)
        already = int(self.scalar(
            "SELECT COUNT(*) FROM forensic_examinations WHERE evidence_id = %s",
            (evidence_id,)) or 0)
        reference = request_no or (
            f"FE/{str(sent_datetime)[:4]}/{evidence_id}-{already + 1:02d}")

        with self.db.transaction():
            examination_id = self.insert_row("forensic_examinations", {
                "evidence_id": evidence_id,
                "request_no": reference,
                "laboratory_name": laboratory_name,
                "examination_type": examination_type,
                "sent_datetime": sent_datetime,
                "remarks": remarks,
                "recorded_by_user_id": self.user_id(),
            })
            self.update_row("evidence", "evidence_id", evidence_id, FORENSIC_SYNC, {
                "forensic_status": "sent",
                "laboratory_name": laboratory_name,
            })
            self.record_transfer(
                evidence_id, occurred_at=sent_datetime, event_type="transferred",
                purpose=f"Forensic examination: {laboratory_name}", remarks=reference)
            self.log("evidence", evidence_id, "status_change",
                     f"Sent to {laboratory_name} ({reference})", case_id=item["case_id"])
        return examination_id

    def record_examination_result(self, examination_id: int, *,
                                  result_status: str,
                                  completed_datetime: str | None = None,
                                  result_summary: str | None = None,
                                  examiner_name: str | None = None,
                                  report_path: str | None = None,
                                  remarks: str | None = None) -> None:
        """Report what the laboratory came back with.

        The item's own forensic status and result follow the request, in
        the same transaction as the request itself.
        """
        request = self.db.query_one(
            "SELECT * FROM forensic_examinations WHERE examination_id = %s",
            (examination_id,))
        if request is None:
            raise DatabaseError("That examination request no longer exists.")

        values = {
            "result_status": result_status,
            "completed_datetime": completed_datetime or datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"),
            "result_summary": result_summary,
            "examiner_name": examiner_name,
            "report_path": report_path,
            "remarks": remarks,
        }
        values = {key: value for key, value in values.items() if value is not None}
        self.guard_fields(FORENSIC_RESULT_FIELDS, values, "forensic examination")

        item = self._require_item(request["evidence_id"])
        with self.db.transaction():
            self.update_row("forensic_examinations", "examination_id", examination_id,
                            FORENSIC_RESULT_FIELDS, values)
            outcome = {"forensic_status": "reported"}
            if result_summary:
                outcome["examination_result"] = result_summary
            self.update_row("evidence", "evidence_id", item["evidence_id"],
                            FORENSIC_SYNC, outcome)
            self.log("evidence", item["evidence_id"], "status_change",
                     f"Examination {request['request_no']}: {result_status}",
                     case_id=item["case_id"])

    # -- filed files ---------------------------------------------------
    def attachments(self, evidence_id: int) -> list[dict]:
        """What is filed against an item. Readable by every role: the
        names and hashes are what a report has to quote, and the bytes
        themselves stay in the evidence folder on the station machine."""
        return self.db.query(
            """
            SELECT a.*, u.username AS uploaded_by_username
            FROM evidence_attachments a
            LEFT JOIN users u ON u.user_id = a.uploaded_by_user_id
            WHERE a.evidence_id = %s
            ORDER BY a.attachment_id
            """,
            (evidence_id,),
        )

    def attachment(self, attachment_id: int) -> dict | None:
        return self.db.query_one(
            "SELECT * FROM evidence_attachments WHERE attachment_id = %s",
            (attachment_id,))

    def add_attachment(self, evidence_id: int, source: str | Path, *,
                       original_name: str | None = None, notes: str | None = None,
                       is_original: bool = True) -> int:
        """File a copy of a photograph, document or clip against an item.

        The source is never modified, and the copy is written to a name
        this method generates, so an upload cannot overwrite what is
        already filed. Nothing reaches the disk until the role check and
        the file checks have passed and the item does not already hold
        those exact bytes.
        """
        self.require(*self.write_roles)
        item = self._require_item(evidence_id)
        path = storage.validate(source, allowed=self.allowed_extensions,
                                max_bytes=self.max_file_bytes)
        digest = storage.sha256_of(path)
        if self.db.query_one(
                "SELECT attachment_id FROM evidence_attachments"
                " WHERE evidence_id = %s AND sha256 = %s", (evidence_id, digest)):
            raise DatabaseError(
                f"'{path.name}' is already filed against this item.")

        stored = storage.store(path, root=self.files_dir, evidence_id=evidence_id,
                               allowed=self.allowed_extensions,
                               max_bytes=self.max_file_bytes)
        with self.db.transaction():
            attachment_id = self.insert_row("evidence_attachments", {
                "evidence_id": evidence_id,
                "stored_path": stored.relative_path,
                "original_name": original_name or stored.original_name,
                "mime_type": stored.mime_type,
                "size_bytes": stored.size_bytes,
                "sha256": stored.sha256,
                "is_original": bool(is_original),
                "notes": notes,
                "uploaded_by_user_id": self.user_id(),
            })
            if is_original and not item["digital_hash_sha256"]:
                self.update_row("evidence", "evidence_id", evidence_id, EVIDENCE_PROFILE,
                                {"digital_hash_sha256": stored.sha256})
            self.log("evidence_attachment", attachment_id, "file_attach",
                     f"Filed '{stored.original_name}' "
                     f"({storage.human_size(stored.size_bytes)})",
                     case_id=item["case_id"])
        return attachment_id

    def attachment_path(self, attachment_id: int) -> Path:
        """Where a filed copy is kept, for the screen that opens it."""
        row = self.attachment(attachment_id)
        if row is None:
            raise DatabaseError("That attachment no longer exists.")
        return self.files_dir / row["stored_path"]

    def verify_attachment(self, attachment_id: int) -> bool:
        """Whether the bytes on file still match what was recorded."""
        row = self.attachment(attachment_id)
        if row is None:
            raise DatabaseError("That attachment no longer exists.")
        path = self.files_dir / row["stored_path"]
        return path.is_file() and storage.sha256_of(path) == row["sha256"]

    def verify_integrity(self, evidence_id: int) -> dict[int, bool]:
        """Check every copy filed against an item, by attachment id."""
        return {row["attachment_id"]: self.verify_attachment(row["attachment_id"])
                for row in self.attachments(evidence_id)}
