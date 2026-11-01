#!/usr/bin/env python3
"""Standalone, dependency-light runtime for the JobBot Agent Skill."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse
from workspace_fs import (register as register_workspace, guard as workspace_output, mkdir as make_dirs,
                          write_bytes as save_bytes, write_text as save_text, copy_file as copy_file,
                          copy_tree, remove_tree, append_text, check_tree)

MAX_DOWNLOAD_BYTES = 2_000_000
ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "resume.tex"
ONBOARDING_SECTIONS = ("market", "identity", "experience", "education", "skills", "preferences")
EXPERIENCE_GROUPS = {"projects": "project", "research": "research", "coursework": "course", "activities": "activity"}
RESUME_SECTIONS = ("summary", "experience", "projects", "research", "coursework", "activities", "education", "skills")
COUNTRY_PRESETS: dict[str, dict[str, Any]] = {
    "US": {"locale": "en-US", "language": "en", "document_type": "resume", "paper_size": "letter", "date_style": "MMM YYYY", "spelling": "en-US", "address_style": "city-region", "include_photo": False},
    "CA": {"locale": "en-CA", "language": "en", "document_type": "resume", "paper_size": "letter", "date_style": "MMM YYYY", "spelling": "en-CA", "address_style": "city-region", "include_photo": False},
    "GB": {"locale": "en-GB", "language": "en", "document_type": "cv", "paper_size": "a4", "date_style": "MMM YYYY", "spelling": "en-GB", "address_style": "city-region", "include_photo": False},
    "AU": {"locale": "en-AU", "language": "en", "document_type": "resume", "paper_size": "a4", "date_style": "MMM YYYY", "spelling": "en-AU", "address_style": "city-region", "include_photo": False},
}

DEFAULT_AGENT_POLICY = {
    "max_concurrent": 2,
    "scoring": {"max_concurrent": 2, "provider": None, "model": None, "reasoning_effort": None, "max_attempts": 2},
}
DEFAULT_DOCUMENT_QUALITY = {"pass_score": 80, "minimum_role_score": 70, "max_rewrites": 2,
                            "weights": {"content": 0.6, "visual": 0.4},
                            "execution": "auto", "review_provider": None, "review_model": None,
                            "visual_provider": None, "visual_model": None,
                            "max_review_attempts": 2}


class UserError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise UserError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise UserError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise UserError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    workspace_output(path.with_suffix(path.suffix + ".tmp"))
    save_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def retain_file(path: Path) -> None:
    """Preserve replaced task artifacts without treating the copy as canonical."""
    if path.is_file():
        if path.is_symlink():
            raise UserError(f"Refusing to replace a symlink: {path}")
        history = path.parent / "history" / path.name
        if not history.resolve().is_relative_to(path.parent.resolve()):
            raise UserError("Artifact history must remain beside the owning record")
        make_dirs(history)
        copy_file(path, history / f"{uuid.uuid4().hex}{path.suffix}")


def retain_directory(path: Path) -> None:
    if path.is_dir():
        if path.is_symlink():
            raise UserError(f"Refusing to replace a symlink: {path}")
        history = path.parent / "history" / path.name / uuid.uuid4().hex
        if not history.resolve().is_relative_to(path.parent.resolve()):
            raise UserError("Artifact history must remain beside the owning record")
        copy_tree(path, history)


def workspace_path(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise UserError("The personal workspace must be outside the skill source directory")
    return register_workspace(path)


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UserError(f"{label} must be an object")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise UserError(f"{label} must be an array")
    return value


def require_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise UserError(f"{label} must be a non-empty string")
    return value.strip()


def require_id(value: Any, label: str) -> str:
    identifier = require_string(value, label)
    if identifier in {".", ".."} or not ID_RE.fullmatch(identifier):
        raise UserError(f"{label} contains unsupported characters: {identifier}")
    return identifier


def job_dir(workspace: Path, job_id: str) -> Path:
    return workspace_output(workspace / "jobs" / require_id(job_id, "job id"))


def cmd_init(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    country = args.country.upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise UserError("--country must be a two-letter ISO-style country code")
    preset = COUNTRY_PRESETS.get(
        country,
        {"locale": f"und-{country}", "language": "und", "document_type": "cv", "paper_size": "a4", "date_style": "YYYY-MM", "spelling": "confirm-with-user", "address_style": "city-region", "include_photo": False},
    )
    make_dirs(workspace / "jobs")
    make_dirs(workspace / "evidence" / "files")
    settings_path = workspace / "workspace.json"
    if not settings_path.exists():
        write_json(settings_path, {"schema_version": 1, "job_freshness_days": 7,
                                   "agents": DEFAULT_AGENT_POLICY, "document_quality": DEFAULT_DOCUMENT_QUALITY})
    profile_path = workspace / "profile.json"
    preferences_path = workspace / "preferences.json"
    if not profile_path.exists():
        write_json(
            profile_path,
            {
                "schema_version": 3,
                "identity": {"name": "", "email": "", "phone": "", "location": "", "residence_country": "", "links": []},
                "work_authorization": [],
                "summary_facts": [],
                "experience": [],
                **{group: [] for group in EXPERIENCE_GROUPS},
                "education": [],
                "skills": [],
            },
        )
    market_path = workspace / "market.json"
    if not market_path.exists():
        write_json(
            market_path,
            {"schema_version": 1, "target_country": country, **preset, "confirmed": False},
        )
    evidence_path = workspace / "evidence" / "manifest.json"
    if not evidence_path.exists():
        write_json(
            evidence_path,
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "user-confirmed",
                        "type": "user_statement",
                        "label": "Facts explicitly confirmed by the user in conversation",
                        "locator": "conversation",
                        "imported_at": now_iso(),
                        "sha256": "",
                        "ownership_confirmed": True,
                    }
                ],
            },
        )
    onboarding_path = workspace / "onboarding.json"
    if not onboarding_path.exists():
        write_json(
            onboarding_path,
            {
                "schema_version": 1,
                "updated_at": now_iso(),
                "sections": {
                    section: {"status": "pending", "summary": "", "confirmed_at": ""}
                    for section in ONBOARDING_SECTIONS
                },
            },
        )
    if not preferences_path.exists():
        write_json(
            preferences_path,
            {
                "schema_version": 1,
                "target_roles": [],
                "locations": [],
                "work_modes": [],
                "compensation": "",
                "deal_breakers": [],
                "employment_countries": {"mode": "unspecified", "countries": []},
                "relocation": {"willingness": "unknown", "acceptable_locations": [], "conditions": []},
            },
        )
    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        save_text(gitignore, "*\n!.gitignore\n")
    print(f"Initialized workspace for target country {country}: {workspace}")
    print(f"Review market defaults with the user: {market_path}")


def cmd_doctor(_: argparse.Namespace) -> None:
    tools = {
        "python3": shutil.which("python3"),
        "pdflatex": shutil.which("pdflatex"),
        "xelatex": shutil.which("xelatex"),
        "lualatex": shutil.which("lualatex"),
        "pdfinfo": shutil.which("pdfinfo"),
        "pdftotext": shutil.which("pdftotext"),
        "pdftoppm": shutil.which("pdftoppm"),
    }
    for name, path in tools.items():
        print(f"{name}: {path or 'MISSING'}")
    if not any(tools[name] for name in ("pdflatex", "xelatex", "lualatex")):
        print("PDF rendering unavailable until a LaTeX distribution is installed.")
    if not all(tools[name] for name in ("pdfinfo", "pdftotext", "pdftoppm")):
        print("Full PDF audit preparation unavailable until Poppler is installed.")


def load_evidence_sources(workspace: Path) -> dict[str, dict[str, Any]]:
    manifest = read_json(workspace / "evidence" / "manifest.json")
    if manifest.get("schema_version") != 1:
        raise UserError("evidence manifest schema_version must be 1")
    sources: dict[str, dict[str, Any]] = {}
    allowed_types = {"user_statement", "resume", "github", "portfolio", "certificate", "transcript", "other"}
    for index, source_value in enumerate(require_list(manifest.get("sources"), "evidence.sources")):
        source = require_dict(source_value, f"evidence.sources[{index}]")
        identifier = require_id(source.get("id"), f"evidence.sources[{index}].id")
        if identifier in sources:
            raise UserError(f"Duplicate evidence source id: {identifier}")
        source_type = require_string(source.get("type"), f"evidence.sources[{index}].type")
        if source_type not in allowed_types:
            raise UserError(f"Unsupported evidence source type: {source_type}")
        require_string(source.get("label"), f"evidence.sources[{index}].label")
        require_string(source.get("locator"), f"evidence.sources[{index}].locator")
        if not isinstance(source.get("ownership_confirmed"), bool):
            raise UserError(f"evidence.sources[{index}].ownership_confirmed must be boolean")
        sources[identifier] = source
    return sources


def validate_source_ids(value: Any, label: str, sources: dict[str, dict[str, Any]]) -> list[str]:
    raw_ids = require_list(value, label)
    if not raw_ids:
        raise UserError(f"{label} must not be empty")
    result: list[str] = []
    for raw_id in raw_ids:
        identifier = require_id(raw_id, label)
        if identifier not in sources:
            raise UserError(f"{label} cites unknown evidence source id: {identifier}")
        if not sources[identifier]["ownership_confirmed"]:
            raise UserError(f"{label} cites source not yet confirmed by the user: {identifier}")
        result.append(identifier)
    return result


def validate_profile(profile: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if profile.get("schema_version") not in {2, 3}:
        raise UserError("profile.schema_version must be 2 or 3")
    identity = require_dict(profile.get("identity"), "profile.identity")
    require_string(identity.get("name"), "profile.identity.name")
    for field in ("email", "phone", "location"):
        require_string(identity.get(field), f"profile.identity.{field}", allow_empty=True)
    residence_country = require_string(identity.get("residence_country"), "profile.identity.residence_country")
    if not re.fullmatch(r"[A-Z]{2}", residence_country):
        raise UserError("profile.identity.residence_country must be a two-letter country code")
    for link in require_list(identity.get("links"), "profile.identity.links"):
        require_string(link, "profile.identity.links entry")

    for index, auth_value in enumerate(require_list(profile.get("work_authorization"), "profile.work_authorization")):
        auth = require_dict(auth_value, f"profile.work_authorization[{index}]")
        country = require_string(auth.get("country"), f"profile.work_authorization[{index}].country")
        if not re.fullmatch(r"[A-Z]{2}", country):
            raise UserError(f"profile.work_authorization[{index}].country must be a two-letter code")
        require_string(auth.get("status"), f"profile.work_authorization[{index}].status")
        if not isinstance(auth.get("requires_sponsorship"), bool):
            raise UserError(f"profile.work_authorization[{index}].requires_sponsorship must be boolean")
        validate_source_ids(auth.get("source_ids"), f"profile.work_authorization[{index}].source_ids", sources)

    evidence: dict[str, dict[str, Any]] = {}

    def add(identifier: str, kind: str, value: dict[str, Any]) -> None:
        if identifier in evidence:
            raise UserError(f"Duplicate profile evidence id: {identifier}")
        evidence[identifier] = {"kind": kind, "value": value}

    for index, fact_value in enumerate(require_list(profile.get("summary_facts"), "profile.summary_facts")):
        fact = require_dict(fact_value, f"profile.summary_facts[{index}]")
        identifier = require_id(fact.get("id"), f"profile.summary_facts[{index}].id")
        require_string(fact.get("text"), f"profile.summary_facts[{index}].text")
        validate_source_ids(fact.get("source_ids"), f"profile.summary_facts[{index}].source_ids", sources)
        add(identifier, "summary_fact", fact)

    for index, exp_value in enumerate(require_list(profile.get("experience"), "profile.experience")):
        exp = require_dict(exp_value, f"profile.experience[{index}]")
        identifier = require_id(exp.get("id"), f"profile.experience[{index}].id")
        for field in ("employer", "title", "start", "end"):
            require_string(exp.get(field), f"profile.experience[{index}].{field}")
        require_string(exp.get("location"), f"profile.experience[{index}].location", allow_empty=True)
        validate_source_ids(exp.get("source_ids"), f"profile.experience[{index}].source_ids", sources)
        add(identifier, "experience", exp)
        for bullet_index, bullet_value in enumerate(require_list(exp.get("bullets"), f"profile.experience[{index}].bullets")):
            bullet = require_dict(bullet_value, f"profile.experience[{index}].bullets[{bullet_index}]")
            bullet_id = require_id(bullet.get("id"), f"profile.experience[{index}].bullets[{bullet_index}].id")
            require_string(bullet.get("text"), f"profile.experience[{index}].bullets[{bullet_index}].text")
            validate_source_ids(bullet.get("source_ids"), f"profile.experience[{index}].bullets[{bullet_index}].source_ids", sources)
            add(bullet_id, "experience_bullet", bullet)

    for index, edu_value in enumerate(require_list(profile.get("education"), "profile.education")):
        edu = require_dict(edu_value, f"profile.education[{index}]")
        identifier = require_id(edu.get("id"), f"profile.education[{index}].id")
        for field in ("institution", "credential", "start", "end"):
            require_string(edu.get(field), f"profile.education[{index}].{field}")
        require_string(edu.get("location"), f"profile.education[{index}].location", allow_empty=True)
        validate_source_ids(edu.get("source_ids"), f"profile.education[{index}].source_ids", sources)
        add(identifier, "education", edu)

    for index, skill_value in enumerate(require_list(profile.get("skills"), "profile.skills")):
        skill = require_dict(skill_value, f"profile.skills[{index}]")
        identifier = require_id(skill.get("id"), f"profile.skills[{index}].id")
        require_string(skill.get("name"), f"profile.skills[{index}].name")
        require_string(skill.get("category"), f"profile.skills[{index}].category")
        validate_source_ids(skill.get("source_ids"), f"profile.skills[{index}].source_ids", sources)
        add(identifier, "skill", skill)
    for group, kind in EXPERIENCE_GROUPS.items():
        entries = profile.get(group, [] if profile["schema_version"] == 2 else None)
        for index, raw in enumerate(require_list(entries, f"profile.{group}")):
            entry = require_dict(raw, f"profile.{group}[{index}]")
            label = f"profile.{group}[{index}]"
            identifier = require_id(entry.get("id"), f"{label}.id")
            require_string(entry.get("name"), f"{label}.name")
            for field in ("start", "end"):
                require_string(entry.get(field), f"{label}.{field}", allow_empty=True)
            for field in ("organization", "role", "location"):
                if field in entry:
                    require_string(entry[field], f"{label}.{field}", allow_empty=True)
            validate_source_ids(entry.get("source_ids"), f"{label}.source_ids", sources)
            add(identifier, kind, entry)
            for n, raw_fact in enumerate(require_list(entry.get("bullets"), f"{label}.bullets")):
                fact = require_dict(raw_fact, f"{label}.bullets[{n}]")
                fact_id = require_id(fact.get("id"), f"{label}.bullets[{n}].id")
                require_string(fact.get("text"), f"{label}.bullets[{n}].text")
                validate_source_ids(fact.get("source_ids"), f"{label}.bullets[{n}].source_ids", sources)
                add(fact_id, f"{kind}_fact", fact)
    for identifier, item in evidence.items():
        for linked in require_list(item["value"].get("related_ids", []), f"{identifier}.related_ids"):
            linked = require_id(linked, f"{identifier}.related_ids")
            if linked not in evidence or linked == identifier:
                raise UserError(f"{identifier} has an unknown or self-referencing related_id: {linked}")
    return evidence


def load_valid_profile(workspace: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    profile = read_json(workspace / "profile.json")
    sources = load_evidence_sources(workspace)
    return profile, validate_profile(profile, sources)


def cmd_validate_profile(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    profile, evidence = load_valid_profile(workspace)
    print(f"Profile valid: {profile['identity']['name']} ({len(evidence)} evidence ids)")
    print(f"SHA-256: {sha256_file(workspace / 'profile.json')}")


def cmd_upgrade_profile(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    profile, _ = load_valid_profile(workspace)
    if profile["schema_version"] == 3:
        print("Profile already uses version 3; no files changed.")
        return
    profile["schema_version"] = 3
    for group in EXPERIENCE_GROUPS:
        profile.setdefault(group, [])
    validate_profile(profile, load_evidence_sources(workspace))
    retain_file(workspace / "profile.json")
    write_json(workspace / "profile.json", profile)
    print("Upgraded profile to version 3; preserved prior bytes in history/profile.json/. Existing prepared documents need refreshed bindings.")


def writing_rules_hash(workspace: Path) -> str | None:
    path = workspace / "writing-rules.json"
    return sha256_file(path) if path.exists() else None


def load_writing_rules(workspace: Path, job_id: str | None = None) -> dict[str, Any]:
    path = workspace / "writing-rules.json"
    record = read_json(path) if path.exists() else {"schema_version": 1, "rules": []}
    if record.get("schema_version") != 1:
        raise UserError("writing-rules.schema_version must be 1")
    country = read_json(workspace / "market.json").get("target_country")
    selected, seen = [], set()
    for raw in require_list(record.get("rules"), "writing-rules.rules"):
        rule = require_dict(raw, "writing rule")
        identifier = require_id(rule.get("id"), "writing rule id")
        if identifier in seen:
            raise UserError("Duplicate writing rule id")
        seen.add(identifier)
        require_string(rule.get("instruction"), "writing rule instruction")
        require_string(rule.get("confirmation"), "writing rule confirmation")
        parse_timestamp(rule.get("confirmed_at"), "writing rule confirmed_at")
        scope, target = rule.get("scope"), rule.get("target")
        if scope not in {"workspace", "market", "job"} or rule.get("status") not in {"active", "retired"}:
            raise UserError("Invalid writing rule scope/status")
        if scope == "workspace" and target is not None:
            raise UserError("Workspace rules must have a null target")
        if scope == "market" and (not isinstance(target, str) or not re.fullmatch(r"[A-Z]{2}", target)):
            raise UserError("Market rules require a two-letter country target")
        if scope == "job":
            require_id(target, "writing rule job target")
        for phrase in require_list(rule.get("forbidden_phrases"), "writing rule forbidden_phrases"):
            require_string(phrase, "forbidden phrase")
        for identifier in require_list(rule.get("excluded_evidence_ids"), "writing rule excluded_evidence_ids"):
            require_id(identifier, "excluded evidence id")
        if rule["status"] == "active" and (scope == "workspace" or scope == "market" and target == country or scope == "job" and target == job_id):
            selected.append(rule)
    return {"schema_version": 1, "rules": selected,
            "forbidden_phrases": sorted({p for r in selected for p in r["forbidden_phrases"]}),
            "excluded_evidence_ids": sorted({p for r in selected for p in r["excluded_evidence_ids"]})}


def cmd_writing_rules(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    print(json.dumps(load_writing_rules(workspace, args.job), ensure_ascii=False, indent=2))


def cmd_set_writing_rule(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    load_writing_rules(workspace)
    path = workspace / "writing-rules.json"
    record = read_json(path) if path.exists() else {"schema_version": 1, "rules": []}
    identifier = require_id(args.id, "writing rule id")
    existing = next((r for r in record["rules"] if r["id"] == identifier), None)
    if args.retire:
        if not existing:
            raise UserError("Cannot retire an unknown writing rule")
        rule = {**existing, "status": "retired", "confirmation": require_string(args.confirmation, "confirmation"), "confirmed_at": now_iso()}
    else:
        if args.scope == "workspace" and args.target or args.scope != "workspace" and not args.target:
            raise UserError("Only market/job-scoped rules require --target")
        rule = {"id": identifier, "instruction": require_string(args.instruction, "instruction"),
                "scope": args.scope, "target": args.target, "status": "active",
                "forbidden_phrases": [require_string(p, "forbidden phrase") for p in args.forbid],
                "excluded_evidence_ids": [require_id(p, "excluded evidence id") for p in args.exclude],
                "confirmation": require_string(args.confirmation, "confirmation"), "confirmed_at": now_iso()}
        if args.scope == "market" and not re.fullmatch(r"[A-Z]{2}", args.target):
            raise UserError("Market rule target must be a two-letter country code")
        if args.scope == "job":
            require_id(args.target, "job target")
    record["rules"] = [r for r in record["rules"] if r["id"] != identifier] + [rule]
    retain_file(path)
    write_json(path, record)
    print(f"Saved writing rule {identifier}; profile facts and historical documents were preserved.")


def excluded_evidence(profile: dict[str, Any], rules: dict[str, Any]) -> set[str]:
    excluded = set(rules["excluded_evidence_ids"])
    for group in ("experience", *EXPERIENCE_GROUPS):
        for entry in profile.get(group, []):
            if entry["id"] in excluded:
                excluded.update(fact["id"] for fact in entry["bullets"])
    return excluded


def validate_writing_constraints(profile: dict[str, Any], resume: dict[str, Any], rules: dict[str, Any], market: dict[str, Any]) -> None:
    excluded = excluded_evidence(profile, rules)
    references = set(resume["profile_skill_ids"])
    identity = profile["identity"]
    texts = [identity["name"], identity.get("email", ""), identity.get("phone", ""), *identity.get("links", [])]
    if market["address_style"] != "none":
        texts.append(identity.get("location", ""))
    rendered_sections = set()
    for group, reference in (("experience", "profile_experience_id"), *[(g, f"profile_{k}_id") for g, k in EXPERIENCE_GROUPS.items()]):
        for item in resume.get(group, []):
            if item["bullets"]:
                references.add(item[reference])
                source = next(e for e in profile.get(group, []) if e["id"] == item[reference])
                fields = ("title", "employer", "location", "start", "end") if group == "experience" else ("name", "organization", "role", "location", "start", "end")
                texts.extend(source.get(f, "") for f in fields)
                rendered_sections.add(group)
            for claim in item["bullets"]:
                references.update(claim["evidence_ids"])
                texts.append(claim["text"])
    for claim in resume["summary"]:
        references.update(claim["evidence_ids"])
        texts.append(claim["text"])
        rendered_sections.add("summary")
    for item in resume["education"]:
        references.add(item["profile_education_id"])
        edu = next(e for e in profile["education"] if e["id"] == item["profile_education_id"])
        texts.extend(edu.get(f, "") for f in ("institution", "credential", "location", "start", "end"))
        rendered_sections.add("education")
    for skill in profile["skills"]:
        if skill["id"] in resume["profile_skill_ids"]:
            texts.extend([skill["name"], skill["category"]])
            rendered_sections.add("skills")
    if references & excluded:
        raise UserError(f"Resume uses evidence excluded by writing rules: {', '.join(sorted(references & excluded))}")
    if rules["forbidden_phrases"]:
        labels = document_labels(market)
        texts.extend(labels[section] for section in rendered_sections)
    normalized = " ".join(" ".join(texts).casefold().split())
    for phrase in rules["forbidden_phrases"]:
        needle = " ".join(phrase.casefold().split())
        pattern = (r"(?<!\w)" if needle[0].isascii() and needle[0].isalnum() else "") + re.escape(needle) + (r"(?!\w)" if needle[-1].isascii() and needle[-1].isalnum() else "")
        if re.search(pattern, normalized):
            raise UserError(f"Resume contains a forbidden writing-rule phrase: {phrase}")


def validate_market(workspace: Path, *, require_confirmed: bool = False) -> dict[str, Any]:
    market = read_json(workspace / "market.json")
    if market.get("schema_version") != 1:
        raise UserError("market.schema_version must be 1")
    country = require_string(market.get("target_country"), "market.target_country")
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise UserError("market.target_country must be a two-letter country code")
    for field in ("locale", "language", "date_style", "spelling"):
        require_string(market.get(field), f"market.{field}")
    if market.get("document_type") not in {"resume", "cv"}:
        raise UserError("market.document_type must be resume or cv")
    if market.get("paper_size") not in {"letter", "a4"}:
        raise UserError("market.paper_size must be letter or a4")
    if market.get("address_style") not in {"none", "city-region", "full"}:
        raise UserError("market.address_style must be none, city-region, or full")
    if not isinstance(market.get("include_photo"), bool) or not isinstance(market.get("confirmed"), bool):
        raise UserError("market.include_photo and market.confirmed must be boolean")
    if require_confirmed and not market["confirmed"]:
        raise UserError("Target-market document settings have not been confirmed by the user")
    return market


def validate_preferences(workspace: Path) -> dict[str, Any]:
    preferences = read_json(workspace / "preferences.json")
    if preferences.get("schema_version") != 1:
        raise UserError("preferences.schema_version must be 1")
    for field in ("target_roles", "locations", "work_modes", "deal_breakers"):
        values = require_list(preferences.get(field), f"preferences.{field}")
        for index, value in enumerate(values):
            require_string(value, f"preferences.{field}[{index}]")
    require_string(preferences.get("compensation"), "preferences.compensation", allow_empty=True)
    if "employment_countries" in preferences:
        policy = require_dict(preferences["employment_countries"], "preferences.employment_countries")
        if policy.get("mode") not in {"unspecified", "any", "only", "exclude"}:
            raise UserError("preferences.employment_countries.mode must be unspecified, any, only, or exclude")
        countries = require_list(policy.get("countries"), "preferences.employment_countries.countries")
        for country in countries:
            if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country):
                raise UserError("preferences.employment_countries.countries must contain two-letter country codes")
        if policy["mode"] in {"only", "exclude"} and not countries:
            raise UserError("Restricted country policies need at least one country")
        if policy["mode"] in {"unspecified", "any"} and countries:
            raise UserError("Unrestricted or unspecified country policies must not list countries")
    if "relocation" in preferences:
        relocation = require_dict(preferences["relocation"], "preferences.relocation")
        if relocation.get("willingness") not in {"unknown", "no", "yes", "conditional"}:
            raise UserError("preferences.relocation.willingness must be unknown, no, yes, or conditional")
        for field in ("acceptable_locations", "conditions"):
            for value in require_list(relocation.get(field), f"preferences.relocation.{field}"):
                require_string(value, f"preferences.relocation.{field}[]")
        if relocation["willingness"] == "conditional" and not relocation["conditions"]:
            raise UserError("Conditional relocation needs the user's conditions")
    return preferences


def read_onboarding(workspace: Path) -> dict[str, Any]:
    onboarding = read_json(workspace / "onboarding.json")
    if onboarding.get("schema_version") != 1:
        raise UserError("onboarding.schema_version must be 1")
    sections = require_dict(onboarding.get("sections"), "onboarding.sections")
    if set(sections) != set(ONBOARDING_SECTIONS):
        raise UserError("onboarding.sections has an unexpected section set")
    for section_name in ONBOARDING_SECTIONS:
        section = require_dict(sections.get(section_name), f"onboarding.sections.{section_name}")
        if section.get("status") not in {"pending", "confirmed"}:
            raise UserError(f"Invalid onboarding status for {section_name}")
        require_string(section.get("summary"), f"onboarding.sections.{section_name}.summary", allow_empty=True)
        require_string(section.get("confirmed_at"), f"onboarding.sections.{section_name}.confirmed_at", allow_empty=True)
    return onboarding


def cmd_confirm_section(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    onboarding = read_onboarding(workspace)
    summary = require_string(args.summary, "confirmation summary")
    if args.section == "market":
        market = validate_market(workspace)
        market["confirmed"] = True
        write_json(workspace / "market.json", market)
    section = onboarding["sections"][args.section]
    section.update({"status": "confirmed", "summary": summary, "confirmed_at": now_iso()})
    onboarding["updated_at"] = now_iso()
    write_json(workspace / "onboarding.json", onboarding)
    print(f"Confirmed onboarding section: {args.section}")


def cmd_onboarding_status(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    onboarding = read_onboarding(workspace)
    for section_name in ONBOARDING_SECTIONS:
        section = onboarding["sections"][section_name]
        print(f"{section_name}: {section['status']}" + (f" — {section['summary']}" if section["summary"] else ""))


def ensure_onboarding_complete(workspace: Path) -> None:
    onboarding = read_onboarding(workspace)
    pending = [name for name in ONBOARDING_SECTIONS if onboarding["sections"][name]["status"] != "confirmed"]
    if pending:
        raise UserError(f"Complete and confirm onboarding sections first: {', '.join(pending)}")
    validate_market(workspace, require_confirmed=True)
    load_valid_profile(workspace)
    validate_preferences(workspace)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._ignored = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        if tag == "title":
            self._in_title = True
        if not self._ignored and tag in {"p", "div", "li", "br", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        if not self._ignored and tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        if self._in_title:
            self.title_parts.append(data)
        self.parts.append(data)

    def text(self) -> str:
        value = html.unescape("".join(self.parts)).replace("\r", "")
        lines = [re.sub(r"\s+", " ", line).strip() for line in value.split("\n")]
        return "\n".join(line for line in lines if line).strip() + "\n"

    def title(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.title_parts)).strip()


def validate_public_https_url(raw_url: str) -> str:
    from public_http import validate_url
    try:
        return validate_url(raw_url)
    except OSError as exc:
        raise UserError(str(exc)) from exc


def http_get_bytes(url: str, headers: dict[str, str] | None = None) -> tuple[str, bytes, str, str]:
    from public_http import fetch
    try:
        return fetch(url, headers, max_bytes=MAX_DOWNLOAD_BYTES)
    except OSError as exc:
        raise UserError(str(exc)) from exc


def fetch_public_text(url: str) -> tuple[str, bytes, str, str]:
    final_url, data, content_type, charset = http_get_bytes(url)
    if content_type not in {"text/html", "text/plain"}:
        raise UserError(f"Unsupported job response content type: {content_type}")
    try:
        decoded = data.decode(charset, errors="replace")
    except LookupError as exc:
        raise UserError(f"Unsupported response charset: {charset}") from exc
    if content_type == "text/html":
        extractor = TextExtractor()
        extractor.feed(decoded)
        return final_url, data, extractor.text(), extractor.title()
    return final_url, data, decoded.replace("\r\n", "\n").strip() + "\n", ""


def append_evidence_source(workspace: Path, source: dict[str, Any]) -> None:
    manifest_path = workspace / "evidence" / "manifest.json"
    manifest = read_json(manifest_path)
    sources = require_list(manifest.get("sources"), "evidence.sources")
    if any(item.get("id") == source["id"] for item in sources if isinstance(item, dict)):
        raise UserError(f"Evidence source id already exists: {source['id']}")
    sources.append(source)
    write_json(manifest_path, manifest)
    load_evidence_sources(workspace)


def cmd_import_evidence(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    source_path = Path(args.file).expanduser().resolve()
    if not source_path.is_file():
        raise UserError(f"Evidence file not found: {source_path}")
    data = source_path.read_bytes()
    if len(data) > 20_000_000:
        raise UserError("Evidence file exceeds the 20 MB limit")
    digest = sha256_bytes(data)
    identifier = require_id(args.id or f"{args.type}.{digest[:12]}", "evidence id")
    destination = workspace / "evidence" / "files" / f"{identifier}{source_path.suffix.lower()}"
    if destination.exists():
        raise UserError(f"Refusing to overwrite existing evidence file: {destination}")
    make_dirs(destination.parent)
    copy_file(source_path, destination)
    append_evidence_source(
        workspace,
        {
            "id": identifier,
            "type": args.type,
            "label": args.label,
            "locator": str(destination.relative_to(workspace)),
            "imported_at": now_iso(),
            "sha256": digest,
            "ownership_confirmed": False,
        },
    )
    print(f"Imported evidence source {identifier}: {destination}")
    print("Ask the user to confirm ownership/relevance, then run confirm-evidence.")


def parse_github_url(raw_url: str) -> tuple[str, str | None, str]:
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() != "https" or parsed.hostname not in {"github.com", "www.github.com"}:
        raise UserError("GitHub evidence must be a public https://github.com/owner/repo URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) not in {1, 2}:
        raise UserError("GitHub URL must point to a public profile or repository root")
    owner = parts[0]
    repo = parts[1] if len(parts) == 2 else None
    if repo and repo.endswith(".git"):
        repo = repo[:-4]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or (repo is not None and not re.fullmatch(r"[A-Za-z0-9_.-]+", repo)):
        raise UserError("GitHub owner or repository name is invalid")
    canonical = f"https://github.com/{owner}" + (f"/{repo}" if repo else "")
    return owner, repo, canonical


def github_api_get(path: str, *, accept: str = "application/vnd.github+json") -> bytes:
    # Public import never borrows ambient account credentials.
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    _, data, _, _ = http_get_bytes(f"https://api.github.com{path}", headers)
    return data


def github_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise UserError(f"Invalid GitHub {label} response") from exc


def public_repository_response(raw):
    record = require_dict(github_json(raw, "repository"), "GitHub repository")
    if record.get("private") is not False or record.get("visibility", "public") != "public":
        raise UserError("Public GitHub import requires an explicitly public repository")


def public_repository_index(raw):
    for value in require_list(github_json(raw, "repository index"), "GitHub repositories"):
        record = require_dict(value, "GitHub repository index item")
        if record.get("private") is not False or record.get("visibility", "public") != "public":
            raise UserError("Public GitHub index unexpectedly contains private or unclassified content")


class GitHubImportAttempt:
    """Retain successful public responses and failure receipts before publication."""
    def __init__(self, workspace, identifier, url):
        self.directory = workspace / "evidence" / "github-attempts" / identifier / uuid.uuid4().hex
        self.state = {"schema_version": 1, "source_id": identifier, "url": url,
                      "started_at": now_iso(), "status": "running", "captures": [], "errors": []}

    def persist(self):
        path = self.directory / "attempt.json"
        retain_file(path)
        write_json(path, self.state)

    def __enter__(self):
        self.persist()
        return self

    def __exit__(self, kind, error, traceback):
        self.state.update(status="failed" if error is not None else "completed", finished_at=now_iso())
        if error is not None:
            self.state["failure"] = {"type": type(error).__name__, "message": str(error)}
        self.persist()
        return False

    def fetch(self, name, path, *, accept="application/vnd.github+json", validate=None):
        try:
            raw = github_api_get(path, accept=accept)
            # Unexpected private/unclassified metadata is rejected before retaining content.
            if validate is not None:
                validate(raw)
            save_bytes(self.directory / name, raw)
            self.state["captures"].append({"path": name, "api_path": path, "sha256": sha256_bytes(raw), "bytes": len(raw)})
        except (UserError, OSError) as exc:
            self.state["errors"].append({"api_path": path, "type": type(exc).__name__, "message": str(exc), "at": now_iso()})
            self.persist()
            raise
        self.persist()
        return raw


def cmd_import_github(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    owner, repo, canonical_url = parse_github_url(args.url)
    default_id = f"github.{owner}.{repo}" if repo else f"github.{owner}"
    identifier = require_id(args.id or default_id, "evidence id")
    if identifier in load_evidence_sources(workspace):
        raise UserError("Evidence ID exists; use a new --id to retain another GitHub snapshot")
    destination_name = f"{owner}__{repo}" if repo else f"{owner}__profile"
    destination = workspace / "evidence" / "github" / destination_name
    if destination.exists():
        destination = destination.with_name(destination.name + "." + sha256_bytes(identifier.encode())[:12])
    if destination.exists():
        raise UserError(f"Refusing to overwrite existing GitHub evidence: {destination}")
    with GitHubImportAttempt(workspace, identifier, canonical_url) as attempt:
        finish_github_import(args, workspace, owner, repo, canonical_url, identifier, destination, attempt)


def finish_github_import(args, workspace, owner, repo, canonical_url, identifier, destination, attempt):
    payloads = {}
    coverage = None
    if repo:
        metadata = attempt.fetch("repository.json", f"/repos/{owner}/{repo}", validate=public_repository_response)
        record = require_dict(github_json(metadata, "repository"), "GitHub repository")
        if record.get("private") is not False or record.get("visibility", "public") != "public":
            raise UserError("Public GitHub import requires an explicitly public repository")
        payloads["repository.json"] = metadata
        payloads["languages.json"] = attempt.fetch("languages.json", f"/repos/{owner}/{repo}/languages")
        try:
            payloads["README.md"] = attempt.fetch("README.md", f"/repos/{owner}/{repo}/readme", accept="application/vnd.github.raw+json")
        except (UserError, OSError) as exc:
            payloads["README.md"] = f"README unavailable: {exc}\n".encode()
        default_label = f"GitHub repository {owner}/{repo}"
        detail = "Public repository metadata is evidence; confirm the user's relationship and personal contributions."
    else:
        limit = getattr(args, "max_pages", 10)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise UserError("--max-pages must be between 1 and 100")
        payloads["profile.json"] = attempt.fetch("profile.json", f"/users/{owner}")
        repositories, pages, seen = [], {}, set()
        complete = False
        for page in range(1, limit + 1):
            raw = attempt.fetch(f"repositories-page-{page}.json", f"/users/{owner}/repos?per_page=100&sort=updated&type=owner&page={page}", validate=public_repository_index)
            items = require_list(github_json(raw, "repository index"), "GitHub repositories")
            pages[f"repositories-page-{page}.json"] = raw
            for item in items:
                item = require_dict(item, "GitHub repository index item")
                if item.get("private") is not False or item.get("visibility", "public") != "public":
                    raise UserError("Public GitHub index unexpectedly contains private or unclassified content")
                key = item.get("id", item.get("full_name", json.dumps(item, sort_keys=True)))
                if key not in seen:
                    repositories.append(item)
                    seen.add(key)
            if len(items) < 100:
                complete = True
                break
        coverage = {"pages_fetched": len(pages), "max_pages": limit, "repositories_saved": len(repositories),
                    "complete": complete, "next_page": None if complete else len(pages) + 1,
                    "scope": "Public repositories owned by this account; not contributions to other owners' repositories"}
        payloads["repositories.json"] = (json.dumps(repositories, ensure_ascii=False, indent=2) + "\n").encode()
        payloads["coverage.json"] = (json.dumps(coverage, indent=2) + "\n").encode()
        payloads.update(pages)
        default_label = f"GitHub profile {owner}"
        detail = f"Public repository index captured ({len(pages)} pages, complete={complete}); inspect coverage.json before claiming coverage."
    make_dirs(destination, exist_ok=False)
    for name, data in payloads.items():
        save_bytes(destination / name, data)
    append_evidence_source(workspace, {
        "id": identifier, "type": "github", "label": args.label or default_label,
        "locator": canonical_url, "imported_at": now_iso(),
        "sha256": sha256_bytes(b"\0".join(payloads.values())), "ownership_confirmed": False,
        "snapshot_directory": str(destination.relative_to(workspace)), "snapshot_files": list(payloads),
        "attempt_directory": str(attempt.directory.relative_to(workspace)),
        **({"coverage": coverage} if coverage else {}),
    })
    print(f"Imported public GitHub evidence {identifier}: {destination}")
    print(detail)


def cmd_confirm_evidence(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    manifest_path = workspace / "evidence" / "manifest.json"
    manifest = read_json(manifest_path)
    found = False
    for source in require_list(manifest.get("sources"), "evidence.sources"):
        if isinstance(source, dict) and source.get("id") == args.id:
            source["ownership_confirmed"] = True
            source["confirmation_note"] = args.note
            source["confirmed_at"] = now_iso()
            found = True
            break
    if not found:
        raise UserError(f"Unknown evidence source id: {args.id}")
    write_json(manifest_path, manifest)
    print(f"Confirmed evidence source: {args.id}")


def evidence_snapshot(workspace: Path, source: dict[str, Any]) -> tuple[str, list[str]]:
    """Verify the saved source bytes before deriving or reusing reading notes."""
    if source["type"] == "user_statement":
        raise UserError("Conversation facts belong in the confirmed profile, not an imported-source review")
    if source["type"] == "github":
        owner, repo, _ = parse_github_url(source["locator"])
        name = f"{owner}__{repo}" if repo else f"{owner}__profile"
        base = workspace / "evidence" / "github" / name
        names = ("repository.json", "languages.json", "README.md") if repo else ("profile.json", "repositories.json")
        if "snapshot_directory" in source:
            base = workspace / require_string(source["snapshot_directory"], "GitHub snapshot directory")
            if not base.resolve().is_relative_to((workspace / "evidence" / "github").resolve()):
                raise UserError("GitHub snapshots must remain in evidence/github")
            names = [require_id(item, "GitHub snapshot filename") for item in require_list(source.get("snapshot_files"), "GitHub snapshot files")]
            if not names:
                raise UserError("GitHub snapshot inventory must not be empty")
        paths = [base / name for name in names]
    else:
        paths = [workspace / require_string(source.get("locator"), "source.locator")]
    for path in paths:
        if not path.resolve().is_relative_to(workspace.resolve()):
            raise UserError("Evidence files must remain inside the selected workspace")
    chunks = [path.read_bytes() for path in paths]
    digest = sha256_bytes(b"\0".join(chunks))
    if digest != source.get("sha256"):
        raise UserError(f"Evidence source changed: {source['id']}; import a new snapshot before reviewing")
    return digest, [str(path.relative_to(workspace)) for path in paths]


def cmd_prepare_source_review(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    sources = load_evidence_sources(workspace)
    identifier = require_id(args.id, "source id")
    if identifier not in sources:
        raise UserError(f"Unknown evidence source id: {identifier}")
    digest, files = evidence_snapshot(workspace, sources[identifier])
    output = workspace / "evidence" / "reviews" / f"{identifier}.json"
    if output.exists():
        raise UserError(f"Refusing to overwrite existing reading notes: {output}")
    write_json(output, {
        "schema_version": 1,
        "source_id": identifier,
        "source_sha256": digest,
        "prepared_at": now_iso(),
        "status": "pending",
        "summary": "",
        "observations": [],
        "candidate_facts": [],
        "questions": [],
    })
    print(f"Prepared source review: {output}")
    print(f"Read the saved files: {', '.join(files)}")
    print("The agent writes the summary and source locators; candidate facts still require user confirmation.")


def validate_source_review(review: dict[str, Any], identifier: str, digest: str) -> None:
    if review.get("schema_version") != 1 or review.get("source_id") != identifier:
        raise UserError("Reading-note schema version or source id is invalid")
    if review.get("source_sha256") != digest:
        raise UserError("Reading notes refer to a different source snapshot")
    require_string(review.get("prepared_at"), "review.prepared_at")
    if review.get("status") not in {"pending", "reviewed"}:
        raise UserError("Reading-note status must be pending or reviewed")
    require_string(review.get("summary"), "review.summary", allow_empty=review["status"] == "pending")
    for field in ("observations", "candidate_facts"):
        for index, value in enumerate(require_list(review.get(field), f"review.{field}")):
            item = require_dict(value, f"review.{field}[{index}]")
            require_string(item.get("text"), f"review.{field}[{index}].text")
            require_string(item.get("locator"), f"review.{field}[{index}].locator")
    for question in require_list(review.get("questions"), "review.questions"):
        require_string(question, "review.questions[]")


def intake_review_status(workspace: Path, refresh_after_days: int) -> dict[str, Any]:
    path = workspace / "intake.json"
    if not path.exists():
        return {"last_reviewed_at": None, "days_since_review": None,
                "suggest_refresh": False, "reason": "No intake review recorded; do not infer age from file modification times"}
    review = read_json(path)
    if review.get("schema_version") != 1:
        raise UserError("intake.schema_version must be 1")
    timestamp = require_string(review.get("last_reviewed_at"), "intake.last_reviewed_at")
    try:
        reviewed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UserError("intake.last_reviewed_at must be an ISO timestamp with timezone") from exc
    if reviewed_at.tzinfo is None:
        raise UserError("intake.last_reviewed_at must include a timezone")
    age = datetime.now(timezone.utc) - reviewed_at
    if age.total_seconds() < 0:
        raise UserError("intake.last_reviewed_at must not be in the future")
    changed = {}
    for name in ("profile", "preferences"):
        digest = require_string(review.get(f"{name}_sha256"), f"intake.{name}_sha256")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise UserError(f"intake.{name}_sha256 must be a SHA-256 hash")
        changed[f"{name}_changed_since_review"] = digest != sha256_file(workspace / f"{name}.json")
    summary = require_string(review.get("summary"), "intake.summary")
    return {"last_reviewed_at": timestamp, "days_since_review": age.days,
            "summary": summary, **changed,
            "suggest_refresh": age.days >= refresh_after_days or any(changed.values())}


def cmd_record_intake_review(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    load_valid_profile(workspace)
    validate_preferences(workspace)
    summary = require_string(args.summary, "intake review summary")
    write_json(workspace / "intake.json", {
        "schema_version": 1, "last_reviewed_at": now_iso(), "summary": summary,
        "profile_sha256": sha256_file(workspace / "profile.json"),
        "preferences_sha256": sha256_file(workspace / "preferences.json"),
    })
    print("Recorded candidate information review; profile, preferences, and onboarding confirmations were preserved.")


def cmd_workspace_status(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    if args.refresh_after_days < 1:
        raise UserError("--refresh-after-days must be positive")
    rows = []
    for identifier, source in load_evidence_sources(workspace).items():
        if source["type"] == "user_statement":
            continue
        row: dict[str, Any] = {
            "id": identifier, "type": source["type"], "label": source["label"],
            "ownership_confirmed": source["ownership_confirmed"],
            "review_status": "missing",
        }
        try:
            digest, files = evidence_snapshot(workspace, source)
            row.update({"source_sha256": digest, "files": files})
            review_path = workspace / "evidence" / "reviews" / f"{identifier}.json"
            if review_path.exists():
                review = read_json(review_path)
                validate_source_review(review, identifier, digest)
                row.update({"review_status": review["status"], "review_file": str(review_path.relative_to(workspace))})
        except (UserError, OSError) as exc:
            row.update({"review_status": "needs_attention", "error": str(exc)})
        rows.append(row)
    profile_path = workspace / "profile.json"
    profile_record = read_json(profile_path)
    market_record = read_json(workspace / "market.json") if (workspace / "market.json").is_file() else {}
    print(json.dumps({
        "workspace": str(workspace),
        "profile_sha256": sha256_file(profile_path),
        "market_configured": (workspace / "market.json").is_file(),
        "market_confirmed": market_record.get("confirmed") is True,
        "experience_counts": {group: len(profile_record.get(group, [])) for group in ("experience", *EXPERIENCE_GROUPS)},
        "writing_rules_sha256": writing_rules_hash(workspace),
        "intake_folder_index": "evidence/intake.json" if (workspace / "evidence" / "intake.json").is_file() else None,
        "intake_review": intake_review_status(workspace, args.refresh_after_days),
        "onboarding": read_onboarding(workspace)["sections"],
        "sources": rows,
    }, ensure_ascii=False, indent=2))


def safe_job_id(requested: str | None, seed: str) -> str:
    if requested:
        return require_id(requested, "job id")
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def initial_jd(job_id: str, source: str, source_hash: str, text_hash: str, title: str = "") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": job_id,
        "source": source,
        "source_sha256": source_hash,
        "text_sha256": text_hash,
        "fetched_at": now_iso(),
        "title": title,
        "company": "",
        "location": "",
        "compensation": "",
        "responsibilities": [],
        "required_qualifications": [],
        "preferred_qualifications": [],
    }


def job_freshness_days(workspace: Path) -> int:
    path = workspace / "workspace.json"
    if not path.exists():
        return 7
    settings = read_json(path)
    if settings.get("schema_version") != 1:
        raise UserError("workspace.schema_version must be 1")
    days = settings.get("job_freshness_days")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 3650:
        raise UserError("workspace.job_freshness_days must be an integer between 1 and 3650")
    return days


def load_agent_policy(workspace: Path) -> dict[str, Any]:
    path = workspace / "workspace.json"
    settings = read_json(path) if path.exists() else {"schema_version": 1}
    if settings.get("schema_version") != 1:
        raise UserError("workspace.schema_version must be 1")
    agents = require_dict(settings.get("agents", {}), "workspace.agents")
    scoring = require_dict(agents.get("scoring", {}), "workspace.agents.scoring")
    policy = {"max_concurrent": agents.get("max_concurrent", DEFAULT_AGENT_POLICY["max_concurrent"]),
              "scoring": {key: scoring.get(key, value) for key, value in DEFAULT_AGENT_POLICY["scoring"].items()}}
    for label, value in (("agents.max_concurrent", policy["max_concurrent"]),
                         ("agents.scoring.max_concurrent", policy["scoring"]["max_concurrent"]),
                         ("agents.scoring.max_attempts", policy["scoring"]["max_attempts"])):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise UserError(f"workspace.{label} must be a positive integer")
    for field in ("provider", "model", "reasoning_effort"):
        if policy["scoring"][field] is not None:
            policy["scoring"][field] = require_string(policy["scoring"][field], f"workspace.agents.scoring.{field}")
    return policy


def cmd_agent_policy(args: argparse.Namespace) -> None:
    policy = load_agent_policy(workspace_path(args.workspace))
    capacity = args.host_worker_capacity
    if capacity is not None and capacity < 0:
        raise UserError("--host-worker-capacity must be non-negative")
    global_limit = min(policy["max_concurrent"], capacity) if capacity is not None else None
    print(json.dumps({
        "configured": policy,
        "host_subagent_capacity": capacity,
        "host_worker_capacity": capacity,
        "effective_global_limit": global_limit,
        "effective_scoring_limit": min(global_limit, policy["scoring"]["max_concurrent"]) if global_limit is not None else None,
        "execution": "Host agent must schedule and enforce these limits; this command does not launch workers or select a model.",
    }, ensure_ascii=False, indent=2))


def load_document_quality_policy(workspace: Path) -> dict[str, Any]:
    path = workspace / "workspace.json"
    settings = read_json(path) if path.exists() else {"schema_version": 1}
    if settings.get("schema_version") != 1:
        raise UserError("workspace.schema_version must be 1")
    raw = require_dict(settings.get("document_quality", {}), "workspace.document_quality")
    policy = {key: raw.get(key, value) for key, value in DEFAULT_DOCUMENT_QUALITY.items()}
    for key in ("pass_score", "minimum_role_score"):
        value = policy[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise UserError(f"document_quality.{key} must be between 0 and 100")
    count = policy["max_rewrites"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise UserError("document_quality.max_rewrites must be a non-negative integer")
    attempts = policy["max_review_attempts"]
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
        raise UserError("document_quality.max_review_attempts must be a positive integer")
    if not isinstance(policy["execution"], str) or policy["execution"] not in {"auto", "session", "subagent"}:
        raise UserError("document_quality.execution must be auto, session, or subagent")
    for key in ("review_provider", "review_model", "visual_provider", "visual_model"):
        if policy[key] is not None:
            policy[key] = require_string(policy[key], f"document_quality.{key}")
    weights = require_dict(policy["weights"], "document_quality.weights")
    if not {"content", "visual"}.issubset(weights) or set(weights) - {"content", "visual", "ats"}:
        raise UserError("Quality reviewers must include content and visual, with optional ats")
    for weight in weights.values():
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 0 < weight <= 1:
            raise UserError("Quality reviewer weights must be positive and at most 1")
    if abs(sum(weights.values()) - 1) > 1e-9:
        raise UserError("Quality reviewer weights must sum to 1")
    return policy


def parse_timestamp(value: Any, label: str) -> datetime:
    raw = require_string(value, label)
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise UserError(f"{label} must be an ISO timestamp with timezone") from exc
    if result.tzinfo is None:
        raise UserError(f"{label} must include a timezone")
    return result


def initial_job_metadata(identifier: str, observed_at: str | None, ttl_days: int) -> dict[str, Any]:
    observed = parse_timestamp(observed_at, "job.source_observed_at") if observed_at else None
    return {
        "schema_version": 1, "id": identifier, "company_id": None,
        "source_observed_at": observed_at, "last_verified_at": None,
        "expires_at": (observed + timedelta(days=ttl_days)).isoformat() if observed else None,
        "availability": "unknown", "application_deadline": None, "deadline_source": None,
    }


def read_job_metadata(directory: Path) -> dict[str, Any]:
    metadata = read_json(directory / "job.json")
    required = {"schema_version", "id", "company_id", "source_observed_at", "last_verified_at",
                "expires_at", "availability", "application_deadline", "deadline_source"}
    if required - metadata.keys():
        raise UserError("job.json is missing required status fields")
    if metadata.get("schema_version") != 1 or metadata.get("id") != directory.name:
        raise UserError("job.json schema version or id is invalid")
    if metadata.get("availability") not in {"unknown", "open", "closed"}:
        raise UserError("job.availability must be unknown, open, or closed")
    if metadata["availability"] != "unknown" and metadata["last_verified_at"] is None:
        raise UserError("An open/closed availability record needs last_verified_at")
    for field in ("source_observed_at", "last_verified_at", "expires_at", "application_deadline"):
        if metadata.get(field) is not None:
            parse_timestamp(metadata[field], f"job.{field}")
    if metadata.get("company_id") is not None:
        require_id(metadata["company_id"], "job.company_id")
    if metadata.get("application_deadline") is not None:
        require_string(metadata.get("deadline_source"), "job.deadline_source")
    return metadata


def cmd_list_jobs(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    current = datetime.now(timezone.utc)
    rows = []
    for directory in sorted((workspace / "jobs").iterdir()):
        if not directory.is_dir() or not (directory / "jd.json").is_file():
            continue
        row: dict[str, Any] = {"id": directory.name}
        try:
            jd = read_json(directory / "jd.json")
            row.update({"title": jd.get("title", ""), "company": jd.get("company", ""), "location": jd.get("location", "")})
            if not (directory / "job.json").exists():
                row.update({"availability": "unknown", "freshness": "unknown", "expires_at": None,
                            "application_deadline": None, "deadline_passed": None})
            else:
                metadata = read_job_metadata(directory)
                expires = metadata.get("expires_at")
                deadline = metadata.get("application_deadline")
                row.update({key: metadata[key] for key in (
                    "company_id", "source_observed_at", "last_verified_at", "expires_at",
                    "availability", "application_deadline", "deadline_source")})
                row["freshness"] = ("expired" if current >= parse_timestamp(expires, "job.expires_at") else "fresh") if expires else "unknown"
                row["deadline_passed"] = current >= parse_timestamp(deadline, "job.application_deadline") if deadline else None
        except (UserError, OSError) as exc:
            row.update({"freshness": "needs_attention", "error": str(exc)})
        rows.append(row)
    print(json.dumps({"jobs": rows}, ensure_ascii=False, indent=2))


def cmd_record_job_check(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    directory = job_dir(workspace, args.job)
    jd = validate_jd(directory)
    ttl_days = job_freshness_days(workspace)
    path = directory / "job.json"
    metadata = read_job_metadata(directory) if path.exists() else initial_job_metadata(directory.name, jd.get("fetched_at"), ttl_days)
    source = require_string(args.source, "job check source")
    summary = require_string(args.summary, "job check summary")
    deadline = parse_timestamp(args.deadline, "application deadline").isoformat() if args.deadline else None
    if args.deadline and not args.deadline_source:
        raise UserError("--deadline requires --deadline-source for the published deadline")
    if args.deadline_source and not args.deadline:
        raise UserError("--deadline-source requires --deadline")
    if args.availability == "unknown" and (args.deadline or args.clear_deadline):
        raise UserError("Do not change a deadline from an unsuccessful availability check")
    checked_at = now_iso()
    metadata["availability"] = args.availability
    if args.availability != "unknown":
        metadata["last_verified_at"] = checked_at
        metadata["expires_at"] = (parse_timestamp(checked_at, "check time") + timedelta(days=ttl_days)).isoformat()
    if deadline:
        metadata.update({"application_deadline": deadline, "deadline_source": require_string(args.deadline_source, "deadline source")})
    if args.clear_deadline:
        metadata.update({"application_deadline": None, "deadline_source": None})
    event = {"checked_at": checked_at, "availability": args.availability, "source": source,
             "summary": summary, "application_deadline": deadline, "deadline_source": args.deadline_source,
             "cleared_deadline": args.clear_deadline}
    append_text(directory / "checks.jsonl", json.dumps(event, ensure_ascii=False) + "\n")
    write_json(path, metadata)
    print(f"Recorded job check: {path}; unknown results do not extend freshness.")


def cmd_fetch_jd(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    ttl_days = job_freshness_days(workspace)
    final_url, source_bytes, text, title = fetch_public_text(args.url)
    identifier = safe_job_id(args.job, final_url)
    directory = job_dir(workspace, identifier)
    if directory.exists():
        raise UserError(f"Refusing to overwrite existing job directory: {directory}")
    make_dirs(directory)
    source_name = "source.html" if b"<" in source_bytes[:500] else "source.txt"
    save_bytes(directory / source_name, source_bytes)
    save_text(directory / "jd.txt", text)
    jd = initial_jd(identifier, final_url, sha256_bytes(source_bytes), sha256_bytes(text.encode()), title)
    write_json(directory / "jd.json", jd)
    write_json(directory / "job.json", initial_job_metadata(identifier, jd["fetched_at"], ttl_days))
    print(f"Fetched job {identifier}: {final_url}")
    print(f"Review and structure: {directory / 'jd.json'}")


def cmd_import_jd(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    ttl_days = job_freshness_days(workspace)
    source_path = Path(args.file).expanduser().resolve()
    source_bytes = source_path.read_bytes()
    if len(source_bytes) > MAX_DOWNLOAD_BYTES:
        raise UserError(f"JD file exceeded {MAX_DOWNLOAD_BYTES} bytes")
    try:
        text = source_bytes.decode("utf-8").replace("\r\n", "\n").strip() + "\n"
    except UnicodeDecodeError as exc:
        raise UserError("--file must contain UTF-8 JD text; extract image/PDF text with host tools and preserve the original with --attachment") from exc
    attachments = []
    for index, raw_path in enumerate(args.attachment, start=1):
        attachment_path = Path(raw_path).expanduser().resolve()
        data = attachment_path.read_bytes()
        if len(data) > 20_000_000:
            raise UserError("Each JD attachment must be at most 20 MB")
        relative = f"attachments/source-{index}{attachment_path.suffix.lower()}"
        attachments.append((relative, data))
    identifier = safe_job_id(args.job, args.source_url + "\n" + text)
    directory = job_dir(workspace, identifier)
    if directory.exists():
        raise UserError(f"Refusing to overwrite existing job directory: {directory}")
    make_dirs(directory)
    save_bytes(directory / "source.txt", source_bytes)
    save_text(directory / "jd.txt", text)
    jd = initial_jd(identifier, args.source_url, sha256_bytes(source_bytes), sha256_bytes(text.encode()))
    if attachments:
        make_dirs(directory / "attachments")
        jd["attachments"] = []
        for relative, data in attachments:
            save_bytes(directory / relative, data)
            jd["attachments"].append({"path": relative, "sha256": sha256_bytes(data)})
    write_json(directory / "jd.json", jd)
    write_json(directory / "job.json", initial_job_metadata(identifier, jd["fetched_at"], ttl_days))
    print(f"Imported job {identifier}: {directory / 'jd.json'}")


def validate_jd(directory: Path) -> dict[str, Any]:
    jd = read_json(directory / "jd.json")
    if jd.get("schema_version") != 1:
        raise UserError("jd.schema_version must be 1")
    if require_id(jd.get("id"), "jd.id") != directory.name:
        raise UserError("jd.id does not match its directory")
    text_path = directory / "jd.txt"
    if jd.get("text_sha256") != sha256_file(text_path):
        raise UserError("jd.txt changed; reacquire it or intentionally update jd.text_sha256")
    source_paths = [path for path in (directory / "source.html", directory / "source.txt") if path.is_file()]
    if len(source_paths) != 1:
        raise UserError("Expected exactly one source.html or source.txt file")
    if jd.get("source_sha256") != sha256_file(source_paths[0]):
        raise UserError(f"{source_paths[0].name} changed; reacquire the JD")
    require_string(jd.get("source"), "jd.source")
    for field in ("title", "company", "location", "compensation"):
        require_string(jd.get(field), f"jd.{field}", allow_empty=True)
    for field in ("responsibilities", "required_qualifications", "preferred_qualifications"):
        values = require_list(jd.get(field), f"jd.{field}")
        for index, value in enumerate(values):
            require_string(value, f"jd.{field}[{index}]")
    seen_attachments = set()
    for value in require_list(jd.get("attachments", []), "jd.attachments"):
        attachment = require_dict(value, "jd.attachments[]")
        relative = Path(require_string(attachment.get("path"), "jd.attachments[].path"))
        path = directory / relative
        if (relative.is_absolute() or not relative.parts or relative.parts[0] != "attachments"
                or not path.resolve().is_relative_to(directory.resolve())
                or not path.resolve().is_relative_to((directory / "attachments").resolve())):
            raise UserError("JD attachments must remain inside the job's attachments directory")
        if str(relative) in seen_attachments:
            raise UserError("Duplicate JD attachment path")
        seen_attachments.add(str(relative))
        if attachment.get("sha256") != sha256_file(path):
            raise UserError(f"JD attachment changed: {relative}; reacquire the source")
    return jd


def cmd_prepare_resume(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    ensure_onboarding_complete(workspace)
    profile, _ = load_valid_profile(workspace)
    directory = job_dir(workspace, args.job)
    jd = validate_jd(directory)
    output = directory / "resume.json"
    if output.exists() and not args.force:
        raise UserError(f"Refusing to overwrite existing {output}; pass --force to replace it")
    rules = load_writing_rules(workspace, args.job)
    excluded = excluded_evidence(profile, rules)
    retain_file(output)
    write_json(
        output,
        {
            "schema_version": 2,
            "job_id": jd["id"],
            "writing_rules_sha256": writing_rules_hash(workspace),
            "market_sha256": sha256_file(workspace / "market.json"),
            "profile_sha256": sha256_file(workspace / "profile.json"),
            "jd_sha256": sha256_file(directory / "jd.json"),
            "target_role": jd.get("title", ""),
            "summary": [],
            "experience": [
                {"profile_experience_id": item["id"], "bullets": []}
                for item in profile["experience"] if item["id"] not in excluded
            ],
            **{group: [{f"profile_{kind}_id": item["id"], "bullets": []}
                       for item in profile.get(group, []) if item["id"] not in excluded]
               for group, kind in EXPERIENCE_GROUPS.items()},
            "section_order": (["summary", "experience", "projects", "research", "activities", "education", "coursework", "skills"]
                              if profile["experience"] else ["summary", "education", "projects", "research", "coursework", "activities", "experience", "skills"]),
            "education": [
                {"profile_education_id": item["id"]}
                for item in profile["education"] if item["id"] not in excluded
            ],
            "profile_skill_ids": [],
        },
    )
    print(f"Prepared evidence-bound resume plan: {output}")


def validate_claim(claim_value: Any, label: str, evidence: dict[str, dict[str, Any]]) -> None:
    claim = require_dict(claim_value, label)
    require_string(claim.get("text"), f"{label}.text")
    ids = require_list(claim.get("evidence_ids"), f"{label}.evidence_ids")
    if not ids:
        raise UserError(f"{label}.evidence_ids must not be empty")
    for raw_id in ids:
        identifier = require_id(raw_id, f"{label}.evidence_ids")
        if identifier not in evidence:
            raise UserError(f"{label} cites unknown profile evidence id: {identifier}")


def load_valid_resume(workspace: Path, directory: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    profile, evidence = load_valid_profile(workspace)
    jd = validate_jd(directory)
    resume = read_json(directory / "resume.json")
    if resume.get("schema_version") not in {1, 2}:
        raise UserError("resume.schema_version must be 1 or 2")
    if resume["schema_version"] == 2 and ("writing_rules_sha256" not in resume or resume["writing_rules_sha256"] != writing_rules_hash(workspace)):
        raise UserError("Writing rules changed after resume preparation; refresh the plan before rendering")
    if resume.get("job_id") != directory.name:
        raise UserError("resume.job_id does not match its directory")
    if resume.get("market_sha256") != sha256_file(workspace / "market.json"):
        raise UserError("Target-market settings changed after resume preparation; prepare and tailor again")
    if resume.get("profile_sha256") != sha256_file(workspace / "profile.json"):
        raise UserError("Profile changed after resume preparation; prepare and tailor again")
    if resume.get("jd_sha256") != sha256_file(directory / "jd.json"):
        raise UserError("Structured JD changed after resume preparation; prepare and tailor again")
    require_string(resume.get("target_role"), "resume.target_role")
    claim_count = 0
    for index, claim in enumerate(require_list(resume.get("summary"), "resume.summary")):
        validate_claim(claim, f"resume.summary[{index}]", evidence)
        claim_count += 1

    experiences = {item["id"]: item for item in profile["experience"]}
    seen_experiences: set[str] = set()
    for index, item_value in enumerate(require_list(resume.get("experience"), "resume.experience")):
        item = require_dict(item_value, f"resume.experience[{index}]")
        exp_id = require_id(item.get("profile_experience_id"), f"resume.experience[{index}].profile_experience_id")
        if exp_id not in experiences:
            raise UserError(f"Unknown profile experience id: {exp_id}")
        if exp_id in seen_experiences:
            raise UserError(f"Duplicate resume experience id: {exp_id}")
        seen_experiences.add(exp_id)
        for bullet_index, claim in enumerate(require_list(item.get("bullets"), f"resume.experience[{index}].bullets")):
            validate_claim(claim, f"resume.experience[{index}].bullets[{bullet_index}]", evidence)
            own_ids = {exp_id, *(fact["id"] for fact in experiences[exp_id]["bullets"])}
            if not own_ids.intersection(claim["evidence_ids"]):
                raise UserError("An employment claim must cite that employer's entry or one of its own stored facts")
            claim_count += 1

    for group, kind in EXPERIENCE_GROUPS.items():
        entries = {item["id"]: item for item in profile.get(group, [])}
        seen = set()
        for index, raw in enumerate(require_list(resume.get(group, [] if resume["schema_version"] == 1 else None), f"resume.{group}")):
            item = require_dict(raw, f"resume.{group}[{index}]")
            identifier = require_id(item.get(f"profile_{kind}_id"), f"resume.{group}[{index}] reference")
            if identifier not in entries or identifier in seen:
                raise UserError(f"Unknown or duplicate profile {kind} id: {identifier}")
            seen.add(identifier)
            own_ids = {identifier, *(f["id"] for f in entries[identifier]["bullets"])}
            for n, raw_claim in enumerate(require_list(item.get("bullets"), f"resume.{group}[{index}].bullets")):
                validate_claim(raw_claim, f"resume.{group}[{index}].bullets[{n}]", evidence)
                if not own_ids.intersection(raw_claim["evidence_ids"]):
                    raise UserError(f"A {kind} claim must cite that entry or one of its own stored facts")
                claim_count += 1
    if "section_order" in resume:
        order = require_list(resume["section_order"], "resume.section_order")
        if len(order) != len(RESUME_SECTIONS) or any(not isinstance(s, str) for s in order) or set(order) != set(RESUME_SECTIONS):
            raise UserError("section_order must contain each supported section exactly once")

    education = {item["id"]: item for item in profile["education"]}
    for index, item_value in enumerate(require_list(resume.get("education"), "resume.education")):
        item = require_dict(item_value, f"resume.education[{index}]")
        edu_id = require_id(item.get("profile_education_id"), f"resume.education[{index}].profile_education_id")
        if edu_id not in education:
            raise UserError(f"Unknown profile education id: {edu_id}")

    skills = {item["id"]: item for item in profile["skills"]}
    for raw_id in require_list(resume.get("profile_skill_ids"), "resume.profile_skill_ids"):
        skill_id = require_id(raw_id, "resume.profile_skill_ids")
        if skill_id not in skills:
            raise UserError(f"Unknown profile skill id: {skill_id}")
    if claim_count == 0:
        raise UserError("Resume must contain at least one evidence-bound summary or experience claim")
    rules = load_writing_rules(workspace, directory.name)
    validate_writing_constraints(profile, resume, rules, read_json(workspace / "market.json"))
    return profile, jd, resume


def cmd_validate_resume(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    directory = job_dir(workspace, args.job)
    _, _, resume = load_valid_resume(workspace, directory)
    print(f"Resume plan valid for job {resume['job_id']}")


LATEX_REPLACEMENTS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(value: Any) -> str:
    text = str(value)
    return "".join(LATEX_REPLACEMENTS.get(char, char) for char in text)


SECTION_LABELS = {
    "en": {"summary": "Profile", "experience": "Professional Experience", "projects": "Projects",
           "research": "Research", "coursework": "Selected Coursework", "activities": "Community & Other Experience",
           "education": "Education", "skills": "Skills"},
    "zh": {"summary": "个人概述", "experience": "工作经历", "projects": "项目经历", "research": "研究经历",
           "coursework": "相关课程", "activities": "其他经历", "education": "教育背景", "skills": "技能"},
}


def document_labels(market: dict[str, Any]) -> dict[str, str]:
    language = market["language"].lower().split("-")[0]
    overrides = require_dict(market.get("section_labels", {}), "market.section_labels")
    if any(key not in RESUME_SECTIONS for key in overrides):
        raise UserError("Unknown section label override")
    labels = dict(SECTION_LABELS.get(language, {}))
    labels.update({key: require_string(value, f"market.section_labels.{key}") for key, value in overrides.items()})
    if set(labels) != set(RESUME_SECTIONS):
        raise UserError("This output language needs confirmed section_labels for every supported section")
    return labels


def has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def latex_engine(market: dict[str, Any], content: str = "") -> str:
    needs_cjk = market["language"].lower().startswith("zh") or has_cjk(content)
    engine = market.get("latex_engine", "xelatex" if needs_cjk else "pdflatex")
    if engine not in {"pdflatex", "xelatex", "lualatex"}:
        raise UserError("latex_engine must be pdflatex, xelatex, or lualatex")
    if needs_cjk and engine == "pdflatex":
        raise UserError("Chinese/CJK text requires xelatex or lualatex")
    return engine


def entry_dates(entry: dict[str, Any]) -> str:
    start, end = entry.get("start", ""), entry.get("end", "")
    return start if start == end else " -- ".join(value for value in (start, end) if value)


def resume_latex(profile: dict[str, Any], resume: dict[str, Any], market: dict[str, Any]) -> str:
    identity = profile["identity"]
    labels = document_labels(market)
    lines = [r"\begin{center}", rf"{{\LARGE\bfseries {latex_escape(identity['name'])}}}\\[4pt]"]
    contact = [identity.get("email", ""), identity.get("phone", "")]
    if market["address_style"] != "none":
        contact.append(identity.get("location", ""))
    contact.extend(identity.get("links", []))
    lines.extend([r"{\small " + latex_escape(" | ".join(item for item in contact if item)) + "}", r"\end{center}", ""])
    groups = {}
    if resume["summary"]:
        groups["summary"] = [latex_escape(item["text"]) + r"\par" for item in resume["summary"]]
    for group, reference in (("experience", "profile_experience_id"), *[(g, f"profile_{k}_id") for g, k in EXPERIENCE_GROUPS.items()]):
        by_id = {item["id"]: item for item in profile.get(group, [])}
        content = []
        for item in resume.get(group, []):
            if not item["bullets"]:
                continue
            entry = by_id[item[reference]]
            heading = entry["title"] if group == "experience" else entry["name"]
            detail = entry["employer"] if group == "experience" else " / ".join(entry.get(f, "") for f in ("organization", "role") if entry.get(f))
            if entry.get("location"):
                detail = " | ".join(v for v in (detail, entry["location"]) if v)
            dates = entry_dates(entry)
            content.append(r"\JobBotEntry{" + latex_escape(heading) + "}{" + latex_escape(detail) + "}{" + latex_escape(dates) + "}")
            content.append(r"\begin{itemize}")
            content.extend(r"\item " + latex_escape(claim["text"]) for claim in item["bullets"])
            content.append(r"\end{itemize}")
        if content:
            groups[group] = content
    by_id = {item["id"]: item for item in profile["education"]}
    if resume["education"]:
        groups["education"] = []
        for item in resume["education"]:
            edu = by_id[item["profile_education_id"]]
            detail = " | ".join(v for v in (edu["credential"], edu.get("location", "")) if v)
            dates = entry_dates(edu)
            groups["education"].append(r"\JobBotEntry{" + latex_escape(edu["institution"]) + "}{" + latex_escape(detail) + "}{" + latex_escape(dates) + "}")
    by_id = {item["id"]: item for item in profile["skills"]}
    skills = {}
    for identifier in resume["profile_skill_ids"]:
        skill = by_id[identifier]
        skills.setdefault(skill["category"], []).append(skill["name"])
    if skills:
        groups["skills"] = [r"\textbf{" + latex_escape(category) + ":} " + latex_escape(", ".join(names)) + r"\par" for category, names in skills.items()]
    for group in resume.get("section_order", RESUME_SECTIONS):
        if group in groups:
            lines.append(r"\JobBotSection{" + latex_escape(labels[group]) + "}")
            lines.extend(groups[group])
    return "\n".join(lines).rstrip() + "\n"


def cmd_render_latex(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    directory = job_dir(workspace, args.job)
    profile, _, resume = load_valid_resume(workspace, directory)
    market = validate_market(workspace, require_confirmed=True)
    if market["include_photo"]:
        raise UserError("Photo rendering is not implemented; set include_photo false or add a reviewed photo layout")
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count("%%JOBBOT_BODY%%") != 1:
        raise UserError("Resume template must contain exactly one %%JOBBOT_BODY%% marker")
    if template.count("%%JOBBOT_PAPER%%") != 1:
        raise UserError("Resume template must contain exactly one %%JOBBOT_PAPER%% marker")
    document_labels(market)
    body = resume_latex(profile, resume, market)
    engine = latex_engine(market, body)
    paper = "letterpaper" if market["paper_size"] == "letter" else "a4paper"
    language_setup = r"\usepackage[fontset=fandol]{ctex}" if market["language"].lower().startswith("zh") or has_cjk(body) else ""
    output = template.replace("%%JOBBOT_PAPER%%", paper).replace("%%JOBBOT_LANGUAGE_SETUP%%", language_setup).replace("%%JOBBOT_BODY%%", body)
    retain_file(directory / "resume.tex")
    save_text(directory / "resume.tex", output)
    retain_file(directory / "render-inputs.json")
    write_json(directory / "render-inputs.json", {
        "schema_version": 1, "engine": engine, "template_sha256": sha256_file(TEMPLATE),
        "writing_rules_sha256": writing_rules_hash(workspace),
        **{f"{name}_sha256": sha256_file(path) for name, path in {
            "profile": workspace / "profile.json", "market": workspace / "market.json",
            "jd": directory / "jd.json", "resume_json": directory / "resume.json", "latex": directory / "resume.tex"}.items()},
    })
    print(f"Rendered LaTeX: {directory / 'resume.tex'}")


def run_checked(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    check_tree(cwd)
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    write_json(cwd / "command-logs" / f"{uuid.uuid4().hex}.json", {
        "schema_version": 1, "completed_at": now_iso(), "command": command,
        "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
    })
    if result.returncode:
        details = (result.stdout + "\n" + result.stderr).strip()
        raise UserError(f"Command failed ({' '.join(command)}):\n{details[-6000:]}")
    return result


def cmd_render_pdf(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    directory = job_dir(workspace, args.job)
    load_valid_resume(workspace, directory)
    tex_path = directory / "resume.tex"
    if not tex_path.exists():
        raise UserError("Missing resume.tex; run render-latex first")
    market = validate_market(workspace, require_confirmed=True)
    engine = latex_engine(market, tex_path.read_text(encoding="utf-8"))
    manifest = read_json(directory / "render-inputs.json")
    if manifest.get("template_sha256") != sha256_file(TEMPLATE) or manifest.get("writing_rules_sha256") != writing_rules_hash(workspace) or manifest.get("engine") != engine:
        raise UserError("Template, writing rules or engine changed; run render-latex again")
    for name, path in {"profile": workspace / "profile.json", "market": workspace / "market.json", "jd": directory / "jd.json",
                       "resume_json": directory / "resume.json", "latex": tex_path}.items():
        if manifest.get(f"{name}_sha256") != sha256_file(path):
            raise UserError(f"Rendered inputs changed ({name}); run render-latex again")
    executable = shutil.which(engine)
    if not executable:
        raise UserError(f"{engine} is not installed")
    retain_file(directory / "resume.pdf")
    for _ in range(2):
        run_checked([executable, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", tex_path.name], directory)
    pdf_path = directory / "resume.pdf"
    if not pdf_path.exists() or not pdf_path.stat().st_size:
        raise UserError(f"{engine} did not produce a non-empty resume.pdf")
    retain_file(directory / "artifacts.json")
    write_json(
        directory / "artifacts.json",
        {
            "schema_version": 1,
            "generated_at": now_iso(),
            "engine": engine,
            "template_sha256": sha256_file(TEMPLATE),
            "writing_rules_sha256": writing_rules_hash(workspace),
            "market_sha256": sha256_file(workspace / "market.json"),
            "profile_sha256": sha256_file(workspace / "profile.json"),
            "jd_sha256": sha256_file(directory / "jd.json"),
            "resume_json_sha256": sha256_file(directory / "resume.json"),
            "latex_sha256": sha256_file(tex_path),
            "pdf_sha256": sha256_file(pdf_path),
        },
    )
    print(f"Rendered PDF: {pdf_path}")
    print(f"SHA-256: {sha256_file(pdf_path)}")


def parse_pdf_pages(pdfinfo_output: str) -> int:
    match = re.search(r"^Pages:\s+(\d+)\s*$", pdfinfo_output, flags=re.MULTILINE)
    if not match:
        raise UserError("Could not determine PDF page count")
    return int(match.group(1))


def archive_existing_audit(directory: Path) -> None:
    audit_path = directory / "audit.json"
    if not audit_path.exists():
        return
    history = directory / "audit-history"
    make_dirs(history)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    copy_file(audit_path, history / f"audit-{stamp}-{uuid.uuid4().hex}.json")


def cmd_prepare_audit(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    directory = job_dir(workspace, args.job)
    _, _, resume = load_valid_resume(workspace, directory)
    tex_path = directory / "resume.tex"
    pdf_path = directory / "resume.pdf"
    artifacts = read_json(directory / "artifacts.json")
    expected = {
        "market_sha256": sha256_file(workspace / "market.json"),
        "profile_sha256": sha256_file(workspace / "profile.json"),
        "jd_sha256": sha256_file(directory / "jd.json"),
        "resume_json_sha256": sha256_file(directory / "resume.json"),
        "latex_sha256": sha256_file(tex_path),
        "pdf_sha256": sha256_file(pdf_path),
    }
    for key, value in expected.items():
        if artifacts.get(key) != value:
            raise UserError(f"Stale artifact manifest for {key}; rerender the PDF")
    tools = {name: shutil.which(name) for name in ("pdfinfo", "pdftotext", "pdftoppm")}
    missing = [name for name, path in tools.items() if not path]
    if missing:
        raise UserError(f"Missing Poppler tools: {', '.join(missing)}")
    info = run_checked([tools["pdfinfo"] or "pdfinfo", pdf_path.name], directory).stdout
    page_count = parse_pdf_pages(info)
    retain_file(directory / "resume.txt")
    run_checked([tools["pdftotext"] or "pdftotext", pdf_path.name, "resume.txt"], directory)
    page_directory = directory / "audit-pages"
    if page_directory.exists():
        retain_directory(page_directory)
        remove_tree(page_directory)
    make_dirs(page_directory)
    run_checked(
        [tools["pdftoppm"] or "pdftoppm", "-png", "-r", "150", str(pdf_path), str(page_directory / "page")],
        directory,
    )
    pages = sorted(page_directory.glob("page-*.png"))
    if len(pages) != page_count:
        raise UserError(f"Expected {page_count} rendered pages, found {len(pages)}")
    archive_existing_audit(directory)
    relative_pages = [str(path.relative_to(directory)) for path in pages]
    write_json(
        directory / "audit.json",
        {
            "schema_version": 1,
            "job_id": resume["job_id"],
            "prepared_at": now_iso(),
            "market_sha256": expected["market_sha256"],
            "profile_sha256": expected["profile_sha256"],
            "jd_sha256": expected["jd_sha256"],
            "resume_json_sha256": expected["resume_json_sha256"],
            "latex_sha256": expected["latex_sha256"],
            "pdf_sha256": expected["pdf_sha256"],
            "pages": relative_pages,
            "deterministic": {
                "profile_provenance": "passed",
                "artifact_hashes": "passed",
                "pdf_page_count": page_count,
                "extracted_text_characters": len((directory / "resume.txt").read_text(encoding="utf-8", errors="replace")),
            },
            "content": {"status": "pending", "summary": "", "issues": []},
            "visual": {"status": "pending", "summary": "", "issues": [], "reviewed_pages": []},
        },
    )
    print(f"Prepared hash-bound audit: {directory / 'audit.json'}")
    print(f"Inspect every page: {page_directory}")


def validate_review(value: Any, label: str) -> dict[str, Any]:
    review = require_dict(value, label)
    status = require_string(review.get("status"), f"{label}.status")
    if status not in {"pending", "passed", "failed"}:
        raise UserError(f"{label}.status must be pending, passed, or failed")
    require_string(review.get("summary"), f"{label}.summary")
    for index, issue_value in enumerate(require_list(review.get("issues"), f"{label}.issues")):
        issue = require_dict(issue_value, f"{label}.issues[{index}]")
        severity = require_string(issue.get("severity"), f"{label}.issues[{index}].severity")
        if severity not in {"low", "medium", "high"}:
            raise UserError(f"Invalid issue severity: {severity}")
        require_string(issue.get("category"), f"{label}.issues[{index}].category")
        require_string(issue.get("message"), f"{label}.issues[{index}].message")
    return review


def cmd_finalize_audit(args: argparse.Namespace) -> None:
    workspace = workspace_path(args.workspace)
    directory = job_dir(workspace, args.job)
    load_valid_resume(workspace, directory)
    audit = read_json(directory / "audit.json")
    if audit.get("schema_version") != 1 or audit.get("job_id") != directory.name:
        raise UserError("audit schema version or job id is invalid")
    current = {
        "market_sha256": sha256_file(workspace / "market.json"),
        "profile_sha256": sha256_file(workspace / "profile.json"),
        "jd_sha256": sha256_file(directory / "jd.json"),
        "resume_json_sha256": sha256_file(directory / "resume.json"),
        "latex_sha256": sha256_file(directory / "resume.tex"),
        "pdf_sha256": sha256_file(directory / "resume.pdf"),
    }
    for key, value in current.items():
        if audit.get(key) != value:
            raise UserError(f"Audit is stale: {key} changed; prepare and perform the audit again")
    pages = require_list(audit.get("pages"), "audit.pages")
    expected_pages = [str(path.relative_to(directory)) for path in sorted((directory / "audit-pages").glob("page-*.png"))]
    if pages != expected_pages or not expected_pages:
        raise UserError("audit.pages does not match the current generated page images")
    content = validate_review(audit.get("content"), "audit.content")
    visual = validate_review(audit.get("visual"), "audit.visual")
    reviewed_pages = require_list(visual.get("reviewed_pages"), "audit.visual.reviewed_pages")
    if sorted(reviewed_pages) != sorted(pages):
        raise UserError("audit.visual.reviewed_pages must list every current page image")
    if content["status"] != "passed" or visual["status"] != "passed":
        raise UserError("Both content and visual audit statuses must be passed")
    high_issues = [
        issue
        for review in (content, visual)
        for issue in review["issues"]
        if issue["severity"] == "high"
    ]
    if high_issues:
        raise UserError("A passed audit cannot contain high-severity issues")
    if (directory / "quality-loop.json").exists():
        run_checked([sys.executable, str(ROOT / "scripts" / "document_quality.py"),
                     "--workspace", str(workspace), "--job", args.job, "--verify"], directory)
    audit["finalized_at"] = now_iso()
    write_json(directory / "audit.json", audit)
    print(f"Audit finalized for {directory / 'resume.pdf'}")
    print(f"PDF SHA-256: {current['pdf_sha256']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone runtime for the JobBot Agent Skill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a file workspace; new helper files use private permissions")
    init_parser.add_argument("--workspace", required=True)
    init_parser.add_argument("--country", required=True, help="Two-letter target-country code, such as US or GB")
    init_parser.set_defaults(func=cmd_init)

    doctor_parser = subparsers.add_parser("doctor", help="Check optional system tools")
    doctor_parser.set_defaults(func=cmd_doctor)

    agent_policy_parser = subparsers.add_parser("agent-policy", help="Validate worker/model policy and calculate host-bounded concurrency limits")
    agent_policy_parser.add_argument("--workspace", required=True)
    agent_policy_parser.add_argument("--host-worker-capacity", "--host-subagent-capacity", dest="host_worker_capacity", type=int,
                                    help="Available host capacity for the selected delegated model-call route, excluding primary (legacy alias: --host-subagent-capacity)")
    agent_policy_parser.set_defaults(func=cmd_agent_policy)

    profile_parser = subparsers.add_parser("validate-profile", help="Validate profile evidence and IDs")
    profile_parser.add_argument("--workspace", required=True)
    profile_parser.set_defaults(func=cmd_validate_profile)

    upgrade_parser = subparsers.add_parser("upgrade-profile", help="Explicitly upgrade a legacy profile, preserving its prior version")
    upgrade_parser.add_argument("--workspace", required=True)
    upgrade_parser.set_defaults(func=cmd_upgrade_profile)

    rules_parser = subparsers.add_parser("writing-rules", help="Show effective confirmed writing rules")
    rules_parser.add_argument("--workspace", required=True)
    rules_parser.add_argument("--job")
    rules_parser.set_defaults(func=cmd_writing_rules)

    set_rule_parser = subparsers.add_parser("set-writing-rule", help="Save or retire a user-confirmed writing instruction")
    set_rule_parser.add_argument("--workspace", required=True)
    set_rule_parser.add_argument("--id", required=True)
    set_rule_parser.add_argument("--instruction")
    set_rule_parser.add_argument("--scope", choices=("workspace", "market", "job"), default="workspace")
    set_rule_parser.add_argument("--target")
    set_rule_parser.add_argument("--forbid", action="append", default=[])
    set_rule_parser.add_argument("--exclude", action="append", default=[])
    set_rule_parser.add_argument("--confirmation", required=True)
    set_rule_parser.add_argument("--retire", action="store_true")
    set_rule_parser.set_defaults(func=cmd_set_writing_rule)

    status_parser = subparsers.add_parser("onboarding-status", help="Show conversational onboarding progress")
    status_parser.add_argument("--workspace", required=True)
    status_parser.set_defaults(func=cmd_onboarding_status)

    workspace_status_parser = subparsers.add_parser("workspace-status", help="Index saved sources and check reading-note freshness")
    workspace_status_parser.add_argument("--workspace", required=True)
    workspace_status_parser.add_argument("--refresh-after-days", type=int, default=90,
                                         help="Advisory interval for asking about progress (default: 90 days); never blocks generation")
    workspace_status_parser.set_defaults(func=cmd_workspace_status)

    intake_review_parser = subparsers.add_parser("record-intake-review", help="Record a user-confirmed update or no-change check-in")
    intake_review_parser.add_argument("--workspace", required=True)
    intake_review_parser.add_argument("--summary", required=True)
    intake_review_parser.set_defaults(func=cmd_record_intake_review)

    review_parser = subparsers.add_parser("prepare-source-review", help="Prepare hash-bound reading notes for an imported source")
    review_parser.add_argument("--workspace", required=True)
    review_parser.add_argument("--id", required=True)
    review_parser.set_defaults(func=cmd_prepare_source_review)

    confirm_section_parser = subparsers.add_parser("confirm-section", help="Record a section the user explicitly confirmed")
    confirm_section_parser.add_argument("--workspace", required=True)
    confirm_section_parser.add_argument("--section", required=True, choices=ONBOARDING_SECTIONS)
    confirm_section_parser.add_argument("--summary", required=True)
    confirm_section_parser.set_defaults(func=cmd_confirm_section)

    evidence_parser = subparsers.add_parser("import-evidence", help="Copy and hash a user-provided evidence file")
    evidence_parser.add_argument("--workspace", required=True)
    evidence_parser.add_argument("--file", required=True)
    evidence_parser.add_argument("--type", required=True, choices=("resume", "portfolio", "certificate", "transcript", "other"))
    evidence_parser.add_argument("--label", required=True)
    evidence_parser.add_argument("--id")
    evidence_parser.set_defaults(func=cmd_import_evidence)

    github_parser = subparsers.add_parser("import-github", help="Import a public GitHub profile or repository as candidate evidence")
    github_parser.add_argument("--workspace", required=True)
    github_parser.add_argument("--url", required=True)
    github_parser.add_argument("--label")
    github_parser.add_argument("--id")
    github_parser.add_argument("--max-pages", type=int, default=10, help="Maximum public repository-index pages (100 repositories/page); truncation is recorded")
    github_parser.set_defaults(func=cmd_import_github)

    confirm_evidence_parser = subparsers.add_parser("confirm-evidence", help="Record user confirmation of evidence ownership/relevance")
    confirm_evidence_parser.add_argument("--workspace", required=True)
    confirm_evidence_parser.add_argument("--id", required=True)
    confirm_evidence_parser.add_argument("--note", required=True)
    confirm_evidence_parser.set_defaults(func=cmd_confirm_evidence)

    fetch_parser = subparsers.add_parser("fetch-jd", help="Safely fetch a public HTTPS job page")
    fetch_parser.add_argument("--workspace", required=True)
    fetch_parser.add_argument("--url", required=True)
    fetch_parser.add_argument("--job")
    fetch_parser.set_defaults(func=cmd_fetch_jd)

    list_jobs_parser = subparsers.add_parser("list-jobs", help="List local jobs with information expiry and published deadlines")
    list_jobs_parser.add_argument("--workspace", required=True)
    list_jobs_parser.set_defaults(func=cmd_list_jobs)

    check_job_parser = subparsers.add_parser("record-job-check", help="Record an agent's source-backed availability check; does not browse")
    check_job_parser.add_argument("--workspace", required=True)
    check_job_parser.add_argument("--job", required=True)
    check_job_parser.add_argument("--availability", required=True, choices=("open", "closed", "unknown"))
    check_job_parser.add_argument("--source", required=True)
    check_job_parser.add_argument("--summary", required=True)
    deadline_group = check_job_parser.add_mutually_exclusive_group()
    deadline_group.add_argument("--deadline", help="Published application deadline as ISO timestamp with timezone")
    deadline_group.add_argument("--clear-deadline", action="store_true", help="Clear an obsolete deadline based on the successful current source check")
    check_job_parser.add_argument("--deadline-source", help="Locator of the source publishing the deadline")
    check_job_parser.set_defaults(func=cmd_record_job_check)

    import_parser = subparsers.add_parser("import-jd", help="Import user-supplied UTF-8 JD text")
    import_parser.add_argument("--workspace", required=True)
    import_parser.add_argument("--file", required=True)
    import_parser.add_argument("--source-url", required=True, help="Original URL, or a source locator such as user-provided:screenshot when no URL is known")
    import_parser.add_argument("--attachment", action="append", default=[], help="Preserve an original screenshot, PDF, or other source file; repeat for multiple files")
    import_parser.add_argument("--job")
    import_parser.set_defaults(func=cmd_import_jd)

    prepare_parser = subparsers.add_parser("prepare-resume", help="Create a hash-bound resume plan")
    prepare_parser.add_argument("--workspace", required=True)
    prepare_parser.add_argument("--job", required=True)
    prepare_parser.add_argument("--force", action="store_true")
    prepare_parser.set_defaults(func=cmd_prepare_resume)

    validate_resume_parser = subparsers.add_parser("validate-resume", help="Validate profile provenance in resume.json")
    validate_resume_parser.add_argument("--workspace", required=True)
    validate_resume_parser.add_argument("--job", required=True)
    validate_resume_parser.set_defaults(func=cmd_validate_resume)

    latex_parser = subparsers.add_parser("render-latex", help="Render validated resume.json to LaTeX")
    latex_parser.add_argument("--workspace", required=True)
    latex_parser.add_argument("--job", required=True)
    latex_parser.set_defaults(func=cmd_render_latex)

    pdf_parser = subparsers.add_parser("render-pdf", help="Compile resume.tex to a hashed PDF")
    pdf_parser.add_argument("--workspace", required=True)
    pdf_parser.add_argument("--job", required=True)
    pdf_parser.set_defaults(func=cmd_render_pdf)

    audit_parser = subparsers.add_parser("prepare-audit", help="Prepare hash-bound content and visual audit artifacts")
    audit_parser.add_argument("--workspace", required=True)
    audit_parser.add_argument("--job", required=True)
    audit_parser.set_defaults(func=cmd_prepare_audit)

    finalize_parser = subparsers.add_parser("finalize-audit", help="Verify and finalize a completed audit")
    finalize_parser.add_argument("--workspace", required=True)
    finalize_parser.add_argument("--job", required=True)
    finalize_parser.set_defaults(func=cmd_finalize_audit)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except (UserError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
