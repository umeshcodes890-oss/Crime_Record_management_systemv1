"""The victim profile: who they are, what they needed, and what followed."""

from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseError
from app.ui.dialogs import ChildFormDialog, officer_choices, officer_id_for
from app.ui.options import (
    COMPENSATION_STATUSES, COMPENSATION_TYPES, CONFIDENTIALITY_LEVELS, CONTACT_TYPES,
    GENDERS, INJURY_LEVELS, MEDICAL_ASSISTANCE, YES_NO, pretty,
)
from app.ui.views.base import Button, ProfileView
from app.ui.widgets import PALETTE, Column, FormPanel, as_bools


# ----------------------------------------------------------------------
# The records a victim carries
# ----------------------------------------------------------------------
class MedicalRecordDialog(ChildFormDialog):
    item_name = "medical record"

    def build(self, form: FormPanel) -> None:
        form.add_entry("facility", "Hospital or centre", required=True,
                       placeholder="Where the victim was taken")
        form.add_entry("treatment_type", "Treatment", required=True,
                       placeholder="e.g. First aid, surgery, dressing")
        form.add_entry("treating_doctor", "Treating doctor")
        form.add_datetime("admitted_datetime", "Admitted on")
        form.add_datetime("discharged_datetime", "Discharged on")
        form.add_entry("cost_incurred", "Cost incurred", placeholder="e.g. 4500.00")
        form.add_entry("medical_report_path", "Report reference")
        form.add_text("description", "What was found", height=70)
        form.add_text("remarks", "Remarks", height=60)
        self.prefill(form)

    def on_save(self, values: dict[str, Any]) -> None:
        if not values.get("facility") or not values.get("treatment_type"):
            raise DatabaseError("Name the facility and the treatment that was given.")
        if self.is_new:
            self.repos.victims.add_medical_record(
                self.parent_id, values["facility"], values["treatment_type"],
                **{key: value for key, value in values.items()
                   if key not in ("facility", "treatment_type")})
        else:
            self.repos.victims.update_medical_record(
                self.record["medical_record_id"], **values)


class ContactDialog(ChildFormDialog):
    item_name = "contact entry"

    def build(self, form: FormPanel) -> None:
        self._officers = self.repos.officers.options()
        form.add_choice("contact_type", "How", CONTACT_TYPES, required=True)
        form.add_datetime("contact_datetime", "When", required=True)
        form.add_choice("officer", "Who made the contact", officer_choices(self._officers))
        form.add_entry("purpose", "Purpose")
        form.add_text("outcome", "What came of it", height=80)
        form.add_choice("follow_up_required", "Follow-up needed", YES_NO)
        form.add_datetime("follow_up_datetime", "Follow up on")
        self.prefill(form, yes_no=("follow_up_required",))
        if self.is_new:
            form.set("follow_up_required", "No")
        for row in self._officers:
            if row["officer_id"] == self.record.get("made_by_officer_id"):
                form.set("officer", f"{row['name']} - {row['rank']}")

    def on_save(self, values: dict[str, Any]) -> None:
        if not values.get("contact_datetime"):
            raise DatabaseError("Say when the contact was made.")
        details = as_bools(dict(values), "follow_up_required")
        details["made_by_officer_id"] = officer_id_for(self._officers, values.get("officer"))
        details.pop("officer")
        if self.is_new:
            self.repos.victims.add_contact(
                self.parent_id, values["contact_type"], values["contact_datetime"],
                **{key: value for key, value in details.items()
                   if key not in ("contact_type", "contact_datetime")})
        else:
            self.repos.victims.update_contact(self.record["contact_id"], **details)


class CompensationDialog(ChildFormDialog):
    item_name = "compensation claim"

    def build(self, form: FormPanel) -> None:
        form.add_entry("scheme_name", "Scheme", required=True,
                       placeholder="e.g. Victim Compensation Scheme 2018")
        form.add_choice("status", "Status", COMPENSATION_STATUSES)
        form.add_choice("compensation_type", "Type of help", COMPENSATION_TYPES)
        form.add_date("application_date", "Applied on")
        form.add_entry("awarded_amount", "Awarded", placeholder="e.g. 50000.00")
        form.add_entry("received_amount", "Received", placeholder="e.g. 25000.00")
        form.add_entry("sanctioning_authority", "Sanctioning authority")
        form.add_entry("order_reference", "Order reference")
        form.add_text("remarks", "Remarks", height=80)
        self.prefill(form)

    def on_save(self, values: dict[str, Any]) -> None:
        if not values.get("scheme_name"):
            raise DatabaseError("Name the scheme the victim is claiming under.")
        if self.is_new:
            self.repos.victims.add_compensation(
                self.parent_id, values["scheme_name"],
                **{key: value for key, value in values.items() if key != "scheme_name"})
        else:
            self.repos.victims.update_compensation(
                self.record["compensation_id"], **values)


# ----------------------------------------------------------------------
class VictimProfileView(ProfileView):
    """One victim, opened tab by tab."""

    def __init__(self, master, app, victim_id: int, on_back) -> None:
        super().__init__(master, app, on_back=on_back)
        self.victim_id = victim_id
        self._build_tabs()
        self.reload()

    # -- the record itself ---------------------------------------------
    def load_record(self) -> dict | None:
        return self.repos.victims.get(self.victim_id)

    def paint_heading(self, record: dict) -> None:
        case = self.repos.cases.get(record["case_id"]) or {}
        pills = [
            (pretty(record.get("injury_level")),
             PALETTE.injury.get(record.get("injury_level"), PALETTE.TEXT_MUTED)),
            (pretty(record.get("confidentiality_level")),
             PALETTE.confidentiality.get(record.get("confidentiality_level"),
                                         PALETTE.TEXT_MUTED)),
        ]
        if record.get("is_prime"):
            # Only the one the case is told from says so.
            pills.insert(0, ("Prime victim", PALETTE.ACCENT))
        self.set_heading(
            record["name"],
            subtitle=f"Case {case.get('case_no', record['case_id'])}"
                     f"  |  {pretty(record.get('injury_level'))} injury"
                     f"  |  Medical help: "
                     f"{pretty(record.get('medical_assistance_status'))}",
            pills=pills,
        )

    # -- tabs -----------------------------------------------------------
    def _build_tabs(self) -> None:
        self.form_tab(
            "Personal information", title="Who the victim is", columns=3,
            note="Blank means nobody has recorded it yet.",
            build=self._build_personal, save=self._save_personal,
        )
        self._build_medical_tab()
        self.form_tab(
            "Statements", title="Statement as recorded", columns=1, scroll=False,
            note="The account the investigating officer wrote down.",
            build=self._build_statement, save=self._save_statement,
        )
        self.table_tab(
            "Contacts", _contact_columns(), title="Contacts with the victim",
            note="Every call, visit and letter, and what came of it.",
            load=self._contacts, add=self._add_contact, delete=self._delete_contact,
            buttons=[Button("Edit contact", self._edit_contact)],
            empty_text="Nobody has been in touch with the victim yet.",
        )
        self.table_tab(
            "Compensation", _compensation_columns(), title="Compensation",
            load=self._compensation, privileged_only=True,
            add=self._add_compensation, delete=self._delete_compensation,
            buttons=[Button("Edit claim", self._edit_compensation)],
            empty_text="No compensation has been claimed for this victim.",
        )

        self.add_action("Open case", self._open_case, write=False)
        self.add_action("Delete victim", self._delete, danger=True)

    def _build_personal(self, form: FormPanel) -> None:
        form.add_entry("name", "Full name", required=True)
        form.add_entry("age", "Age")
        form.add_choice("gender", "Gender", GENDERS)
        form.add_date("date_of_birth", "Date of birth")
        form.add_entry("phone", "Phone")
        form.add_entry("email", "Email")
        form.add_entry("occupation", "Occupation")
        form.add_entry("national_id", "National ID", placeholder="Aadhaar or passport")
        form.add_choice("confidentiality_level", "Confidentiality", CONFIDENTIALITY_LEVELS)
        form.add_entry("emergency_contact_name", "Emergency contact")
        form.add_entry("emergency_contact_phone", "Emergency contact phone")
        form.add_entry("relationship_to_accused", "Relation to the accused")
        form.add_datetime("incident_datetime", "When it happened")
        form.add_entry("incident_location", "Where it happened")
        form.add_text("address", "Address", height=64)

    def _save_personal(self, values: dict[str, Any]) -> None:
        if not values.get("name"):
            raise DatabaseError("A victim has to have a name.")
        self.repos.victims.update(self.victim_id, **values)

    def _build_medical_tab(self) -> None:
        page = self.open_tab("Medical", blocks=4)
        self.form_tab(
            "Treatment the victim was given", page=page, row=0, scroll=False,
            note="What the hospital told the officer, not the reports below.",
            build=self._build_medical, save=self._save_medical,
        )
        self.table_tab(
            "Medical records", _medical_columns(), page=page, row=2,
            title="Medical records", load=self._medical_records, privileged_only=True,
            add=self._add_medical_record, delete=self._delete_medical_record,
            buttons=[Button("Edit record", self._edit_medical_record)],
            height=200,
            empty_text="No treatment has been filed for this victim.",
        )

    def _build_medical(self, form: FormPanel) -> None:
        form.add_choice("injury_level", "Injury level", INJURY_LEVELS)
        form.add_choice("medical_assistance_status", "Medical assistance",
                        MEDICAL_ASSISTANCE)
        form.add_entry("hospital_name", "Hospital")
        form.add_entry("hospital_reference", "Hospital reference")
        form.add_entry("special_assistance", "Special assistance needed",
                       placeholder="e.g. Interpreter, wheelchair, child support")

    def _save_medical(self, values: dict[str, Any]) -> None:
        self.repos.victims.update(self.victim_id, **values)

    def _build_statement(self, form: FormPanel) -> None:
        form.add_text("statement", "What the victim says happened", height=260)

    def _save_statement(self, values: dict[str, Any]) -> None:
        self.repos.victims.update(self.victim_id, statement=values.get("statement"))

    # -- child rows ------------------------------------------------------
    def _medical_records(self) -> list[dict]:
        return self.repos.victims.medical_records(self.victim_id)

    def _add_medical_record(self) -> None:
        MedicalRecordDialog(self.app, self.repos, self.victim_id).show()

    def _edit_medical_record(self) -> None:
        self.require_selection(
            "Medical records", "a medical record",
            lambda row: MedicalRecordDialog(
                self.app, self.repos, self.victim_id, row).show())

    def _delete_medical_record(self, row: dict) -> None:
        self.delete_record(
            f"The treatment at '{row['facility']}'",
            lambda: self.repos.victims.delete_medical_record(row["medical_record_id"]))

    def _contacts(self) -> list[dict]:
        return self.repos.victims.contacts(self.victim_id)

    def _add_contact(self) -> None:
        ContactDialog(self.app, self.repos, self.victim_id).show()

    def _edit_contact(self) -> None:
        self.require_selection(
            "Contacts", "a contact entry",
            lambda row: ContactDialog(self.app, self.repos, self.victim_id, row).show())

    def _delete_contact(self, row: dict) -> None:
        self.delete_record(
            f"The {row['contact_type']} contact of {row['contact_datetime']}",
            lambda: self.repos.victims.delete_contact(row["contact_id"]))

    def _compensation(self) -> list[dict]:
        return self.repos.victims.compensation(self.victim_id)

    def _add_compensation(self) -> None:
        CompensationDialog(self.app, self.repos, self.victim_id).show()

    def _edit_compensation(self) -> None:
        self.require_selection(
            "Compensation", "a claim",
            lambda row: CompensationDialog(
                self.app, self.repos, self.victim_id, row).show())

    def _delete_compensation(self, row: dict) -> None:
        self.delete_record(
            f"The '{row['scheme_name']}' claim",
            lambda: self.repos.victims.delete_compensation(row["compensation_id"]))

    # -- header ----------------------------------------------------------
    def _open_case(self) -> None:
        self.app.navigate("cases", case_id=self.record["case_id"])

    def _delete(self) -> None:
        if self.delete_record(
            f"Victim '{self.record['name']}'",
            lambda: self.repos.victims.delete(self.victim_id),
        ):
            self.on_back()


# ----------------------------------------------------------------------
def _medical_columns() -> list[Column]:
    return [
        Column("facility", "Facility", 190),
        Column("treatment_type", "Treatment", 160),
        Column("treating_doctor", "Doctor", 160),
        Column("admitted_datetime", "Admitted", 150),
        Column("discharged_datetime", "Discharged", 150),
        Column("cost_incurred", "Cost", 110, anchor="e"),
        Column("description", "Findings", 240),
    ]


def _contact_columns() -> list[Column]:
    return [
        Column("contact_type", "How", 130),
        Column("contact_datetime", "When", 160),
        Column("made_by_name", "Who", 170),
        Column("purpose", "Purpose", 200),
        Column("outcome", "Outcome", 240),
        Column("follow_up_datetime", "Follow up", 160),
    ]


def _compensation_columns() -> list[Column]:
    return [
        Column("scheme_name", "Scheme", 220),
        Column("compensation_type", "Type", 140),
        Column("status", "Status", 140),
        Column("application_date", "Applied", 120),
        Column("awarded_amount", "Awarded", 110, anchor="e"),
        Column("received_amount", "Received", 110, anchor="e"),
        Column("sanctioning_authority", "Sanctioned by", 180),
        Column("order_reference", "Order", 140),
    ]
