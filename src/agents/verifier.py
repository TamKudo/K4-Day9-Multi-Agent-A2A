"""Pre-submission gate. Raises on any contract violation; never edits output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..schemas import CaseInput, CaseOutput, ContractError

TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
EVIDENCE_PATTERN = re.compile(
    r"^(?:order:(?P<order>[^:]+)"
    r"|item:(?P<item>[^:]+:[^:]+)"
    r"|payment:(?P<payment>[^:]+:[^:]+)"
    r"|seller:(?P<seller>[^:]+)"
    r"|policy:(?P<policy>[A-Z_]+))$"
)

MONEY_FIELDS = ("item_total_brl", "freight_total_brl", "expected_total_brl",
                "payment_total_brl", "difference_brl")
TIMESTAMP_FIELDS = ("delivered_at", "estimated_delivery_at", "carrier_handoff_at")
ITEM_DEPENDENT_FIELDS = ("expected_total_brl", "difference_brl", "reconciled")

VALID_STATUSES = {"action_required", "no_action"}
VALID_PARTY_TYPES = {"seller", "logistics_provider", "platform"}
VALID_CAUSE_CODES = {
    "SELLER_HANDOFF_AFTER_LIMIT", "CARRIER_DELIVERED_AFTER_ESTIMATE",
    "ORDER_CANCELED_AFTER_PAYMENT", "ORDER_UNAVAILABLE_AFTER_PAYMENT",
    "MULTIPLE_PAYMENTS_RECONCILED", "DELIVERY_WITHIN_ESTIMATE",
}


class VerificationError(ContractError):
    """Raised when an assembled output fails verification.

    Carries every violation found so a failing case can be fixed in one pass
    instead of one error per run.
    """

    def __init__(self, case_id: str, violations: Sequence[str]) -> None:
        self.case_id = case_id
        self.violations = list(violations)
        detail = "; ".join(self.violations)
        super().__init__(f"{case_id}: {detail}")


@dataclass
class OutputVerifier:
    """Checks an assembled :class:`CaseOutput` before it reaches disk.

    The verifier owns no repairs: it either returns ``None`` or raises.  Array
    truncation belongs to ``CaseOutput.validate_limits`` and the coordinator.
    """

    strict_evidence: bool = True
    _violations: List[str] = field(default_factory=list, init=False, repr=False)

    def verify(self, case: CaseInput, output: CaseOutput) -> None:
        violations = self.collect(case, output)
        if violations:
            raise VerificationError(case.case_id, violations)

    def collect(self, case: CaseInput, output: CaseOutput) -> List[str]:
        """Return every violation found, without raising."""
        self._violations = []
        payload = output.to_dict()

        if payload["case_id"] != case.case_id:
            self._fail(f"case_id {payload['case_id']} does not match input {case.case_id}")

        self._check_entities(case, payload)
        self._check_assessment(payload)
        self._check_payment(payload)
        self._check_delivery(payload)
        self._check_root_cause(payload)
        self._check_financials(payload)
        self._check_evidence(case, payload)
        return list(self._violations)

    def _fail(self, message: str) -> None:
        self._violations.append(message)

    # -- affected entities ------------------------------------------------
    def _check_entities(self, case: CaseInput, payload: Dict[str, Any]) -> None:
        entities = payload["affected_entities"]
        claimed = case.customer_request.claimed_order_id
        if entities["order_ids"] != [claimed]:
            self._fail(
                f"order_ids must be exactly [{claimed}], got {entities['order_ids']}"
            )

        related = payload["customer_context"]["related_order_ids"]
        leaked = [order_id for order_id in related if order_id in entities["order_ids"]]
        if leaked:
            self._fail(f"historical orders leaked into affected_entities: {leaked}")

        for item_id in entities["item_ids"]:
            if not _is_composite(item_id, claimed):
                self._fail(f"item_id {item_id} is not <claimed_order_id>:<order_item_id>")
        for payment_id in entities["payment_ids"]:
            if not _is_composite(payment_id, claimed):
                self._fail(
                    f"payment_id {payment_id} is not <claimed_order_id>:<sequential>"
                )

        for name, values in entities.items():
            if len(values) != len(set(values)):
                self._fail(f"{name} contains duplicates")

    # -- assessment -------------------------------------------------------
    def _check_assessment(self, payload: Dict[str, Any]) -> None:
        assessment = payload["case_assessment"]
        if assessment["case_status"] not in VALID_STATUSES:
            self._fail(f"unknown case_status {assessment['case_status']}")

        confidence = assessment["confidence"]
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            self._fail(f"confidence {confidence} outside [0, 1]")
        self._check_rounded("confidence", confidence)

        issues = assessment["secondary_issues"]
        if len(issues) != len(set(issues)):
            self._fail("secondary_issues contains duplicates")

        refund = payload["financial_resolution"]["recommended_refund_brl"]
        expected_status = "action_required" if refund > 0 else "no_action"
        if assessment["case_status"] != expected_status:
            self._fail(
                f"case_status {assessment['case_status']} contradicts refund {refund}"
            )

    # -- payment reconciliation -------------------------------------------
    def _check_payment(self, payload: Dict[str, Any]) -> None:
        reconciliation = payload["payment_reconciliation"]
        if reconciliation["currency"] != "BRL":
            self._fail(f"currency must be BRL, got {reconciliation['currency']}")

        for name in MONEY_FIELDS:
            self._check_optional_number(f"payment_reconciliation.{name}",
                                        reconciliation[name])

        # Order without item rows: the item-dependent totals must be null.
        if not payload["affected_entities"]["item_ids"]:
            for name in ITEM_DEPENDENT_FIELDS:
                value = reconciliation[name]
                if value is not None:
                    self._fail(
                        f"{name} must be null for an order without items, got {value!r}"
                    )
            for name in ("item_total_brl", "freight_total_brl"):
                if reconciliation[name] is not None:
                    self._fail(f"{name} must be null for an order without items")
        else:
            reconciled = reconciliation["reconciled"]
            if not isinstance(reconciled, bool):
                self._fail(f"reconciled must be a boolean, got {reconciled!r}")

        types = reconciliation["payment_types"]
        if not isinstance(types, list) or any(not isinstance(item, str) for item in types):
            self._fail("payment_types must be a list of strings")

    # -- delivery ---------------------------------------------------------
    def _check_delivery(self, payload: Dict[str, Any]) -> None:
        delivery = payload["delivery_analysis"]
        for name in TIMESTAMP_FIELDS:
            self._check_timestamp(f"delivery_analysis.{name}", delivery[name])
        self._check_optional_number("delivery_variance_hours",
                                    delivery["delivery_variance_hours"])

        seller_ids = payload["affected_entities"]["seller_ids"]
        for entry in delivery["seller_handoff_analysis"]:
            self._check_timestamp("shipping_limit_at", entry["shipping_limit_at"])
            self._check_optional_number("handoff_variance_hours",
                                        entry["handoff_variance_hours"])
            if not isinstance(entry["late_handoff"], bool):
                self._fail(f"late_handoff must be a boolean, got {entry['late_handoff']!r}")
            if entry["seller_id"] not in seller_ids:
                self._fail(
                    f"handoff seller {entry['seller_id']} is missing from seller_ids"
                )

        analysed = {entry["seller_id"] for entry in delivery["seller_handoff_analysis"]
                    if entry["late_handoff"]}
        for seller_id in delivery["late_handoff_seller_ids"]:
            if seller_id not in analysed:
                self._fail(
                    f"late seller {seller_id} is not marked late in seller_handoff_analysis"
                )

    # -- root cause -------------------------------------------------------
    def _check_root_cause(self, payload: Dict[str, Any]) -> None:
        analysis = payload["root_cause_analysis"]
        ranks = [cause["rank"] for cause in analysis["ranked_causes"]]
        if ranks != list(range(1, len(ranks) + 1)):
            self._fail(f"ranked_causes ranks must start at 1 and be dense, got {ranks}")
        for cause in analysis["ranked_causes"]:
            if cause["cause_code"] not in VALID_CAUSE_CODES:
                self._fail(f"unknown cause_code {cause['cause_code']}")

        seller_ids = payload["affected_entities"]["seller_ids"]
        for party in analysis["responsible_parties"]:
            if party["party_type"] not in VALID_PARTY_TYPES:
                self._fail(f"unknown party_type {party['party_type']}")
            if party["party_type"] == "seller" and party["party_id"] not in seller_ids:
                self._fail(
                    f"responsible seller {party['party_id']} is missing from seller_ids"
                )

    # -- money ------------------------------------------------------------
    def _check_financials(self, payload: Dict[str, Any]) -> None:
        resolution = payload["financial_resolution"]
        if resolution["currency"] != "BRL":
            self._fail(f"financial currency must be BRL, got {resolution['currency']}")
        refund = resolution["recommended_refund_brl"]
        if not isinstance(refund, (int, float)) or isinstance(refund, bool):
            self._fail(f"recommended_refund_brl must be numeric, got {refund!r}")
            return
        if refund < 0:
            self._fail(f"recommended_refund_brl must not be negative, got {refund}")
        self._check_rounded("recommended_refund_brl", refund)

    # -- evidence ---------------------------------------------------------
    def _check_evidence(self, case: CaseInput, payload: Dict[str, Any]) -> None:
        evidence_ids = payload["evidence_ids"]
        if len(evidence_ids) != len(set(evidence_ids)):
            self._fail("evidence_ids contains duplicates")

        entities = payload["affected_entities"]
        known_causes = {
            cause["cause_code"] for cause in payload["root_cause_analysis"]["ranked_causes"]
        }
        for evidence_id in evidence_ids:
            match = EVIDENCE_PATTERN.match(evidence_id)
            if match is None:
                self._fail(f"evidence {evidence_id!r} does not match any allowed form")
                continue
            if not self.strict_evidence:
                continue
            self._check_evidence_target(evidence_id, match, case, entities, known_causes)

    def _check_evidence_target(
        self,
        evidence_id: str,
        match: "re.Match[str]",
        case: CaseInput,
        entities: Dict[str, Any],
        known_causes: set,
    ) -> None:
        """Rebuild the referenced entity from case data, not by string shape."""
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "order" and value != case.customer_request.claimed_order_id:
            self._fail(f"evidence {evidence_id} references an unknown order")
        elif kind == "item" and value not in entities["item_ids"]:
            self._fail(f"evidence {evidence_id} references an item outside item_ids")
        elif kind == "payment" and value not in entities["payment_ids"]:
            self._fail(f"evidence {evidence_id} references a payment outside payment_ids")
        elif kind == "seller" and value not in entities["seller_ids"]:
            self._fail(f"evidence {evidence_id} references a seller outside seller_ids")
        elif kind == "policy" and value not in known_causes:
            self._fail(f"evidence {evidence_id} references a cause outside ranked_causes")

    # -- shared field checks ----------------------------------------------
    def _check_timestamp(self, name: str, value: Optional[str]) -> None:
        if value is None:
            return
        if not isinstance(value, str) or not TIMESTAMP_PATTERN.match(value):
            self._fail(f"{name} must be 'YYYY-MM-DD HH:MM:SS' or null, got {value!r}")

    def _check_optional_number(self, name: str, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            self._fail(f"{name} must be numeric or null, got {value!r}")
            return
        self._check_rounded(name, value)

    def _check_rounded(self, name: str, value: Any) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value != round(value, 2):
                self._fail(f"{name} must be rounded to 2 decimals, got {value}")


def _is_composite(value: Any, order_id: str) -> bool:
    return isinstance(value, str) and value.startswith(f"{order_id}:") \
        and len(value.split(":")) == 2 and value.split(":")[1] != ""
