"""The evidence profile: what the item is, and every hand it has passed through."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import customtkinter as ctk

from app.db.connection import DatabaseError
from app.db.storage import human_size
from app.ui.dialogs import (
    ChildFormDialog, FormDialog, TextDialog, officer_choices, officer_id_for,
)
from app.ui.options import (
    CUSTODY_EVENTS, EVIDENCE_CATEGORIES, EVIDENCE_CONDITIONS, EVIDENCE_STATUSES,
    EVIDENCE_TYPES, FORENSIC_RESULTS, YES_NO, pretty,
)
from app.ui.theme import fonts
from app.ui.views.base import Button, ProfileView
from app.ui.widgets import PALETTE, Column, FormPanel, as_form_values

KEEP_AS_IS = "Not changing its state"


# ----------------------------------------------------------------------
# The records an item carries
# ----------------------------------------------------------------------
class TransferDialog(ChildFormDialog):
    """Append one link to the chain of custody.

    The officer handing the item over is taken from the last entry, so
    the chain cannot be broken by a mistyped name.
    """

    item_name = "custody entry"

    def build(self, form: FormPanel) -> None:
        self._officers = self.repos.officers.options()
        form.add_choice("event_type", "Movement", CUSTODY_EVENTS, required=True)
        form.add_datetime("occurred_at", "When", required=True)
        form.add_choice("to_officer", "Handed to", officer_choices(self._officers))
        form.add_entry("purpose", "Why it moved")
        form.add_choice("seal_intact", "Seal intact", YES_NO)
        form.add_choice("status", "State the item is now in", [KEEP_AS_IS] + EVIDENCE_STATUSES)
        form.add_text("remarks", "Remarks", height=80)
        form.set("event_type", "transferred")
        form.set("seal_intact", "Yes")

    def on_save(self, values: dict[str, Any]) -> None:
        if not values.get("occurred_at"):
            raise DatabaseError("Say when the item moved.")
        status = values.get("status")
        self.repos.evidence.record_transfer(
            self.parent_id,
            occurred_at=values["occurred_at"],
            event_type=values.get("event_type") or "transferred",
            to_officer_id=officer_id_for(self._officers, values.get("to_officer")),
            purpose=values.get("purpose") or None,
            seal_intact=values.get("seal_intact") != "No",
            remarks=values.get("remarks") or None,
            status=None if not status or status == KEEP_AS_IS else status)


class ForensicRequestDialog(ChildFormDialog):
    """Send the item to a laboratory, and log it leaving."""

    item_name = "forensic request"

    def build(self, form: FormPanel) -> None:
        form.add_entry("laboratory_name", "Laboratory", required=True)
        form.add_datetime("sent_datetime", "Sent on", required=True)
        form.add_entry("examination_type", "What is to be examined",
                       placeholder="e.g. DNA, fingerprint, image analysis")
        form.add_entry("request_no", "Requisition number",
                       placeholder="Leave blank to let the system issue one")
        form.add_text("remarks", "Remarks", height=90)

    def on_save(self, values: dict[str, Any]) -> None:
        if not values.get("laboratory_name") or not values.get("sent_datetime"):
            raise DatabaseError("Name the laboratory and the day the item went to it.")
        self.repos.evidence.send_to_forensics(
            self.parent_id, laboratory_name=values["laboratory_name"],
            sent_datetime=values["sent_datetime"],
            examination_type=values.get("examination_type") or None,
            request_no=values.get("request_no") or None,
            remarks=values.get("remarks") or None)


class ForensicResultDialog(ChildFormDialog):
    item_name = "examination result"

    def build(self, form: FormPanel) -> None:
        form.add_choice("result_status", "Result", FORENSIC_RESULTS, required=True)
        form.add_datetime("completed_datetime", "Reported on")
        form.add_entry("examiner_name", "Examiner")
        form.add_entry("report_path", "Report reference")
        form.add_text("result_summary", "What the laboratory found", height=140)
        form.add_text("remarks", "Remarks", height=70)
        self.prefill(form)

    def on_save(self, values: dict[str, Any]) -> None:
        if not values.get("result_status"):
            raise DatabaseError("Say what the examination came back with.")
        self.repos.evidence.record_examination_result(
            self.record["examination_id"],
            result_status=values["result_status"],
            completed_datetime=values.get("completed_datetime") or None,
            result_summary=values.get("result_summary") or None,
            examiner_name=values.get("examiner_name") or None,
            report_path=values.get("report_path") or None,
            remarks=values.get("remarks") or None)


class AttachmentDialog(FormDialog):
    """File a copy of a photograph, document or clip against the item.

    The bytes are never touched here: the repository copies them to a
    name it generates, so filing a second 'scene.jpg' cannot bury the
    first one.
    """

    def __init__(self, master, repos, evidence_id: int, source: str) -> None:
        self.repos = repos
        self.evidence_id = evidence_id
        self.source = source
        super().__init__(master, "File a copy", size=(560, 400), save_text="File it")

    def build(self, form: FormPanel) -> None:
        holder = form.add_block("Selected file")
        ctk.CTkLabel(
            holder, text=f"{Path(self.source).name}  "
                         f"({human_size(Path(self.source).stat().st_size)})",
            font=fonts().body, text_color=PALETTE.TEXT, anchor="w",
        ).grid(row=1, column=0, sticky="w")
        form.add_choice("is_original", "Is this the original?", YES_NO)
        form.add_text("notes", "Notes on this copy", height=90)
        form.set("is_original", "Yes")

    def on_save(self, values: dict[str, Any]) -> None:
        self.repos.evidence.add_attachment(
            self.evidence_id, self.source,
            notes=values.get("notes") or None,
            is_original=values.get("is_original") != "No")


# ----------------------------------------------------------------------
class EvidenceProfileView(ProfileView):
    """One evidence item, opened tab by tab."""

    def __init__(self, master, app, evidence_id: int, on_back) -> None:
        super().__init__(master, app, on_back=on_back)
        self.evidence_id = evidence_id
        self._officers: list[dict] = []
        self._build_tabs()
        self.reload()

    # -- the record itself ---------------------------------------------
    def load_record(self) -> dict | None:
        return self.repos.evidence.get(self.evidence_id)

    def paint_heading(self, record: dict) -> None:
        case = self.repos.cases.get(record["case_id"]) or {}
        pills = [
            (pretty(record.get("evidence_status")),
             PALETTE.evidence_status.get(record.get("evidence_status"),
                                         PALETTE.TEXT_MUTED)),
            (pretty(record.get("forensic_status")),
             PALETTE.forensic_status.get(record.get("forensic_status"),
                                         PALETTE.TEXT_MUTED)),
            (f"Seal {pretty(record.get('condition'))}",
             _condition_colour(record.get("condition"))),
        ]
        if record.get("is_prime"):
            # The exhibit the case turns on, named by whoever decided so.
            pills.insert(0, ("Prime evidence", PALETTE.ACCENT))
        self.set_heading(
            record["item_name"] or record["description"],
            subtitle=f"Case {case.get('case_no', record['case_id'])}"
                     f"  |  Ref {record.get('evidence_ref') or '-'}"
                     f"  |  {pretty(record.get('type'))}",
            pills=pills,
        )
        self._state.configure(text=_state_line(record))

    # -- tabs -----------------------------------------------------------
    def _build_tabs(self) -> None:
        self.form_tab(
            "Overview", title="What the item is", columns=3,
            note="The reference number is issued by the register itself.",
            build=self._build_overview, save=self._save_overview,
        )
        self.form_tab(
            "Collection", title="How the item was picked up", columns=2,
            note="Where, by whom, and under what authority.",
            build=self._build_collection, save=self._save_collection,
            present=self._present_collection, accept=self._accept_collection,
        )
        self.table_tab(
            "Attachments", _attachment_columns(), title="Copies filed here",
            note="A filed copy is never deleted from the store, so it is not removed here either.",
            load=self._attachments, add=self._file_a_copy,
            buttons=[
                Button("Open copy", self._open_copy, write=False),
                Button("Verify hashes", self._verify_hashes, write=False),
            ],
            empty_text="No file is filed against this item.",
        )
        self.table_tab(
            "Custody History", _custody_columns(), title="Chain of custody",
            note="Append only: a mistake is corrected by another entry, never by rewriting one.",
            load=self._custody, add=self._record_movement,
            empty_text="The chain of custody has no entries yet.",
        )
        self.table_tab(
            "Forensic Examination", _examination_columns(), title="Examinations",
            note="Sending an item out also writes its movement in the chain of custody.",
            load=self._examinations, add=self._send_to_forensics,
            on_row_double=self._read_examination,
            buttons=[Button("Report result", self._report_result)],
            empty_text="This item has not been sent for examination.",
        )

        self.add_action("Open case", self._open_case, write=False)
        self.add_action("Delete item", self._delete, danger=True)

    def _build_overview(self, form: FormPanel) -> None:
        form.add_entry("item_name", "Item name", required=True,
                       placeholder="e.g. Black laptop, Dell Inspiron")
        form.add_choice("type", "Evidence type", EVIDENCE_TYPES)
        form.add_choice("evidence_category", "Category", EVIDENCE_CATEGORIES)
        form.add_choice("condition", "Condition", EVIDENCE_CONDITIONS)
        form.add_entry("packaging_type", "Packaging",
                       placeholder="e.g. Sealed plastic bag, paper envelope")
        form.add_entry("seal_number", "Seal number")
        form.add_entry("storage_location", "Stored at",
                       placeholder="e.g. Evidence room, rack B-4")
        form.add_entry("seized_under", "Seized under",
                       placeholder="e.g. Section 102 CrPC, memo dated 4 Nov")
        form.add_text("description", "Short description", height=70)
        form.add_text("detailed_description", "Full description", height=120)

        holder = form.add_block("Where the item stands")
        self._state = ctk.CTkLabel(
            holder, text="", font=fonts().small, text_color=PALETTE.TEXT_MUTED,
            anchor="w", justify="left", wraplength=880,
        )
        self._state.grid(row=1, column=0, sticky="w")

    def _save_overview(self, values: dict[str, Any]) -> None:
        if not values.get("item_name"):
            raise DatabaseError("An item has to have a name.")
        self.repos.evidence.update(self.evidence_id, **values)

    # -- collection ------------------------------------------------------
    def _build_collection(self, form: FormPanel) -> None:
        self._officers = self.repos.officers.options()
        form.add_choice("collected_by", "Collected by", officer_choices(self._officers))
        form.add_datetime("collected_datetime", "Collected on")
        form.add_entry("collection_location", "Collected at")
        form.add_entry("collection_method", "How it was taken",
                       placeholder="e.g. Seizure memo, voluntary handover, forensic sweep")
        form.add_datetime("chain_of_custody_datetime", "Chain opened on")
        form.add_entry("digital_hash_sha256", "SHA-256 of the digital original",
                       placeholder="Filled in when an original is filed here")

    def _present_collection(self, record: dict) -> dict:
        values = as_form_values(record)
        for row in self._officers:
            if row["officer_id"] == record.get("collected_by_officer_id"):
                values["collected_by"] = f"{row['name']} - {row['rank']}"
        return values

    def _accept_collection(self, values: dict[str, Any]) -> dict:
        details = {key: value for key, value in values.items() if key != "collected_by"}
        officer_id = officer_id_for(self._officers, values.get("collected_by"))
        if officer_id is not None:
            details["collected_by_officer_id"] = officer_id
        return details

    def _save_collection(self, values: dict[str, Any]) -> None:
        digest = values.get("digital_hash_sha256")
        if digest and len(digest) != 64:
            raise DatabaseError(
                "A SHA-256 hash is 64 characters. Paste the whole hash, or clear this "
                "field and file the original on the Attachments tab instead.")
        self.repos.evidence.update(self.evidence_id, **values)

    # -- filed copies ----------------------------------------------------
    def _attachments(self) -> list[dict]:
        return self.repos.evidence.attachments(self.evidence_id)

    def _file_a_copy(self) -> None:
        source = _pick_file(self)
        if not source:
            return
        try:
            AttachmentDialog(self.app, self.repos, self.evidence_id, source).show()
        except DatabaseError as exc:
            self.app.toast(str(exc), "error", 6500)

    def _open_copy(self) -> None:
        self.require_selection("Attachments", "a filed copy", self._open_row)

    def _open_row(self, row: dict) -> None:
        path = self.repos.evidence.attachment_path(row["attachment_id"])
        if not path.is_file():
            raise DatabaseError(f"'{path.name}' is not in the evidence folder on this machine.")
        try:
            os.startfile(path)
        except OSError as exc:
            raise DatabaseError(f"Windows would not open '{path.name}': {exc}") from exc

    def _verify_hashes(self) -> None:
        results = self.guard(self.repos.evidence.verify_integrity, self.evidence_id)
        if results is None:
            return
        if not results:
            self.app.toast("There is no copy filed against this item to check.", "info")
        elif all(results.values()):
            self.app.toast(
                f"{len(results)} filed cop{'y is' if len(results) == 1 else 'ies are'} "
                "unchanged.", "success")
        else:
            broken = sum(1 for ok in results.values() if not ok)
            self.app.toast(
                f"{broken} filed cop{'y does' if broken == 1 else 'ies do'} not match "
                "the hash on record. Report this to the evidence officer.", "error", 8000)

    # -- chain of custody -------------------------------------------------
    def _custody(self) -> list[dict]:
        return self.repos.evidence.custody_history(self.evidence_id)

    def _record_movement(self) -> None:
        TransferDialog(self.app, self.repos, self.evidence_id).show()

    # -- forensics --------------------------------------------------------
    def _examinations(self) -> list[dict]:
        return self.repos.evidence.examinations(self.evidence_id)

    def _send_to_forensics(self) -> None:
        ForensicRequestDialog(self.app, self.repos, self.evidence_id).show()

    def _report_result(self) -> None:
        self.require_selection(
            "Forensic Examination", "an examination request",
            lambda row: ForensicResultDialog(
                self.app, self.repos, self.evidence_id, row).show())

    def _read_examination(self, row: dict) -> None:
        TextDialog(
            self.app, f"Requisition {row['request_no']}",
            row.get("result_summary") or "The result has not been recorded yet.",
            subtitle=f"{row.get('laboratory_name')}  |  "
                     f"{pretty(row.get('examination_type'))}  |  "
                     f"sent {row.get('sent_datetime')}  |  "
                     f"{pretty(row.get('result_status'))}",
        ).show()

    # -- header -----------------------------------------------------------
    def _open_case(self) -> None:
        self.app.navigate("cases", case_id=self.record["case_id"])

    def _delete(self) -> None:
        if self.delete_record(
            f"Evidence '{self.record.get('item_name') or self.record['evidence_ref']}'",
            lambda: self.repos.evidence.delete(self.evidence_id),
        ):
            self.on_back()


# ----------------------------------------------------------------------
def _pick_file(parent) -> str:
    """Ask for a file, or hand back nothing when the choice is cancelled."""
    from tkinter import filedialog

    return filedialog.askopenfilename(
        parent=parent, title="Choose the file to file as evidence",
        filetypes=[("Evidence files",
                    ".jpg .jpeg .png .gif .webp .tif .tiff .bmp .heic .pdf .txt .csv "
                    ".rtf .odt .doc .docx .xls .xlsx .ppt .pptx .mp4 .avi .mov .mkv "
                    ".webm .mp3 .wav .m4a .amr .zip .rar .7z .tar .gz"),
                   ("All files", "*.*")],
    )


def _state_line(record: dict) -> str:
    """Where the item stands, which no form on this page is allowed to set."""
    return (
        f"State: {pretty(record.get('evidence_status'))}"
        f"  |  Forensic: {pretty(record.get('forensic_status'))}"
        f"  |  Laboratory: {record.get('laboratory_name') or '-'}"
        f"\nLast result: {record.get('examination_result') or '-'}"
    )


def _condition_colour(condition: str | None) -> str:
    return {
        "intact": PALETTE.SUCCESS,
        "partial": PALETTE.WARNING,
        "degraded": PALETTE.WARNING,
        "damaged": PALETTE.DANGER,
    }.get(condition or "", PALETTE.TEXT_MUTED)


def _attachment_columns() -> list[Column]:
    return [
        Column("original_name", "Filed as", 200),
        Column("is_original", "Original", 90, anchor="center",
               render=lambda row: "Original" if row.get("is_original") else "Copy"),
        Column("mime_type", "Kind", 140),
        Column("size_bytes", "Size", 100, anchor="e",
               render=lambda row: human_size(int(row.get("size_bytes") or 0))),
        Column("sha256", "SHA-256", 200,
               render=lambda row: (row.get("sha256") or "")[:16] + "..."),
        Column("uploaded_by_username", "Filed by", 130),
        Column("uploaded_at", "Filed on", 160),
        Column("notes", "Notes", 220),
    ]


def _custody_columns() -> list[Column]:
    return [
        Column("sequence_no", "Link", 70, anchor="center"),
        Column("event_type", "Movement", 140),
        Column("occurred_at", "When", 160),
        Column("from_officer_name", "From", 170),
        Column("to_officer_name", "To", 170),
        Column("purpose", "Purpose", 220),
        Column("seal_intact", "Seal", 90, anchor="center",
               render=lambda row: "-" if row.get("seal_intact") is None
               else ("Intact" if row["seal_intact"] else "Broken")),
        Column("recorded_by_username", "Logged by", 130),
    ]


def _examination_columns() -> list[Column]:
    return [
        Column("request_no", "Requisition", 150),
        Column("laboratory_name", "Laboratory", 190),
        Column("examination_type", "Examination", 170),
        Column("examiner_name", "Examiner", 160),
        Column("sent_datetime", "Sent", 160),
        Column("completed_datetime", "Reported", 160),
        Column("result_status", "Result", 140),
        Column("result_summary", "Findings", 260),
    ]
