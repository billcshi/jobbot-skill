#!/usr/bin/env python3
"""Validate agent-written job-match judgments and calculate a transparent score."""

from __future__ import annotations

import argparse
import json
import math
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from jobbot_skill import (
    UserError, job_dir, load_agent_policy, load_valid_profile, now_iso, parse_timestamp, read_job_metadata,
    read_json, require_dict, require_list, require_string, sha256_file, validate_jd,
    validate_preferences, workspace_path, write_json,
)
from workspace_fs import mkdir as make_dirs, write_bytes as save_bytes

WEIGHTS = {"role_alignment": 0.30, "skills": 0.25, "location": 0.20,
           "industry": 0.15, "experience_level": 0.10}


def strings(value, label):
    return [require_string(item, label) for item in require_list(value, label)]


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1 or not math.isfinite(value):
        raise UserError(f"{label} must be a finite number between 0 and 1")
    return value


def bindings(workspace, directory):
    return {
        "profile_sha256": sha256_file(workspace / "profile.json"),
        "preferences_sha256": sha256_file(workspace / "preferences.json"),
        "jd_sha256": sha256_file(directory / "jd.json"),
        "job_status_sha256": sha256_file(directory / "job.json") if (directory / "job.json").exists() else None,
    }


def calculate(record, evidence, source_uncertain=False, not_current=False):
    if record.get("schema_version") != 1 or record.get("rubric_version") != "jobbot-match-v1":
        raise UserError("Unsupported match schema/rubric version")
    dimensions = require_list(record.get("dimensions"), "match.dimensions")
    seen = set()
    scored_weight = unknown_weight = weighted = total_weight = 0.0
    has_unknown_dimension = False
    for value in dimensions:
        item = require_dict(value, "dimension")
        identifier = item.get("id")
        if not isinstance(identifier, str) or identifier not in WEIGHTS or identifier in seen:
            raise UserError("Each rubric dimension must appear exactly once")
        seen.add(identifier)
        weight = number(item.get("weight"), "dimension.weight")
        total_weight += weight
        require_string(item.get("reason"), "dimension.reason")
        profile_ids = strings(item.get("profile_evidence_ids"), "dimension.profile_evidence_ids")
        if any(identifier not in evidence for identifier in profile_ids):
            raise UserError("Dimension cites unknown profile evidence IDs")
        job_refs = strings(item.get("job_references"), "dimension.job_references")
        status = item.get("status")
        if "value" not in item:
            raise UserError("dimension.value is required, including an explicit null for unknown/not-applicable dimensions")
        if not isinstance(status, str):
            raise UserError("Dimension status must be a string")
        if status == "scored":
            score = number(item.get("value"), "dimension.value")
            if not job_refs:
                raise UserError("A scored dimension needs job/source references")
            if score > 0 and identifier in {"role_alignment", "skills", "experience_level"} and not profile_ids:
                raise UserError("Positive capability alignment needs profile evidence IDs")
            weighted += weight * score
            scored_weight += weight
        elif status in {"unknown", "not_applicable"}:
            if item.get("value") is not None:
                raise UserError("Unknown/not-applicable dimensions must have a null value")
            if status == "unknown":
                has_unknown_dimension = True
                unknown_weight += weight
        else:
            raise UserError("Dimension status must be scored, unknown, or not_applicable")
    if seen != set(WEIGHTS) or not math.isclose(total_weight, 1.0, abs_tol=1e-9):
        raise UserError("All rubric dimensions are required and their weights must sum to 1")
    constraint_states = []
    for value in require_list(record.get("hard_constraints"), "match.hard_constraints"):
        item = require_dict(value, "constraint")
        require_string(item.get("constraint"), "constraint.constraint")
        require_string(item.get("reason"), "constraint.reason")
        if not strings(item.get("source_refs"), "constraint.source_refs"):
            raise UserError("A hard-constraint judgment needs source references")
        state = item.get("status")
        if not isinstance(state, str) or state not in {"met", "violated", "unknown"}:
            raise UserError("Constraint status must be met, violated, or unknown")
        constraint_states.append(state)
    for field in ("strengths", "gaps", "unresolved"):
        strings(record.get(field), f"match.{field}")
    eligibility = "ineligible" if "violated" in constraint_states else "unknown" if "unknown" in constraint_states else "eligible"
    raw_score = 100 * weighted / scored_weight if scored_weight else None
    coverage = scored_weight / (scored_weight + unknown_weight) if scored_weight + unknown_weight else None
    if eligibility == "ineligible":
        raw_score = None
    if raw_score is not None:
        raw_score = round(raw_score, 2)
    tier = next((tier for cutoff, tier in ((80, "A"), (65, "B"), (50, "C"), (0, "D")) if raw_score >= cutoff), None) if raw_score is not None else None
    status = ("ineligible" if eligibility == "ineligible" else "not_current" if not_current else
              "insufficient" if raw_score is None else "provisional" if has_unknown_dimension or eligibility == "unknown" or source_uncertain else "complete")
    return {"score": round(raw_score, 2) if raw_score is not None else None,
            "tier": tier, "coverage": round(coverage, 4) if coverage is not None else None,
            "eligibility": eligibility, "assessment_status": status}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--prepare", action="store_true", help="Prepare agent-written dimension/constraint judgments")
    parser.add_argument("--force", action="store_true", help="With --prepare, archive an existing assessment before replacing it")
    parser.add_argument("--import-judgments", help="Validate a scoring worker's isolated JSON result and publish it to match.json")
    parser.add_argument("--verify", action="store_true", help="Read-only validation of bindings and the saved derived result")
    args = parser.parse_args()
    try:
        if args.verify and (args.prepare or args.force or args.import_judgments):
            raise UserError("--verify cannot be combined with mutation options")
        workspace = workspace_path(args.workspace)
        directory = job_dir(workspace, args.job)
        _, evidence = load_valid_profile(workspace)
        validate_preferences(workspace)
        validate_jd(directory)
        current_bindings = bindings(workspace, directory)
        path = directory / "match.json"
        if args.prepare:
            if args.import_judgments:
                raise UserError("--prepare cannot be combined with --import-judgments")
            load_agent_policy(workspace)
            if path.exists():
                if not args.force:
                    raise UserError("Match assessment exists; --prepare --force archives it before replacement")
                history = directory / "match-history"
                make_dirs(history)
                save_bytes(history / f"match-{uuid.uuid4().hex}.json", path.read_bytes())
            write_json(path, {
                "schema_version": 1, "rubric_version": "jobbot-match-v1", "job_id": args.job,
                **current_bindings, "prepared_at": now_iso(), "hard_constraints": [],
                "dimensions": [{"id": identifier, "weight": weight, "status": "unknown", "value": None,
                                "reason": "", "profile_evidence_ids": [], "job_references": []}
                               for identifier, weight in WEIGHTS.items()],
                "strengths": [], "gaps": [], "unresolved": [],
            })
            print(f"Prepared match assessment: {path}; the agent supplies evidence-based judgments.")
            return 0
        if args.force:
            raise UserError("--force is only valid with --prepare")
        if args.import_judgments:
            imported_path = Path(args.import_judgments).expanduser().resolve()
            if not imported_path.is_relative_to(workspace):
                raise UserError("Scoring-worker results must be inside the selected workspace")
            if imported_path == path.resolve():
                raise UserError("Worker result must be a separate staging file, not canonical match.json")
            imported_digest = sha256_file(imported_path)
            record = read_json(imported_path)
        else:
            canonical_digest = sha256_file(path)
            record = read_json(path)
        required = {"schema_version", "rubric_version", "job_id", "profile_sha256", "preferences_sha256",
                    "jd_sha256", "job_status_sha256", "prepared_at", "hard_constraints", "dimensions",
                    "strengths", "gaps", "unresolved"}
        if required - record.keys():
            raise UserError("Match assessment is missing required fields")
        parse_timestamp(record["prepared_at"], "match.prepared_at")
        if record.get("job_id") != args.job:
            raise UserError("match.job_id does not match the selected job")
        for key, value in current_bindings.items():
            if record.get(key) != value:
                raise UserError(f"Stale match assessment: {key} changed; reassess current inputs")
        uncertain, not_current = True, False
        if (directory / "job.json").exists():
            metadata = read_job_metadata(directory)
            now = datetime.now(timezone.utc)
            expired = not metadata["expires_at"] or now >= parse_timestamp(metadata["expires_at"], "job.expires_at")
            not_current = metadata["availability"] == "closed" or bool(metadata["application_deadline"] and now >= parse_timestamp(metadata["application_deadline"], "deadline"))
            uncertain = expired or metadata["availability"] == "unknown"
        calculated = calculate(record, evidence, uncertain, not_current)
        unchanged = all(key in record and record[key] == value for key, value in calculated.items()) and bool(record.get("scored_at"))
        if record.get("scored_at"):
            parse_timestamp(record["scored_at"], "match.scored_at")
        if args.verify and not unchanged:
            raise UserError("Saved match result needs recalculation; --verify never modifies it")
        if not args.verify and (args.import_judgments or not unchanged):
            record.update(calculated)
            record["scored_at"] = now_iso()
        if args.import_judgments:
            if sha256_file(imported_path) != imported_digest:
                raise UserError("Scoring-worker result changed during validation; wait for the worker to finish")
            record["judgment_source"] = {"path": str(imported_path.relative_to(workspace)), "sha256": imported_digest}
        if bindings(workspace, directory) != current_bindings:
            raise UserError("Scoring inputs changed during validation; reassess before publication")
        if not args.import_judgments and sha256_file(path) != canonical_digest:
            raise UserError("Canonical assessment changed during validation; retry the check")
        if not args.verify and (args.import_judgments or not unchanged):
            if path.exists():
                history = directory / "match-history"
                make_dirs(history)
                save_bytes(history / f"match-{uuid.uuid4().hex}.json", path.read_bytes())
            write_json(path, record)
        print(json.dumps({key: record[key] for key in ("score", "tier", "coverage", "eligibility", "assessment_status", "strengths", "gaps", "unresolved")}, ensure_ascii=False, indent=2))
        return 0
    except (UserError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
