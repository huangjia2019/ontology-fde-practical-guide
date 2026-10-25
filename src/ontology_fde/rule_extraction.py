from __future__ import annotations

import re
import hashlib
import math
from copy import deepcopy
from typing import Any

from .paths import load_structured


class RuleLifecycleError(RuntimeError):
    pass


class OntologyGuidedRuleDemo:
    """Offline document → neutral Rule Draft demo.

    It intentionally does not pretend to be a general NLP system.  A deterministic extractor
    makes every mapping and limitation visible, which is more useful for governance tests.
    """

    def __init__(self) -> None:
        self.corpus = load_structured(
            "data/mock/documents/refund_policy_corpus.json"
        )
        self.expected_template = load_structured(
            "config/rules/drafts/opened_consumable_rule_draft.json"
        )
        self.test_suite = load_structured(
            "config/evals/document_rule_cases.json"
        )

    def extract(self) -> dict[str, Any]:
        policy = next(
            doc for doc in self.corpus["documents"] if doc["document_type"] == "approved_policy"
        )
        observations = [
            doc for doc in self.corpus["documents"] if doc["document_type"] == "expert_observation"
        ]
        match = re.search(
            r"more than\s*(\d+)\s*hours", policy["text"], flags=re.IGNORECASE
        )
        if not match:
            raise ValueError("Policy has no machine-detectable hour threshold")
        threshold = int(match.group(1))
        if "opened consumables" not in policy["text"].lower() or "b2c" not in policy["text"].lower():
            raise ValueError("Policy cannot be bound to the scoped ontology concepts")

        draft = deepcopy(self.expected_template)
        draft["conditions"] = [
            "customer_channel == b2c",
            "item_category == opened_consumable",
            f"hours_between(signed_at, request_opened_at) > {threshold}",
        ]
        draft["provenance"] = [
            {
                "document_id": policy["document_id"],
                "document_type": policy["document_type"],
                "support": "normative",
                "source_locator": "policy:paragraph-1",
                "source_hash_prefix": hashlib.sha256(policy["text"].encode("utf-8")).hexdigest()[:12],
            },
            *[
                {
                    "document_id": doc["document_id"],
                    "document_type": doc["document_type"],
                    "support": "corroborating",
                    "source_locator": "ticket:body",
                    "source_hash_prefix": hashlib.sha256(doc["text"].encode("utf-8")).hexdigest()[:12],
                }
                for doc in observations
            ],
        ]
        return draft

    def validate(self, draft: dict[str, Any] | None = None) -> dict[str, Any]:
        draft = draft or self.extract()
        structural = self._validate_structural(draft)
        semantic = self._validate_semantic(draft)
        operational = self._validate_operational(draft)
        epistemic = self._validate_epistemic(draft)
        sections = {
            "structural": structural,
            "semantic": semantic,
            "operational": operational,
            "epistemic": epistemic,
        }
        validation_complete = all(section["passed"] for section in sections.values())
        blockers = []
        if draft.get("missing_inputs"):
            blockers.append("missing_inputs_not_resolved")
        if draft.get("review_required"):
            blockers.append("human_review_not_completed")
        if draft.get("lifecycle", {}).get("state") != "compiled":
            blockers.append("rule_not_compiled")
        return {
            "passed": validation_complete,
            "validation_complete": validation_complete,
            "production_ready": validation_complete and not blockers,
            "production_blockers": blockers,
            "validation_types": sections,
            "test_kinds": sorted({case["kind"] for case in operational["cases"]}),
        }

    def _validate_structural(self, draft: dict[str, Any]) -> dict[str, Any]:
        required = {
            "rule_id", "knowledge_layers", "scope", "ontology_bindings", "data_bindings",
            "inputs", "conditions", "conclusion", "provenance", "missing_inputs",
            "epistemic_status", "review_required", "lifecycle",
        }
        missing = sorted(required - draft.keys())
        binding_fields = {"source", "type", "unit", "freshness", "owner", "missing_policy"}
        bad_bindings = [
            row.get("input", "<unknown>")
            for row in draft.get("data_bindings", [])
            if not binding_fields.issubset(row)
        ]
        checks = {
            "required_fields_present": not missing,
            "three_knowledge_layers": set(draft.get("knowledge_layers", {}))
            == {"general", "context", "decision"},
            "data_bindings_complete": not bad_bindings,
            "lifecycle_declared": draft.get("lifecycle", {}).get("state") == "draft",
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "missing_fields": missing,
            "invalid_data_bindings": bad_bindings,
        }

    def _validate_semantic(self, draft: dict[str, Any]) -> dict[str, Any]:
        object_catalog = load_structured("config/ontology/objects.yaml")
        known_objects = {
            row["name"]
            for group in ("core_objects", "supporting_objects")
            for row in object_catalog[group]
        }
        known_actions = {
            load_structured(path)["action_id"]
            for path in (
                "config/actions/approve_refund_small.yaml",
                "config/actions/request_human_refund_approval.yaml",
                "config/actions/request_missing_evidence.yaml",
            )
        }
        bad_bindings = []
        for binding in draft["ontology_bindings"].values():
            prefix, value = binding.split(".", 1)
            if prefix == "Action":
                if value not in known_actions:
                    bad_bindings.append(binding)
            elif prefix not in known_objects:
                bad_bindings.append(binding)
        bound_inputs = {row["input"] for row in draft["data_bindings"]}
        checks = {
            "ontology_bindings_resolve": not bad_bindings,
            "inputs_have_data_bindings": set(draft["inputs"]).issubset(bound_inputs),
            "scope_is_narrow": draft["scope"]["in_scope"]["channel"] == ["b2c"],
            "conclusion_is_neutral_routing": draft["conclusion"]["action"]
            == "request_human_refund_approval",
        }
        return {"passed": all(checks.values()), "checks": checks, "unresolved": bad_bindings}

    def _validate_operational(self, draft: dict[str, Any]) -> dict[str, Any]:
        results = []
        for case in self.test_suite["cases"]:
            actual = self.evaluate_candidate(draft, case["given"])
            results.append(
                {
                    **case,
                    "actual": actual,
                    "passed": actual == case["expect"],
                }
            )
        return {"passed": bool(results) and all(row["passed"] for row in results), "cases": results}

    def _validate_epistemic(self, draft: dict[str, Any]) -> dict[str, Any]:
        policy = next(
            doc for doc in self.corpus["documents"] if doc["document_type"] == "approved_policy"
        )
        checks = {
            "normative_provenance_present": any(
                row["document_type"] == "approved_policy" and row["support"] == "normative"
                for row in draft["provenance"]
            ),
            "source_locator_and_hash_present": all(
                row.get("source_locator") and row.get("source_hash_prefix")
                for row in draft["provenance"]
            ),
            "candidate_not_claimed_as_approved": draft["epistemic_status"].startswith("candidate"),
            "human_review_required": draft["review_required"] is True,
            "known_gap_declared": bool(draft["missing_inputs"]),
            "conclusion_not_stronger_than_source": (
                "must be routed to a customer service supervisor for human review"
                in policy["text"].lower()
                and draft["conclusion"]["action"] == "request_human_refund_approval"
            ),
        }
        return {"passed": all(checks.values()), "checks": checks}

    @staticmethod
    def evaluate_candidate(draft: dict[str, Any], facts: dict[str, Any]) -> str:
        """Evaluate a draft only inside the validation sandbox, never as a production action."""

        channel = str(facts.get("customer_channel", "unknown")).lower()
        if channel != "b2c":
            return "out_of_scope"
        hours = facts.get("hours_since_signed")
        if hours is None:
            return "missing_data"
        if facts.get("item_category") != "opened_consumable":
            return "no_match"
        try:
            elapsed = float(hours)
        except (TypeError, ValueError):
            return "missing_data"
        if not math.isfinite(elapsed) or elapsed < 0:
            return "missing_data"
        # This adapter supports one explicit condition, not an arbitrary DSL.
        # Read the extracted threshold rather than silently using a second copy.
        thresholds = [
            int(match.group(1))
            for condition in draft.get("conditions", [])
            if (match := re.fullmatch(
                r"hours_between\(signed_at, request_opened_at\) > (\d+)", condition
            ))
        ]
        if len(thresholds) != 1:
            raise RuleLifecycleError("Expected one supported elapsed-hours condition")
        return "match" if elapsed > thresholds[0] else "no_match"

    @staticmethod
    def execute_rule(draft: dict[str, Any], facts: dict[str, Any]) -> str:
        if draft.get("missing_inputs"):
            raise RuleLifecycleError(
                f"Rule has unresolved missing_inputs: {draft['missing_inputs']}"
            )
        state = draft.get("lifecycle", {}).get("state")
        allowed = draft.get("lifecycle", {}).get("execution_allowed_states", [])
        if state != "compiled" or state not in allowed:
            raise RuleLifecycleError(
                f"Rule state {state!r} cannot execute; required one of {allowed}"
            )
        if draft.get("review_required") is not False or not draft["lifecycle"].get("approved_by"):
            raise RuleLifecycleError("Rule has no completed human-review record")
        return OntologyGuidedRuleDemo.evaluate_candidate(draft, facts)

    @staticmethod
    def approve_rule(
        draft: dict[str, Any], *, reviewer: str, resolved_missing_inputs: list[str]
    ) -> dict[str, Any]:
        if draft.get("lifecycle", {}).get("state") != "draft":
            raise RuleLifecycleError("Only a draft rule can be approved")
        if not reviewer.strip():
            raise RuleLifecycleError("A reviewer must be named")
        approved = deepcopy(draft)
        unresolved = set(approved.get("missing_inputs", [])) - set(resolved_missing_inputs)
        if unresolved:
            raise RuleLifecycleError(f"Cannot approve; unresolved missing_inputs: {sorted(unresolved)}")
        approved["missing_inputs"] = []
        approved["review_required"] = False
        approved["lifecycle"]["state"] = "approved"
        approved["lifecycle"]["approved_by"] = reviewer
        return approved

    @staticmethod
    def compile_rule(draft: dict[str, Any]) -> dict[str, Any]:
        if draft.get("missing_inputs"):
            raise RuleLifecycleError("Cannot compile a rule with unresolved missing_inputs")
        if draft.get("lifecycle", {}).get("state") != "approved":
            raise RuleLifecycleError("Only an approved rule can be compiled")
        if draft.get("review_required") is not False or not draft["lifecycle"].get("approved_by"):
            raise RuleLifecycleError("Cannot compile without a completed human-review record")
        compiled = deepcopy(draft)
        compiled["lifecycle"]["state"] = "compiled"
        return compiled

    @staticmethod
    def retire_rule(rule: dict[str, Any]) -> dict[str, Any]:
        retired = deepcopy(rule)
        retired["lifecycle"]["state"] = "retired"
        return retired

    def run_demo(self) -> dict[str, Any]:
        draft = self.extract()
        validation = self.validate(draft)
        try:
            self.execute_rule(
                draft,
                {"customer_channel": "b2c", "item_category": "opened_consumable", "hours_since_signed": 25},
            )
        except RuleLifecycleError as error:
            execution_guard = {"passed": True, "message": str(error)}
        else:
            execution_guard = {"passed": False, "message": "Candidate draft executed unexpectedly"}
        return {
            "source_documents": [
                {"document_id": row["document_id"], "title": row["title"], "type": row["document_type"]}
                for row in self.corpus["documents"]
            ],
            "draft": draft,
            "validation": validation,
            "candidate_execution_guard": execution_guard,
        }
