"""The witness profile: who they are, what they said, and how they are kept safe."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk

from app.db.connection import DatabaseError
from app.ui.dialogs import (
    ChildFormDialog, TextDialog, officer_choices, officer_id_for,
)
from app.ui.options import (
    AVAILABILITY, CONFIDENTIALITY_LEVELS, GENDERS, INTERVIEW_OUTCOMES,
    PROTECTION_STATUSES, WITNESS_TYPES, YES_NO, pretty,
)
from app.ui.theme import fonts
from app.ui.views.base import Button, ProfileView
from app.ui.widgets import PALETTE, Column, FormPanel, clip


# ----------------------------------------------------------------------
# The records a witness carries
# ----------------------------------------------------------------------
class StatementDialog(ChildFormDialog):
    """File what the witness says now, beside what they said before."""

    item_name = "statement"
    size = (700, 520)

    def build(self, form: FormPanel) -> None:
        form.add_entry("language", "Language", placeholder="e.g. English, Hindi, Tamil")
        form.add_entry("remark", "Why the account is changing",
                       placeholder="e.g. Recall improved after the site visit")
        form.add_text("statement_body", "Statement", height=240, required=True,
                      placeholder="The witness's own words")

    def on_save(self, values: dict[str, Any]) -> None:
        self.repos.witnesses.add_statement(
            self.parent_id, values.get("statement_body") or "",
            language=values.get("language") or None, remark=values.get("remark") or None)


class ReliabilityDialog(ChildFormDialog):
    """A person's judgement of a witness, signed with their name.

    Nothing here works the credibility out on its own: the flag moves
    only when somebody gives a reason for moving it.
    """

    item_name = "reliability assessment"
    size = (620, 420)

    def build(self, form: FormPanel) -> None:
        form.add_choice("is_reliable", "Believed", YES_NO, required=True)
        form.add_text("reliability_remark", "Why", height=180, required=True,
                      placeholder="What makes this witness believed, or not")

    def on_save(self, values: dict[str, Any]) -> None:
        self.repos.witnesses.assess_reliability(
            self.parent_id, values.get("is_reliable") == "Yes",
            values.get("reliability_remark") or "")


class InterviewDialog(ChildFormDialog):
    item_name = "interview booking"
    size = (660, 460)

    def build(self, form: FormPanel) -> None:
        self._officers = self.repos.officers.options()
        form.add_datetime("scheduled_datetime", "Scheduled for", required=True)
        form.add_entry("location", "Where")
        form.add_choice("interviewer", "Interviewing officer",
                        officer_choices(self._officers))
        form.add_text("notes", "Notes for the interview", height=140)

    def on_save(self, values: dict[str, Any]) -> None:
        if not values.get("scheduled_datetime"):
            raise DatabaseError("Say when the interview is to be held.")
        self.repos.witnesses.schedule_interview(
            self.parent_id, values["scheduled_datetime"],
            location=values.get("location") or None,
            interviewer_officer_id=officer_id_for(self._officers, values.get("interviewer")),
            notes=values.get("notes") or None)


class InterviewOutcomeDialog(ChildFormDialog):
    """How the interview went, written against the booking that was made."""

    item_name = "interview outcome"
    size = (640, 460)

    def build(self, form: FormPanel) -> None:
        form.add_choice("outcome", "Outcome", INTERVIEW_OUTCOMES, required=True)
        form.add_datetime("held_datetime", "Held at")
        form.add_entry("duration_minutes", "Minutes taken")
        form.add_text("notes", "What came out of it", height=160)
        self.prefill(form)

    def on_save(self, values: dict[str, Any]) -> None:
        duration = values.get("duration_minutes")
        self.repos.witnesses.mark_interview(
            self.record["interview_id"], values["outcome"],
            held_datetime=values.get("held_datetime") or None,
            duration_minutes=int(duration) if duration.isdigit() else None,
            notes=values.get("notes") or None)


class ProtectionDialog(ChildFormDialog):
    item_name = "protection order"

    def build(self, form: FormPanel) -> None:
        form.add_entry("measure", "Measure", required=True,
                       placeholder="e.g. Police guard, relocated, identity withheld")
        form.add_choice("status", "Status", PROTECTION_STATUSES)
        form.add_entry("basis", "Ordered on what basis", required=True,
                       placeholder="e.g. Threat received on 4 November")
        form.add_date("start_date", "From", required=True)
        form.add_date("end_date", "Until")
        form.add_datetime("review_datetime", "Next review")
        form.add_text("remarks", "Remarks", height=110)
        self.prefill(form)

    def on_save(self, values: dict[str, Any]) -> None:
        for key, label in (("measure", "the measure"), ("basis", "why it is needed"),
                           ("start_date", "when it starts")):
            if not values.get(key):
                raise DatabaseError(f"Name {label}.")
        if self.is_new:
            self.repos.witnesses.add_protection(
                self.parent_id, values["measure"], values["basis"], values["start_date"],
                **{key: value for key, value in values.items()
                   if key not in ("measure", "basis", "start_date")})
        else:
            self.repos.witnesses.update_protection(
                self.record["protection_id"], **values)


# ----------------------------------------------------------------------
class WitnessProfileView(ProfileView):
    """One witness, opened tab by tab."""

    def __init__(self, master, app, witness_id: int, on_back) -> None:
        super().__init__(master, app, on_back=on_back)
        self.witness_id = witness_id
        self._build_tabs()
        self.reload()

    # -- the record itself ---------------------------------------------
    def load_record(self) -> dict | None:
        return self.repos.witnesses.get(self.witness_id)

    def paint_heading(self, record: dict) -> None:
        case = self.repos.cases.get(record["case_id"]) or {}
        kind = pretty(record.get("witness_type"))
        self.set_heading(
            record["name"],
            subtitle=f"Case {case.get('case_no', record['case_id'])}"
                     f"  |  {kind if kind.lower().endswith('witness') else kind + ' witness'}",
            pills=[
                (pretty(record.get("availability_status")),
                 PALETTE.SUCCESS if record.get("availability_status") == "available"
                 else PALETTE.TEXT_MUTED),
                ("Needs protection" if record.get("protection_required") else "No order",
                 PALETTE.WARNING if record.get("protection_required")
                 else PALETTE.TEXT_MUTED),
                _credibility(record),
                (pretty(record.get("confidentiality_level")),
                 PALETTE.confidentiality.get(record.get("confidentiality_level"),
                                             PALETTE.TEXT_MUTED)),
            ],
        )
        self._assessment.configure(text=_assessment_line(record))

    # -- tabs -----------------------------------------------------------
    def _build_tabs(self) -> None:
        self.form_tab(
            "Personal information", title="Who the witness is", columns=3,
            note="Contact detail is masked for a viewer.",
            build=self._build_personal, save=self._save_personal,
        )
        self.table_tab(
            "Statements", _statement_columns(), title="Statements on file",
            note="Every account is kept. A new one never replaces an old one.",
            load=self._statements, add=self._add_statement,
            on_row_double=self._read_statement, privileged_only=True,
            buttons=[
                Button("Read statement", self._read_selected, write=False),
                Button("Assess reliability", self._assess_reliability),
            ],
            empty_text="This witness has not given a statement yet.",
        )
        self.table_tab(
            "Interviews", _interview_columns(), title="Interviews",
            note="A booking stays on file when its outcome is recorded.",
            load=self._interviews, add=self._schedule, delete=self._delete_interview,
            privileged_only=True,
            buttons=[Button("Record outcome", self._mark_outcome)],
            empty_text="No interview has been booked for this witness.",
        )
        self.table_tab(
            "Protection", _protection_columns(), title="Protection",
            note="Who is being protected, and why, stays with the case staff.",
            load=self._protection, add=self._order_protection,
            delete=self._delete_protection, privileged_only=True,
            buttons=[Button("Edit order", self._edit_protection)],
            empty_text="No protection has been ordered for this witness.",
        )

        self.add_action("Open case", self._open_case, write=False)
        self.add_action("Delete witness", self._delete, danger=True)

    def _build_personal(self, form: FormPanel) -> None:
        form.add_entry("name", "Full name", required=True)
        form.add_choice("gender", "Gender", GENDERS)
        form.add_date("date_of_birth", "Date of birth")
        form.add_entry("phone", "Phone")
        form.add_entry("email", "Email")
        form.add_entry("address", "Address")
        form.add_entry("occupation", "Occupation")
        form.add_choice("witness_type", "Witness type", WITNESS_TYPES)
        form.add_choice("availability_status", "Availability", AVAILABILITY)
        form.add_choice("confidentiality_level", "Confidentiality", CONFIDENTIALITY_LEVELS)
        form.add_entry("relationship_to_victim", "Relation to the victim")
        form.add_entry("relationship_to_accused", "Relation to the accused")
        form.add_datetime("observation_datetime", "Saw it at")
        form.add_entry("observation_location", "Saw it from")
        form.add_entry("statement_language", "Speaks")

        holder = form.add_block("Credibility, as a person decided it")
        self._assessment = ctk.CTkLabel(
            holder, text="", font=fonts().small, text_color=PALETTE.TEXT_MUTED,
            anchor="w", justify="left", wraplength=880,
        )
        self._assessment.grid(row=1, column=0, sticky="w")

    def _save_personal(self, values: dict[str, Any]) -> None:
        if not values.get("name"):
            raise DatabaseError("A witness has to have a name.")
        self.repos.witnesses.update(self.witness_id, **values)

    # -- statements -------------------------------------------------------
    def _statements(self) -> list[dict]:
        return self.repos.witnesses.statements(self.witness_id)

    def _add_statement(self) -> None:
        StatementDialog(self.app, self.repos, self.witness_id).show()

    def _read_selected(self) -> None:
        self.require_selection("Statements", "a statement", self._read_statement)

    def _read_statement(self, row: dict) -> None:
        state = (f"superseded {row['superseded_at']}" if row.get("superseded_at")
                 else "the current account")
        TextDialog(
            self.app, f"Statement version {row['version']}",
            row.get("statement_body") or "",
            subtitle=f"Recorded {row.get('recorded_at')} by "
                     f"{row.get('recorded_by') or '-'} in "
                     f"{row.get('language') or '-'}  |  {state}",
        ).show()

    def _assess_reliability(self) -> None:
        ReliabilityDialog(self.app, self.repos, self.witness_id).show()

    # -- interviews -------------------------------------------------------
    def _interviews(self) -> list[dict]:
        return self.repos.witnesses.interviews(self.witness_id)

    def _schedule(self) -> None:
        InterviewDialog(self.app, self.repos, self.witness_id).show()

    def _mark_outcome(self) -> None:
        self.require_selection(
            "Interviews", "a booking",
            lambda row: InterviewOutcomeDialog(
                self.app, self.repos, self.witness_id, row).show())

    def _delete_interview(self, row: dict) -> None:
        self.delete_record(
            f"The interview booked for {row['scheduled_datetime']}",
            lambda: self.repos.witnesses.delete_interview(row["interview_id"]))

    # -- protection -------------------------------------------------------
    def _protection(self) -> list[dict]:
        return self.repos.witnesses.protection_records(self.witness_id)

    def _order_protection(self) -> None:
        ProtectionDialog(self.app, self.repos, self.witness_id).show()

    def _edit_protection(self) -> None:
        self.require_selection(
            "Protection", "an order",
            lambda row: ProtectionDialog(
                self.app, self.repos, self.witness_id, row).show())

    def _delete_protection(self, row: dict) -> None:
        self.delete_record(
            f"The protection ordered on {row['start_date']}",
            lambda: self.repos.witnesses.delete_protection(row["protection_id"]))

    # -- header -----------------------------------------------------------
    def _open_case(self) -> None:
        self.app.navigate("cases", case_id=self.record["case_id"])

    def _delete(self) -> None:
        if self.delete_record(
            f"Witness '{self.record['name']}'",
            lambda: self.repos.witnesses.delete(self.witness_id),
        ):
            self.on_back()


# ----------------------------------------------------------------------
def _credibility(record: dict) -> tuple[str, str]:
    """What the heading says about a witness's account.

    A witness who has not been assessed is not treated as believed: the
    flag on the row is only the note the recording officer left, so the
    pill waits for the signed decision.
    """
    if not record.get("assessed_at"):
        return "Credibility not assessed", PALETTE.TEXT_MUTED
    if record.get("is_reliable"):
        return "Believed", PALETTE.SUCCESS
    return "Not believed", PALETTE.DANGER


def _assessment_line(record: dict) -> str:
    if not record.get("assessed_at"):
        return ("Nobody has judged this witness yet. Use 'Assess reliability' when a "
                "person has read the account and decided.")
    remark = record.get("reliability_remark") or "No reason was written down."
    return f"{remark}\nDecided on {record['assessed_at']}."


def _statement_columns() -> list[Column]:
    return [
        Column("version", "Version", 80, anchor="center"),
        Column("superseded_at", "Status", 120, anchor="center",
               render=lambda row: "Current" if not row.get("superseded_at") else "Superseded"),
        Column("statement_body", "Account", 460,
               render=lambda row: clip(row.get("statement_body"))),
        Column("language", "Language", 110),
        Column("recorded_at", "Recorded", 160),
        Column("recorded_by", "By", 140),
        Column("remark", "Note", 220),
    ]


def _interview_columns() -> list[Column]:
    return [
        Column("scheduled_datetime", "Scheduled", 160),
        Column("held_datetime", "Held", 160),
        Column("location", "Where", 200),
        Column("interviewer_name", "Officer", 180),
        Column("duration_minutes", "Minutes", 90, anchor="center"),
        Column("outcome", "Outcome", 150),
        Column("notes", "Notes", 260),
    ]


def _protection_columns() -> list[Column]:
    return [
        Column("measure", "Measure", 220),
        Column("status", "Status", 120),
        Column("start_date", "From", 120),
        Column("end_date", "Until", 120),
        Column("review_datetime", "Next review", 160),
        Column("basis", "Basis", 260),
        Column("authorised_by", "Ordered by", 150),
    ]
