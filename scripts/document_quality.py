#!/usr/bin/env python3
"""Prepare frozen document reviews and enforce a bounded score/feedback loop."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import uuid
from pathlib import Path

from jobbot_skill import (
    UserError, evidence_snapshot, job_dir, load_document_quality_policy, load_evidence_sources, load_valid_resume, now_iso,
    read_json, require_dict, require_list, require_string, sha256_file,
    workspace_path, write_json, retain_file, sha256_bytes,
)

from workspace_fs import OBJECTS_DIRECTORY, guard, mkdir as make_dirs, write_bytes as save_bytes, readonly


def inside(workspace, path):
    if not path.resolve().is_relative_to(workspace):
        raise UserError("Quality-review files must remain inside the workspace")
    return guard(path)


def current_files(workspace, directory):
    profile, jd, _ = load_valid_resume(workspace, directory)
    audit = read_json(directory / "audit.json")
    artifacts = read_json(directory / "artifacts.json")
    if audit.get("job_id") != directory.name:
        raise UserError("Prepared audit belongs to another job")
    bound = {"profile_sha256": workspace / "profile.json", "market_sha256": workspace / "market.json",
             "jd_sha256": directory / "jd.json", "resume_json_sha256": directory / "resume.json",
             "latex_sha256": directory / "resume.tex", "pdf_sha256": directory / "resume.pdf"}
    for key, path in bound.items():
        if audit.get(key) != sha256_file(path) or artifacts.get(key) != sha256_file(path):
            raise UserError(f"Stale prepared document for {key}; render and prepare-audit again")
    pages = require_list(audit.get("pages"), "audit.pages")
    expected = [str(path.relative_to(directory)) for path in sorted((directory / "audit-pages").glob("page-*.png"))]
    if not pages or pages != expected:
        raise UserError("Prepared audit must list every current page image")
    files = list(bound.values()) + [workspace / "preferences.json", directory / "artifacts.json", directory / "resume.txt"]
    files.extend(path for path in (workspace / "writing-rules.json", directory / "render-inputs.json",
                                   directory / "selection.json", directory / "quantification.json") if path.is_file())
    files.extend(path for path in (directory / "source.html", directory / "source.txt") if path.is_file())
    files.extend(directory / item["path"] for item in jd.get("attachments", []))
    manifest = workspace / "evidence" / "manifest.json"
    if manifest.exists():
        files.append(manifest)
        used_sources = set()
        def source_ids(value):
            if isinstance(value, dict):
                used_sources.update(value.get("source_ids", []))
                for child in value.values():
                    source_ids(child)
            elif isinstance(value, list):
                for child in value:
                    source_ids(child)
        source_ids(profile)
        for identifier, source in load_evidence_sources(workspace).items():
            if identifier in used_sources and source["type"] != "user_statement":
                _, paths = evidence_snapshot(workspace, source)
                files.extend(workspace / path for path in paths)
                notes = workspace / "evidence" / "reviews" / f"{identifier}.json"
                if notes.exists():
                    files.append(notes)
    files.extend(directory / page for page in pages)
    for path in files:
        inside(workspace, path)
    return list(dict.fromkeys(files)), {page: sha256_file(directory / page) for page in pages}


def loop_state(workspace, directory):
    state = read_json(inside(workspace, directory / "quality-loop.json"))
    if state.get("job_id") != directory.name or state.get("schema_version") not in {1, 2}:
        raise UserError("Invalid quality-loop state")
    state["schema_version"] = 2
    state.setdefault("document_id", "legacy-" + directory.name)
    state.setdefault("producer_ids", [state["writer_id"]])
    state.setdefault("round_limit", state["policy"]["max_rewrites"] + 1)
    state.setdefault("events", [])
    state.setdefault("versions", [{"id": "legacy", "parent_id": None, "start_round": 0, "reason": "Original document"}])
    return state


def save_state(directory, state):
    retain_file(directory / "quality-loop.json")
    write_json(directory / "quality-loop.json", state)


def handoff(workspace, directory, writer_id, reason):
    writer_id = require_string(writer_id, "writer ID")
    reason = require_string(reason, "handoff reason")
    state = loop_state(workspace, directory)
    previous = state["writer_id"]
    if previous != writer_id:
        state["writer_id"] = writer_id
        state["producer_ids"] = sorted(set(state["producer_ids"]) | {previous, writer_id})
        state["events"].append({"type": "handoff", "from": previous, "to": writer_id,
                                "reason": reason, "at": now_iso(), "rounds_used": len(state["rounds"])})
        save_state(directory, state)
    print(json.dumps({"document_id": state["document_id"], "writer_id": state["writer_id"],
                      "rounds_used": len(state["rounds"]), "round_limit": state["round_limit"]}))


def context_names(workspace, directory, names):
    generated = {str((directory / name).relative_to(workspace)) for name in
                 ("resume.json", "resume.tex", "resume.pdf", "resume.txt", "artifacts.json", "render-inputs.json")}
    pages = directory / "audit-pages"
    return {raw for raw in names if raw not in generated and not (workspace / raw).is_relative_to(pages)}


def context_hashes(workspace, directory, files):
    names = context_names(workspace, directory, (str(path.relative_to(workspace)) for path in files))
    return {raw: sha256_file(workspace / raw) for raw in names}


def effective_input_hash(path, original, resume_name):
    """A change detector, separate from exact-byte provenance and approval."""
    if Path(original).suffix.lower() != '.json':
        return sha256_file(path)
    data = path.read_bytes()
    try:
        value = json.loads(data)
        if original == resume_name and isinstance(value, dict):
            # These validated exact-byte bindings are not writing content.
            value = {key: item for key, item in value.items() if key not in
                     {'profile_sha256', 'market_sha256', 'jd_sha256', 'writing_rules_sha256'}}
        canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (ValueError, UnicodeDecodeError):
        # Unstructured/malformed imported JSON remains exact-byte source data.
        return sha256_bytes(data)
    return sha256_bytes(canonical.encode('utf-8'))


def effective_inputs(workspace, originals, names, resume_name):
    return {raw: effective_input_hash(inside(workspace, originals[raw]), raw, resume_name) for raw in names}


def freeze_file(workspace, original):
    data = original.read_bytes()
    digest = sha256_bytes(data)
    blob = inside(workspace, workspace / OBJECTS_DIRECTORY / "sha256" / digest[:2] / digest)
    if blob.exists():
        if sha256_file(blob) != digest:
            raise UserError("Content-addressed snapshot is corrupt; preserve and repair it explicitly")
    else:
        save_bytes(blob, data)
        readonly(blob)
    return {"original_path": str(original.relative_to(workspace)), "snapshot_path": str(blob.relative_to(workspace)),
            "sha256": digest, "bytes": len(data), "media_type": mimetypes.guess_type(original.name)[0] or "application/octet-stream"}


def prepare(workspace, directory, writer_id, revision_notes=None, *, new_version=False, reason=None, grant_rounds=0):
    writer_id = require_string(writer_id, "writer ID")
    if isinstance(grant_rounds, bool) or not isinstance(grant_rounds, int) or grant_rounds < 0:
        raise UserError("Additional draft budget must be a non-negative integer")
    if grant_rounds and not new_version:
        raise UserError("Additional rounds require an explicit --new-version and user-request reason")
    state_path = inside(workspace, directory / "quality-loop.json")
    exists = state_path.exists()
    if exists:
        state = loop_state(workspace, directory)
        if state["writer_id"] != writer_id:
            raise UserError("Use --handoff with the new actual writer ID and a reason; the existing budget is preserved")
        if not state["rounds"]:
            raise UserError("Invalid empty existing quality loop")
        if not new_version and state["rounds"][-1]["decision"] != "rewrite":
            raise UserError("Use --new-version --reason for corrected inputs or a requested revision; current round is not rewrite")
    else:
        if new_version or grant_rounds:
            raise UserError("A new version requires an existing document")
        state = {"schema_version": 2, "job_id": directory.name, "document_id": uuid.uuid4().hex,
                 "writer_id": writer_id, "producer_ids": [writer_id], "policy": load_document_quality_policy(workspace),
                 "rounds": [], "events": [], "versions": [{"id": uuid.uuid4().hex, "parent_id": None, "start_round": 0, "reason": "Initial document"}]}
        state["round_limit"] = state["policy"]["max_rewrites"] + 1
    files, pages = current_files(workspace, directory)
    context = context_hashes(workspace, directory, files)
    document_names = {str((directory / name).relative_to(workspace)) for name in ('resume.json', 'resume.tex')}
    resume_name = str((directory / 'resume.json').relative_to(workspace))
    effective = effective_inputs(workspace, {str(path.relative_to(workspace)): path for path in files},
                                 set(context) | document_names, resume_name)
    notes_path = None
    if state["rounds"]:
        previous_path = inside(workspace, workspace / state["rounds"][-1]["packet_path"])
        if sha256_file(previous_path) != state["rounds"][-1]["packet_sha256"]:
            raise UserError("Previous quality packet changed")
        previous = read_json(previous_path)
        check_snapshots(workspace, previous)
        if previous["policy"] != state["policy"]:
            raise UserError("Do not change the frozen quality policy to make a draft pass")
        old = {entry["original_path"]: entry["sha256"] for entry in previous["files"]}
        previous_effective = previous.get('effective_input_hashes') if previous.get('effective_input_version') == 1 else None
        if previous_effective is None:
            # Read verified historical snapshots; never mutate a legacy packet or use changed originals.
            previous_names = context_names(workspace, directory, old) | document_names
            previous_names.discard(previous.get('revision_notes_path'))
            snapshots = {entry['original_path']: workspace / entry['snapshot_path'] for entry in previous['files']}
            previous_effective = effective_inputs(workspace, snapshots, previous_names, resume_name)
        changed_document = any(previous_effective.get(raw) != effective[raw] for raw in document_names)
        changed_context = ({raw: value for raw, value in previous_effective.items() if raw not in document_names} !=
                           {raw: value for raw, value in effective.items() if raw not in document_names})
        if new_version:
            reason = require_string(reason, "new-version reason / user request")
            if not changed_document and not changed_context:
                raise UserError("No substantive input/document change; do not rescore an unchanged artifact")
            if state["rounds"][-1].get("next_action") == "collect_evidence" and not changed_context:
                raise UserError("Material collection requires substantive context changes; rewriting alone cannot resolve missing evidence")
            parent = state["versions"][-1]["id"]
            state["versions"].append({"id": uuid.uuid4().hex, "parent_id": parent,
                                      "start_round": len(state["rounds"]), "reason": reason})
            state["events"].append({"type": "new_version", "at": now_iso(), "reason": reason,
                                    "writer_id": writer_id, "previous_round_id": previous["round_id"]})
            if grant_rounds:
                state["round_limit"] += grant_rounds
                state["events"].append({"type": "budget_grant", "at": now_iso(), "rounds": grant_rounds,
                                        "reason": reason, "writer_id": writer_id, "round_limit": state["round_limit"]})
        else:
            if changed_context:
                raise UserError("Reviewed context changed; use --new-version --reason and retain the existing budget")
            if not changed_document:
                raise UserError("No effective revision to resume.json/TeX; JSON formatting alone cannot rescore unchanged drafts")
            if not revision_notes:
                raise UserError("A rewrite requires --revision-notes documenting prior feedback")
        if revision_notes:
            notes_path = inside(workspace, Path(revision_notes).expanduser().absolute())
            notes = read_json(notes_path)
            if notes.get("previous_round_id") != previous["round_id"]:
                raise UserError("Revision notes refer to another review round")
            changes = require_list(notes.get("changes"), "revision.changes")
            if not changes:
                raise UserError("Revision notes need concrete changes or explained dispositions")
            for change in changes:
                item = require_dict(change, "revision.change")
                for field in ("finding_locator", "action", "explanation"):
                    require_string(item.get(field), f"revision.change.{field}")
            files.append(notes_path)
    if len(state["rounds"]) >= state["round_limit"]:
        raise UserError("Document draft budget exhausted; an explicitly requested new version needs --grant-rounds N --reason, not a reset")
    round_id = uuid.uuid4().hex
    root = inside(workspace, directory / "quality-rounds" / round_id)
    make_dirs(root, exist_ok=False)
    make_dirs(root / "reviews")
    frozen = [freeze_file(workspace, original) for original in files]
    packet = {"schema_version": 1, "job_id": directory.name, "round_id": round_id,
              "document_id": state["document_id"], "version_id": state["versions"][-1]["id"],
              "round_index": len(state["rounds"]), "round_limit": state["round_limit"],
              "writer_id": writer_id, "producer_ids": state["producer_ids"], "policy": state["policy"],
              "context_hashes": context, "effective_input_version": 1, "effective_input_hashes": effective,
              "prepared_at": now_iso(), "pdf_sha256": sha256_file(directory / "resume.pdf"),
              "pages": pages, "files": frozen,
              "report_paths": {role: str((root / "reviews" / f"{role}.json").relative_to(workspace)) for role in state["policy"]["weights"]}}
    if notes_path:
        packet["revision_notes_path"] = str(notes_path.relative_to(workspace))
    check_frozen(workspace, packet)
    path = root / "packet.json"
    write_json(path, packet)
    state["rounds"].append({"id": round_id, "packet_path": str(path.relative_to(workspace)),
                            "packet_sha256": sha256_file(path), "version_id": packet["version_id"], "decision": "pending"})
    save_state(directory, state)
    print(json.dumps({"packet": str(path), "report_paths": packet["report_paths"],
                      "document_id": state["document_id"], "version_id": packet["version_id"],
                      "rewrites_used": packet["round_index"], "round_limit": state["round_limit"],
                      "max_rewrites": state["policy"]["max_rewrites"]}, indent=2))


def check_snapshots(workspace, packet):
    for entry in packet["files"]:
        if sha256_file(inside(workspace, workspace / entry["snapshot_path"])) != entry["sha256"]:
            raise UserError("Historical document snapshot changed; do not replace the old evidence")


def check_frozen(workspace, packet):
    for entry in packet["files"]:
        for key in ("original_path", "snapshot_path"):
            path = inside(workspace, workspace / entry[key])
            if sha256_file(path) != entry["sha256"]:
                raise UserError(f"Document review is stale: {entry[key]} changed; prepare a new version with --new-version --reason after refreshing affected inputs")


def collect_reviews(workspace, packet, packet_hash, producer_ids=()):
    reviews, identities, missing = {}, set(), []
    for role, raw_path in packet["report_paths"].items():
        path = inside(workspace, workspace / raw_path)
        if not path.exists():
            missing.append(f"{role}: no review received")
            continue
        report = read_json(path)
        required = {"schema_version", "role", "packet_sha256", "pdf_sha256", "status", "score", "summary", "issues"}
        if required - report.keys():
            raise UserError("Quality report is missing required fields")
        if report.get("schema_version") != 1 or report.get("role") != role:
            raise UserError("Quality report schema/role mismatch")
        if report.get("packet_sha256") != packet_hash or report.get("pdf_sha256") != packet["pdf_sha256"]:
            raise UserError("Quality report refers to another packet/PDF")
        summary = require_string(report.get("summary"), "review.summary")
        next_action = report.get("next_action", "none")
        if not isinstance(next_action, str) or next_action not in {"none", "rewrite", "collect_evidence"}:
            raise UserError("Review next_action must be none, rewrite, or collect_evidence")
        if next_action == "collect_evidence" and (role != "content" or report.get("status") != "completed"):
            raise UserError("Only a completed content review may request collect_evidence")
        if report.get("status") == "unavailable":
            if report.get("score") is not None:
                raise UserError("Unavailable review must not invent a score")
            missing.append(f"{role}: {summary}")
            continue
        if report.get("status") != "completed" or report.get("execution_kind") not in {"subagent", "session"}:
            raise UserError("Review must be completed in an independent subagent/session, or unavailable")
        route = packet["policy"].get("execution", "auto")
        if route != "auto" and report["execution_kind"] != route:
            raise UserError("Review execution differs from the user's frozen session/subagent choice")
        identity = require_string(report.get("reviewer_id"), "review.reviewer_id")
        if identity in set(producer_ids) | set(packet.get("producer_ids", [packet["writer_id"]])) or identity in identities:
            raise UserError("Reviewer identities must differ from the writer and each other")
        identities.add(identity)
        score = report.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
            raise UserError("Review score must be between 0 and 100")
        for raw in require_list(report.get("issues"), "review.issues"):
            issue = require_dict(raw, "review.issue")
            if issue.get("severity") not in {"low", "medium", "high"}:
                raise UserError("Issue severity must be low, medium, or high")
            for field in ("category", "locator", "message", "suggestion"):
                require_string(issue.get(field), f"review.issue.{field}")
        if next_action == "collect_evidence" and not any(
                issue["category"] == "material_gap" and issue["severity"] in {"medium", "high"}
                for issue in report["issues"]):
            raise UserError("collect_evidence requires an actionable medium/high material_gap issue")
        if role == "visual" and report.get("reviewed_page_hashes") != packet["pages"]:
            raise UserError("Visual reviewer must inspect every current page image with exact hashes")
        reviews[role] = report
    return reviews, missing


def audit_sections(packet, reviews):
    content_roles = [role for role in reviews if role != "visual"]
    def section(roles):
        return {"status": "passed", "summary": " | ".join(f"{role}: {reviews[role]['summary']}" for role in roles),
                "issues": [{key: issue[key] for key in ("severity", "category", "message")}
                           for role in roles for issue in reviews[role]["issues"]]}
    result = {"content": section(content_roles), "visual": section(["visual"])}
    result["visual"]["reviewed_pages"] = list(packet["pages"])
    return result


def evaluate(workspace, directory):
    state_path = inside(workspace, directory / "quality-loop.json")
    state = loop_state(workspace, directory)
    latest = state["rounds"][-1]
    if latest["decision"] not in {"pending", "blocked"}:
        raise UserError("This review round is already decided; preserve it and follow its rewrite/stop result")
    packet_path = inside(workspace, workspace / latest["packet_path"])
    packet_hash = sha256_file(packet_path)
    if packet_hash != latest["packet_sha256"]:
        raise UserError("Frozen quality packet changed")
    packet = read_json(packet_path)
    check_frozen(workspace, packet)
    if latest.get("next_action") == "collect_evidence":
        # Completing a missing role must not erase an already recorded request for evidence.
        previous_outcome = read_json(inside(workspace, packet_path.parent / "outcome.json"))
        content_name = packet["report_paths"]["content"]
        content_path = inside(workspace, workspace / content_name)
        expected = previous_outcome.get("review_files", {}).get(content_name)
        if (previous_outcome.get("round_id") != packet["round_id"] or
                previous_outcome.get("packet_sha256") != packet_hash or
                previous_outcome.get("next_action") != "collect_evidence" or not expected or
                not content_path.is_file() or sha256_file(content_path) != expected):
            raise UserError("The completed content review requesting material collection changed; restore the exact report or collect evidence and prepare a new version")
    reviews, missing = collect_reviews(workspace, packet, packet_hash, state["producer_ids"])
    policy = packet["policy"]
    score = None
    issues = [issue for report in reviews.values() for issue in report["issues"]]
    collect_evidence = any(report.get("next_action") == "collect_evidence" for report in reviews.values())
    if missing:
        decision = "blocked"
    else:
        score = round(sum(reviews[role]["score"] * weight for role, weight in policy["weights"].items()), 2)
        passed = (score >= policy["pass_score"] and
                  all(report["score"] >= policy["minimum_role_score"] for report in reviews.values()) and
                  not any(issue["severity"] == "high" for issue in issues))
        if collect_evidence:
            decision = "needs_material" if packet["round_index"] + 1 < packet.get("round_limit", policy["max_rewrites"] + 1) else "exhausted"
        elif passed:
            decision = "passed"
        elif not issues:
            decision = "blocked"
            missing.append("Scores miss the threshold but provide no actionable issues; clarify review without rewriting the PDF")
        else:
            decision = "rewrite" if packet["round_index"] + 1 < packet.get("round_limit", policy["max_rewrites"] + 1) else "exhausted"
    outcome = {"schema_version": 1, "job_id": directory.name, "round_id": packet["round_id"],
               "packet_sha256": packet_hash, "pdf_sha256": packet["pdf_sha256"], "decision": decision,
               "overall_score": score, "role_scores": {role: report["score"] for role, report in reviews.items()},
               "rewrites_used": packet["round_index"], "policy": policy, "missing": missing, "issues": issues,
               "review_files": {raw: sha256_file(workspace / raw) for raw in packet["report_paths"].values()
                                if (workspace / raw).exists()}, "evaluated_at": now_iso()}
    if collect_evidence:
        outcome["next_action"] = "collect_evidence"
        latest["next_action"] = "collect_evidence"
    else:
        latest.pop("next_action", None)
    if decision == "passed":
        outcome["audit_sections"] = audit_sections(packet, reviews)
    check_frozen(workspace, packet)
    if decision == "passed":
        audit = read_json(directory / "audit.json")
        audit.update(outcome["audit_sections"])
        retain_file(directory / "audit.json")
        write_json(directory / "audit.json", audit)
    retain_file(packet_path.parent / "outcome.json")
    write_json(packet_path.parent / "outcome.json", outcome)
    retain_file(directory / "quality.json")
    write_json(directory / "quality.json", outcome)
    latest["decision"] = decision
    save_state(directory, state)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))


def verify(workspace, directory):
    state = loop_state(workspace, directory)
    outcome = read_json(inside(workspace, directory / "quality.json"))
    latest = state["rounds"][-1]
    if latest["decision"] != "passed" or outcome.get("decision") != "passed" or outcome.get("round_id") != latest["id"]:
        raise UserError("Document quality loop has not passed for the current round")
    packet_path = inside(workspace, workspace / latest["packet_path"])
    digest = sha256_file(packet_path)
    if digest != latest["packet_sha256"] or digest != outcome.get("packet_sha256"):
        raise UserError("Quality packet binding changed")
    packet = read_json(packet_path)
    if packet["policy"] != state["policy"] or outcome.get("policy") != state["policy"]:
        raise UserError("Frozen quality policy changed")
    check_frozen(workspace, packet)
    reviews, missing = collect_reviews(workspace, packet, digest, state["producer_ids"])
    if missing:
        raise UserError("Required quality reviews are unavailable")
    if any(report.get("next_action") == "collect_evidence" for report in reviews.values()):
        raise UserError("Content review requires material collection; document quality cannot pass")
    for raw, expected in outcome["review_files"].items():
        if sha256_file(inside(workspace, workspace / raw)) != expected:
            raise UserError("A completed quality report changed")
    score = round(sum(reviews[role]["score"] * weight for role, weight in packet["policy"]["weights"].items()), 2)
    if (score < packet["policy"]["pass_score"] or outcome.get("overall_score") != score or
            any(report["score"] < packet["policy"]["minimum_role_score"] for report in reviews.values()) or
            any(issue["severity"] == "high" for report in reviews.values() for issue in report["issues"])):
        raise UserError("Quality score or blocking issues do not pass")
    sections = audit_sections(packet, reviews)
    audit = read_json(directory / "audit.json")
    if outcome.get("pdf_sha256") != packet["pdf_sha256"] or outcome.get("audit_sections") != sections:
        raise UserError("Quality conclusion differs from the reviewer evidence")
    if audit.get("content") != sections["content"] or audit.get("visual") != sections["visual"]:
        raise UserError("Derived audit sections differ from the quality reviews")
    print("Current document quality, reviewer reports, and derived audit verified.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--job", required=True)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--prepare", action="store_true", help="Freeze a rendered draft and prepare independent review tasks")
    actions.add_argument("--handoff", action="store_true", help="Record a new actual writer without resetting draft/review budgets")
    actions.add_argument("--verify", action="store_true", help="Verify a passed current round without changing files")
    parser.add_argument("--writer-id", help="Actual primary writer agent/session ID, required with --prepare")
    parser.add_argument("--revision-notes", help="For a rewrite, workspace-local JSON recording previous_round_id and changes")
    parser.add_argument("--new-version", action="store_true", help="With --prepare, continue corrected inputs or a user-requested document revision")
    parser.add_argument("--reason", help="Reason/user request for a handoff, version or explicit budget grant")
    parser.add_argument("--grant-rounds", type=int, default=0, help="Explicit additional draft budget for a requested new version; never resets prior use")
    args = parser.parse_args()
    try:
        workspace = workspace_path(args.workspace)
        directory = inside(workspace, job_dir(workspace, args.job))
        if (args.new_version or args.grant_rounds) and not args.prepare:
            raise UserError("--new-version/--grant-rounds require --prepare")
        if args.prepare:
            prepare(workspace, directory, args.writer_id, args.revision_notes, new_version=args.new_version, reason=args.reason, grant_rounds=args.grant_rounds)
        elif args.handoff:
            handoff(workspace, directory, args.writer_id, args.reason)
        elif args.verify:
            verify(workspace, directory)
        else:
            evaluate(workspace, directory)
        return 0
    except (UserError, OSError, KeyError, IndexError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
