from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "jobbot_skill.py"


def load_cli_module():
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("jobbot_skill_cli", CLI)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load JobBot Skill CLI module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_cli(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != expect:
        raise AssertionError(
            f"Expected exit {expect}, got {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class JobBotSkillCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "workspace"
        run_cli("init", "--workspace", str(self.workspace), "--country", "US")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_agent_policy_caps_scoring_and_review_against_host_capacity(self) -> None:
        result = json.loads(run_cli("agent-policy", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(result["configured"]["max_concurrent"], 2)
        self.assertIsNone(result["effective_global_limit"])
        self.assertIsNone(result["configured"]["scoring"]["model"])
        result = json.loads(run_cli("agent-policy", "--workspace", str(self.workspace), "--host-subagent-capacity", "1").stdout)
        self.assertEqual(result["effective_global_limit"], 1)
        self.assertEqual(result["effective_scoring_limit"], 1)
        result = json.loads(run_cli("agent-policy", "--workspace", str(self.workspace), "--host-subagent-capacity", "0").stdout)
        self.assertEqual(result["effective_scoring_limit"], 0)
        settings = {"schema_version": 1, "job_freshness_days": 7, "agents": {
            "max_concurrent": 3, "scoring": {"max_concurrent": 2, "model": "fixture-economy-model", "max_attempts": 1},
        }}
        write_json(self.workspace / "workspace.json", settings)
        run_cli("init", "--workspace", str(self.workspace), "--country", "US")
        result = json.loads(run_cli("agent-policy", "--workspace", str(self.workspace), "--host-subagent-capacity", "8").stdout)
        self.assertEqual(result["effective_global_limit"], 3)
        self.assertEqual(result["effective_scoring_limit"], 2)
        self.assertEqual(result["configured"]["scoring"]["model"], "fixture-economy-model")
        self.assertEqual(result["configured"]["scoring"]["max_attempts"], 1)

    def test_agent_policy_supports_legacy_settings_and_rejects_invalid_limits(self) -> None:
        path = self.workspace / "workspace.json"
        write_json(path, {"schema_version": 1, "job_freshness_days": 7})
        result = json.loads(run_cli("agent-policy", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(result["configured"]["scoring"]["max_concurrent"], 2)
        for policy in ({"max_concurrent": 0}, {"max_concurrent": True}, {"scoring": {"max_concurrent": -1}},
                       {"scoring": {"max_attempts": 0}}, {"scoring": {"model": []}}, {"scoring": {"reasoning_effort": " "}}):
            with self.subTest(policy=policy):
                write_json(path, {"schema_version": 1, "job_freshness_days": 7, "agents": policy})
                run_cli("agent-policy", "--workspace", str(self.workspace), expect=2)

    def test_provider_policy_is_opaque_and_does_not_require_a_specific_vendor(self) -> None:
        module = load_cli_module()
        path = self.workspace / "workspace.json"
        for provider in ("anthropic", "openai", "deepseek", "custom-local"):
            with self.subTest(provider=provider):
                write_json(path, {"schema_version": 1, "job_freshness_days": 7,
                                  "agents": {"scoring": {"provider": provider, "model": "fixture-model"}},
                                  "document_quality": {"review_provider": provider, "review_model": "fixture-model",
                                                       "visual_provider": provider, "visual_model": "fixture-vision-model"}})
                policy = json.loads(run_cli("agent-policy", "--workspace", str(self.workspace), "--host-worker-capacity", "1").stdout)
                self.assertEqual(policy["configured"]["scoring"]["provider"], provider)
                self.assertEqual(policy["effective_scoring_limit"], 1)
                quality = module.load_document_quality_policy(self.workspace)
                self.assertEqual(quality["review_provider"], provider)
                self.assertEqual(quality["visual_provider"], provider)
        write_json(path, {"schema_version": 1, "job_freshness_days": 7, "agents": {"scoring": {"provider": []}}})
        run_cli("agent-policy", "--workspace", str(self.workspace), expect=2)

    def test_job_local_expiry_is_configurable_and_inconclusive_checks_do_not_extend_it(self) -> None:
        settings = self.workspace / "workspace.json"
        write_json(settings, {"schema_version": 1, "job_freshness_days": 3})
        run_cli("init", "--workspace", str(self.workspace), "--country", "US")
        self.assertEqual(json.loads(settings.read_text())["job_freshness_days"], 3)
        directory = self.import_job()
        path = directory / "job.json"
        metadata = json.loads(path.read_text())
        observed = datetime.fromisoformat(metadata["source_observed_at"])
        expires = datetime.fromisoformat(metadata["expires_at"])
        self.assertEqual(expires - observed, timedelta(days=3))
        self.assertIsNone(metadata["application_deadline"])
        self.assertEqual(metadata["availability"], "unknown")
        metadata["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        write_json(path, metadata)
        row = json.loads(run_cli("list-jobs", "--workspace", str(self.workspace)).stdout)["jobs"][0]
        self.assertEqual(row["freshness"], "expired")
        self.assertEqual(row["availability"], "unknown")
        before = (directory / "jd.json").read_bytes()
        run_cli("record-job-check", "--workspace", str(self.workspace), "--job", "example-job",
                "--availability", "unknown", "--source", "fixture:unavailable", "--summary", "Source inaccessible; no status conclusion.")
        unknown = json.loads(path.read_text())
        self.assertEqual(unknown["expires_at"], metadata["expires_at"])
        self.assertIsNone(unknown["last_verified_at"])
        run_cli("record-job-check", "--workspace", str(self.workspace), "--job", "example-job",
                "--availability", "open", "--source", "fixture:current-posting", "--summary", "Posting is still open.")
        current = json.loads(path.read_text())
        self.assertEqual(datetime.fromisoformat(current["expires_at"]) - datetime.fromisoformat(current["last_verified_at"]), timedelta(days=3))
        self.assertEqual((directory / "jd.json").read_bytes(), before)
        events = [json.loads(line) for line in (directory / "checks.jsonl").read_text().splitlines()]
        self.assertEqual([event["availability"] for event in events], ["unknown", "open"])

    def test_job_deadline_is_separate_from_local_expiry_and_resume_provenance(self) -> None:
        self.populate_profile()
        directory = self.import_job()
        self.prepare_complete_resume(directory)
        resume_before = (directory / "resume.json").read_bytes()
        deadline = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        args = ("record-job-check", "--workspace", str(self.workspace), "--job", "example-job",
                "--availability", "open", "--source", "fixture:posting", "--summary", "Source includes a published deadline.")
        run_cli(*args, "--deadline", deadline, expect=2)
        self.assertFalse((directory / "checks.jsonl").exists())
        run_cli(*args, "--deadline", deadline, "--deadline-source", "fixture:posting/deadline")
        row = json.loads(run_cli("list-jobs", "--workspace", str(self.workspace)).stdout)["jobs"][0]
        self.assertEqual(row["freshness"], "fresh")
        self.assertTrue(row["deadline_passed"])
        self.assertEqual(row["application_deadline"], deadline)
        run_cli("validate-resume", "--workspace", str(self.workspace), "--job", "example-job")
        self.assertEqual((directory / "resume.json").read_bytes(), resume_before)
        run_cli(*args, "--clear-deadline")
        row = json.loads(run_cli("list-jobs", "--workspace", str(self.workspace)).stdout)["jobs"][0]
        self.assertIsNone(row["deadline_passed"])
        self.assertIsNone(row["application_deadline"])

    def test_legacy_job_status_is_unknown_until_checked_and_closed_history_is_retained(self) -> None:
        directory = self.import_job()
        path = directory / "job.json"
        path.unlink()
        row = json.loads(run_cli("list-jobs", "--workspace", str(self.workspace)).stdout)["jobs"][0]
        self.assertEqual(row["freshness"], "unknown")
        self.assertIsNone(row["expires_at"])
        self.assertFalse(path.exists())
        run_cli("record-job-check", "--workspace", str(self.workspace), "--job", "example-job",
                "--availability", "closed", "--source", "fixture:closed", "--summary", "Source explicitly says closed.")
        row = json.loads(run_cli("list-jobs", "--workspace", str(self.workspace)).stdout)["jobs"][0]
        self.assertEqual(row["availability"], "closed")
        self.assertTrue((directory / "source.txt").exists())
        self.assertTrue((directory / "checks.jsonl").exists())

    def test_storage_validation_rejects_path_ids_bad_policy_and_ambiguous_deadlines(self) -> None:
        directory = self.import_job()
        source = Path(self.temp.name) / "jd.txt"
        result = run_cli("import-jd", "--workspace", str(self.workspace), "--file", str(source),
                         "--source-url", "fixture:test", "--job", "..", expect=2)
        self.assertIn("unsupported characters", result.stderr)
        args = ("record-job-check", "--workspace", str(self.workspace), "--job", "example-job",
                "--availability", "open", "--source", "fixture:test", "--summary", "Checked posting.")
        run_cli(*args, "--deadline", "2030-01-01", "--deadline-source", "fixture:date", expect=2)
        self.assertFalse((directory / "checks.jsonl").exists())
        write_json(self.workspace / "workspace.json", {"schema_version": 1, "job_freshness_days": False})
        result = run_cli("import-jd", "--workspace", str(self.workspace), "--file", str(source),
                         "--source-url", "fixture:new", "--job", "bad-policy", expect=2)
        self.assertIn("job_freshness_days", result.stderr)
        self.assertFalse((self.workspace / "jobs" / "bad-policy").exists())

    def test_visual_job_source_preserves_original_and_detects_attachment_changes(self) -> None:
        module = load_cli_module()
        text = Path(self.temp.name) / "visible-jd.txt"
        text.write_text("Backend Engineer\nPython required\n", encoding="utf-8")
        screenshot = Path(self.temp.name) / "posting.png"
        # Opaque fixture bytes: this test checks preservation, not image recognition.
        screenshot.write_bytes(b"screenshot-source-fixture")
        extra = Path(self.temp.name) / "details.pdf"
        extra.write_bytes(b"pdf-source-fixture")
        run_cli("import-jd", "--workspace", str(self.workspace), "--file", str(text),
                "--source-url", "user-provided:screenshot", "--job", "visual-job",
                "--attachment", str(screenshot), "--attachment", str(extra))
        directory = self.workspace / "jobs" / "visual-job"
        jd = module.validate_jd(directory)
        self.assertEqual(jd["source"], "user-provided:screenshot")
        self.assertEqual(len(jd["attachments"]), 2)
        stored = directory / jd["attachments"][0]["path"]
        self.assertEqual(stored.read_bytes(), screenshot.read_bytes())
        self.assertEqual(jd["attachments"][0]["sha256"], hashlib.sha256(screenshot.read_bytes()).hexdigest())
        stored.write_bytes(b"changed-source")
        with self.assertRaisesRegex(module.UserError, "JD attachment changed"):
            module.validate_jd(directory)

    def test_job_attachment_paths_are_confined_and_binary_is_not_imported_as_text(self) -> None:
        module = load_cli_module()
        directory = self.import_job()
        path = directory / "jd.json"
        jd = json.loads(path.read_text())
        for relative in ("../outside.png", "attachments/../../outside.png", "attachments/../source.txt", ".", str(Path(self.temp.name) / "outside.png")):
            with self.subTest(relative=relative):
                write_json(path, {**jd, "attachments": [{"path": relative, "sha256": "0" * 64}]})
                with self.assertRaisesRegex(module.UserError, "inside the job's attachments directory"):
                    module.validate_jd(directory)
        binary = Path(self.temp.name) / "posting.png"
        binary.write_bytes(b"\x89PNG\r\n\x1a\n")
        result = run_cli("import-jd", "--workspace", str(self.workspace), "--file", str(binary),
                         "--source-url", "user-provided:screenshot", "--job", "bad-image-import", expect=2)
        self.assertIn("UTF-8 JD text", result.stderr)
        self.assertFalse((self.workspace / "jobs" / "bad-image-import").exists())

    def test_preferences_separate_country_restrictions_and_relocation_from_document_market(self) -> None:
        module = load_cli_module()
        path = self.workspace / "preferences.json"
        preferences = module.validate_preferences(self.workspace)
        # A US document preset does not silently impose a US-only job-search rule.
        self.assertEqual(preferences["employment_countries"], {"mode": "unspecified", "countries": []})
        self.assertEqual(preferences["relocation"]["willingness"], "unknown")
        preferences.update({
            "target_roles": [],
            "locations": ["Seattle, WA"],
            "employment_countries": {"mode": "only", "countries": ["US"]},
            "relocation": {"willingness": "conditional", "acceptable_locations": [],
                           "conditions": ["Only for a role and compensation package worth moving for; exact bar to discuss."]},
        })
        write_json(path, preferences)
        self.assertEqual(module.validate_preferences(self.workspace), preferences)
        self.populate_profile()
        before = path.read_bytes()
        run_cli("record-intake-review", "--workspace", str(self.workspace), "--summary", "Country restriction and relocation preferences recorded.")
        self.assertEqual(path.read_bytes(), before)
        # Existing workspaces need no migration; absent fields remain unspecified.
        del preferences["employment_countries"]
        del preferences["relocation"]
        write_json(path, preferences)
        self.assertEqual(module.validate_preferences(self.workspace), preferences)

    def test_preferences_reject_ambiguous_country_rules_and_missing_relocation_conditions(self) -> None:
        module = load_cli_module()
        path = self.workspace / "preferences.json"
        original = json.loads(path.read_text())
        invalid = [
            {"employment_countries": {"mode": "only", "countries": []}},
            {"employment_countries": {"mode": "only", "countries": ["United States"]}},
            {"employment_countries": {"mode": "unspecified", "countries": ["US"]}},
            {"employment_countries": {"mode": "any", "countries": ["US"]}},
            {"employment_countries": {"mode": "maybe", "countries": []}},
            {"relocation": {"willingness": "conditional", "acceptable_locations": [], "conditions": []}},
            {"relocation": {"willingness": "maybe", "acceptable_locations": [], "conditions": []}},
        ]
        for override in invalid:
            with self.subTest(override=override):
                write_json(path, {**original, **override})
                with self.assertRaises(module.UserError):
                    module.validate_preferences(self.workspace)

    def test_intake_checkin_preserves_facts_and_detects_progress(self) -> None:
        self.populate_profile()
        profile_path = self.workspace / "profile.json"
        before = profile_path.read_bytes()
        onboarding_before = (self.workspace / "onboarding.json").read_bytes()
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertIsNone(status["intake_review"]["last_reviewed_at"])
        self.assertFalse(status["intake_review"]["suggest_refresh"])
        run_cli("record-intake-review", "--workspace", str(self.workspace), "--summary", "User confirmed no changes.")
        review = json.loads((self.workspace / "intake.json").read_text())
        self.assertEqual(review["profile_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(profile_path.read_bytes(), before)
        self.assertEqual((self.workspace / "onboarding.json").read_bytes(), onboarding_before)
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(status["intake_review"]["days_since_review"], 0)
        self.assertFalse(status["intake_review"]["suggest_refresh"])
        profile = json.loads(before)
        profile["summary_facts"][0]["text"] = "Completed another backend project."
        write_json(profile_path, profile)
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertTrue(status["intake_review"]["profile_changed_since_review"])
        self.assertTrue(status["intake_review"]["suggest_refresh"])
        self.assertEqual(json.loads((self.workspace / "intake.json").read_text()), review)

    def test_old_intake_can_be_reused_for_another_resume(self) -> None:
        self.populate_profile()
        directory = self.import_job()
        self.prepare_complete_resume(directory)
        run_cli("record-intake-review", "--workspace", str(self.workspace), "--summary", "Initial collection complete.")
        path = self.workspace / "intake.json"
        review = json.loads(path.read_text())
        review["last_reviewed_at"] = (datetime.now(timezone.utc) - timedelta(days=95)).isoformat()
        write_json(path, review)
        before = path.read_bytes()
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertTrue(status["intake_review"]["suggest_refresh"])
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace), "--refresh-after-days", "120").stdout)
        self.assertFalse(status["intake_review"]["suggest_refresh"])
        run_cli("import-jd", "--workspace", str(self.workspace), "--file", str(Path(self.temp.name) / "jd.txt"),
                "--source-url", "fixture:another-job", "--job", "another-job")
        # Reuse the existing confirmations without running another interview/check-in.
        run_cli("prepare-resume", "--workspace", str(self.workspace), "--job", "another-job")
        self.assertTrue((self.workspace / "jobs" / "another-job" / "resume.json").is_file())
        self.assertEqual(path.read_bytes(), before)

    def test_intake_review_rejects_invalid_dates_and_intervals(self) -> None:
        self.populate_profile()
        run_cli("record-intake-review", "--workspace", str(self.workspace), "--summary", "User reviewed facts.")
        path = self.workspace / "intake.json"
        review = json.loads(path.read_text())
        for timestamp in ("not-a-date", "2020-01-01T12:00:00", (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()):
            with self.subTest(timestamp=timestamp):
                review["last_reviewed_at"] = timestamp
                write_json(path, review)
                result = run_cli("workspace-status", "--workspace", str(self.workspace), expect=2)
                self.assertIn("intake.last_reviewed_at", result.stderr)
        result = run_cli("workspace-status", "--workspace", str(self.workspace), "--refresh-after-days", "0", expect=2)
        self.assertIn("must be positive", result.stderr)

    def import_transcript_for_review(self) -> tuple[str, Path]:
        original = Path(self.temp.name) / "transcript.txt"
        original.write_text("Python Programming: A\nEmbedded Systems: A\n", encoding="utf-8")
        run_cli("import-evidence", "--workspace", str(self.workspace),
                "--file", str(original), "--type", "transcript",
                "--label", "Course transcript", "--id", "transcript.term")
        run_cli("prepare-source-review", "--workspace", str(self.workspace), "--id", "transcript.term")
        return "transcript.term", self.workspace / "evidence" / "reviews" / "transcript.term.json"

    def test_source_reviews_resume_intake_without_confirming_inferences(self) -> None:
        identifier, review_path = self.import_transcript_for_review()
        review = json.loads(review_path.read_text())
        source = json.loads((self.workspace / "evidence" / "manifest.json").read_text())["sources"][-1]
        self.assertEqual(review["source_sha256"], source["sha256"])
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(status["sources"][0]["review_status"], "pending")
        review.update({
            "status": "reviewed", "summary": "Strong Python and embedded coursework; explore assignments.",
            "observations": [{"text": "Python Programming: A", "locator": "transcript.txt, line 1"}],
            "candidate_facts": [{"text": "Python project experience to discuss", "locator": "transcript.txt, line 1"}],
            "questions": ["What did you implement for the Python final assignment?"],
        })
        write_json(review_path, review)
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(status["sources"][0]["review_status"], "reviewed")
        self.assertFalse(status["sources"][0]["ownership_confirmed"])
        self.assertIn("evidence/files/transcript.term.txt", status["sources"][0]["files"])
        # Reading an agent interpretation must not promote it into confirmed profile evidence.
        self.populate_profile()
        profile_path = self.workspace / "profile.json"
        profile = json.loads(profile_path.read_text())
        profile["summary_facts"][0]["source_ids"] = [identifier]
        write_json(profile_path, profile)
        result = run_cli("validate-profile", "--workspace", str(self.workspace), expect=2)
        self.assertIn("not yet confirmed", result.stderr)
        preserved = review_path.read_bytes()
        run_cli("prepare-source-review", "--workspace", str(self.workspace), "--id", identifier, expect=2)
        self.assertEqual(review_path.read_bytes(), preserved)

    def test_workspace_status_detects_changed_sources_and_stale_reviews(self) -> None:
        _, review_path = self.import_transcript_for_review()
        review = json.loads(review_path.read_text())
        review["source_sha256"] = "0" * 64
        write_json(review_path, review)
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertEqual(status["sources"][0]["review_status"], "needs_attention")
        self.assertIn("different source snapshot", status["sources"][0]["error"])
        (self.workspace / "evidence" / "files" / "transcript.term.txt").write_text("Changed grade")
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertIn("Evidence source changed", status["sources"][0]["error"])

    def test_source_review_requires_readable_summary_and_locators(self) -> None:
        _, review_path = self.import_transcript_for_review()
        review = json.loads(review_path.read_text())
        review["status"] = "reviewed"
        write_json(review_path, review)
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertIn("review.summary", status["sources"][0]["error"])
        review.update({"summary": "Read the transcript", "observations": [{"text": "Python: A"}]})
        write_json(review_path, review)
        status = json.loads(run_cli("workspace-status", "--workspace", str(self.workspace)).stdout)
        self.assertIn("locator", status["sources"][0]["error"])

    def test_evidence_snapshot_covers_github_files_and_confines_local_paths(self) -> None:
        module = load_cli_module()
        directory = self.workspace / "evidence" / "github" / "example__project"
        directory.mkdir(parents=True)
        contents = [b'{"name":"project"}', b'{"Python":100}', b"# Project\n"]
        for name, data in zip(("repository.json", "languages.json", "README.md"), contents):
            (directory / name).write_bytes(data)
        source = {"id": "github.project", "type": "github", "locator": "https://github.com/example/project",
                  "sha256": hashlib.sha256(b"\0".join(contents)).hexdigest()}
        digest, files = module.evidence_snapshot(self.workspace, source)
        self.assertEqual(digest, source["sha256"])
        self.assertEqual(len(files), 3)
        (directory / "README.md").write_text("Modified")
        with self.assertRaises(module.UserError):
            module.evidence_snapshot(self.workspace, source)
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("private")
        with self.assertRaises(module.UserError):
            module.evidence_snapshot(self.workspace, {
                "id": "outside", "type": "other", "locator": "../outside.txt", "sha256": "",
            })

    def populate_profile(self) -> None:
        write_json(
            self.workspace / "profile.json",
            {
                "schema_version": 2,
                "identity": {
                    "name": "Example Candidate",
                    "email": "candidate@example.com",
                    "phone": "555-0100",
                    "location": "Seattle, WA",
                    "residence_country": "US",
                    "links": ["https://example.com"],
                },
                "work_authorization": [
                    {
                        "country": "US",
                        "status": "User-confirmed authorization",
                        "requires_sponsorship": False,
                        "source_ids": ["user-confirmed"],
                    }
                ],
                "summary_facts": [
                    {"id": "fact.backend", "text": "Builds reliable backend services.", "source_ids": ["user-confirmed"]}
                ],
                "experience": [
                    {
                        "id": "exp.example",
                        "employer": "Example Co",
                        "title": "Software Engineer",
                        "location": "Seattle, WA",
                        "start": "2022",
                        "end": "Present",
                        "source_ids": ["user-confirmed"],
                        "bullets": [
                            {"id": "exp.example.api", "text": "Built a production API in Python.", "source_ids": ["user-confirmed"]}
                        ],
                    }
                ],
                "education": [
                    {
                        "id": "edu.example",
                        "institution": "Example University",
                        "credential": "B.S. Computer Science",
                        "location": "Seattle, WA",
                        "start": "2018",
                        "end": "2022",
                        "source_ids": ["user-confirmed"],
                    }
                ],
                "skills": [
                    {"id": "skill.python", "name": "Python", "category": "Languages", "source_ids": ["user-confirmed"]}
                ],
            },
        )

    def confirm_onboarding(self) -> None:
        for section in ("market", "identity", "experience", "education", "skills", "preferences"):
            run_cli(
                "confirm-section",
                "--workspace",
                str(self.workspace),
                "--section",
                section,
                "--summary",
                f"Fixture confirmed {section}",
            )

    def import_job(self) -> Path:
        source = Path(self.temp.name) / "jd.txt"
        source.write_text(
            "Backend Engineer\nRequired: Python and production API experience.\n",
            encoding="utf-8",
        )
        run_cli(
            "import-jd",
            "--workspace",
            str(self.workspace),
            "--file",
            str(source),
            "--source-url",
            "fixture:test",
            "--job",
            "example-job",
        )
        directory = self.workspace / "jobs" / "example-job"
        jd = json.loads((directory / "jd.json").read_text(encoding="utf-8"))
        jd.update(
            {
                "title": "Backend Engineer",
                "company": "Hiring Co",
                "location": "Seattle, WA",
                "compensation": "$100k-$150k",
                "responsibilities": ["Build backend services"],
                "required_qualifications": ["Python", "Production APIs"],
                "preferred_qualifications": [],
            }
        )
        write_json(directory / "jd.json", jd)
        return directory

    def prepare_complete_resume(self, directory: Path) -> None:
        self.confirm_onboarding()
        run_cli(
            "prepare-resume",
            "--workspace",
            str(self.workspace),
            "--job",
            "example-job",
        )
        resume_path = directory / "resume.json"
        resume = json.loads(resume_path.read_text(encoding="utf-8"))
        resume.update(
            {
                "target_role": "Backend Engineer",
                "summary": [
                    {"text": "Backend engineer focused on reliable services.", "evidence_ids": ["fact.backend"]}
                ],
                "experience": [
                    {
                        "profile_experience_id": "exp.example",
                        "bullets": [
                            {"text": "Built a production Python API.", "evidence_ids": ["exp.example.api", "skill.python"]}
                        ],
                    }
                ],
                "education": [{"profile_education_id": "edu.example"}],
                "profile_skill_ids": ["skill.python"],
            }
        )
        write_json(resume_path, resume)

    def test_file_pipeline_and_optional_pdf_audit(self) -> None:
        self.populate_profile()
        run_cli("validate-profile", "--workspace", str(self.workspace))
        directory = self.import_job()
        self.prepare_complete_resume(directory)
        run_cli("validate-resume", "--workspace", str(self.workspace), "--job", "example-job")
        run_cli("render-latex", "--workspace", str(self.workspace), "--job", "example-job")
        latex = (directory / "resume.tex").read_text(encoding="utf-8")
        self.assertIn("Example Candidate", latex)
        self.assertIn("Built a production Python API", latex)

        required_tools = ("pdflatex", "pdfinfo", "pdftotext", "pdftoppm")
        if not all(shutil.which(tool) for tool in required_tools):
            self.skipTest("LaTeX/Poppler tools unavailable")
        run_cli("render-pdf", "--workspace", str(self.workspace), "--job", "example-job")
        run_cli("prepare-audit", "--workspace", str(self.workspace), "--job", "example-job")
        audit_path = directory / "audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit["content"] = {"status": "passed", "summary": "Claims verified.", "issues": []}
        audit["visual"] = {
            "status": "passed",
            "summary": "All rendered pages inspected.",
            "issues": [],
            "reviewed_pages": audit["pages"],
        }
        write_json(audit_path, audit)
        run_cli("finalize-audit", "--workspace", str(self.workspace), "--job", "example-job")

    def test_unknown_evidence_fails_closed(self) -> None:
        self.populate_profile()
        directory = self.import_job()
        self.prepare_complete_resume(directory)
        resume_path = directory / "resume.json"
        resume = json.loads(resume_path.read_text(encoding="utf-8"))
        resume["summary"][0]["evidence_ids"] = ["invented.claim"]
        write_json(resume_path, resume)
        result = run_cli(
            "validate-resume",
            "--workspace",
            str(self.workspace),
            "--job",
            "example-job",
            expect=2,
        )
        self.assertIn("unknown profile evidence id", result.stderr)

    def test_profile_change_invalidates_resume(self) -> None:
        self.populate_profile()
        directory = self.import_job()
        self.prepare_complete_resume(directory)
        profile_path = self.workspace / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["identity"]["location"] = "Portland, OR"
        write_json(profile_path, profile)
        result = run_cli(
            "validate-resume",
            "--workspace",
            str(self.workspace),
            "--job",
            "example-job",
            expect=2,
        )
        self.assertIn("Profile changed", result.stderr)

    def test_import_refuses_to_overwrite_existing_job(self) -> None:
        self.populate_profile()
        self.import_job()
        source = Path(self.temp.name) / "another-jd.txt"
        source.write_text("Different job\n", encoding="utf-8")
        result = run_cli(
            "import-jd",
            "--workspace",
            str(self.workspace),
            "--file",
            str(source),
            "--source-url",
            "fixture:other",
            "--job",
            "example-job",
            expect=2,
        )
        self.assertIn("Refusing to overwrite", result.stderr)

    def test_source_change_invalidates_jd(self) -> None:
        self.populate_profile()
        self.confirm_onboarding()
        directory = self.import_job()
        (directory / "source.txt").write_text("tampered\n", encoding="utf-8")
        result = run_cli(
            "prepare-resume",
            "--workspace",
            str(self.workspace),
            "--job",
            "example-job",
            expect=2,
        )
        self.assertIn("source.txt changed", result.stderr)

    def test_imported_evidence_requires_user_confirmation(self) -> None:
        self.populate_profile()
        evidence_file = Path(self.temp.name) / "old-resume.txt"
        evidence_file.write_text("Example Candidate resume\n", encoding="utf-8")
        run_cli(
            "import-evidence",
            "--workspace",
            str(self.workspace),
            "--file",
            str(evidence_file),
            "--type",
            "resume",
            "--label",
            "Prior resume",
            "--id",
            "resume.prior",
        )
        profile_path = self.workspace / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["summary_facts"][0]["source_ids"] = ["resume.prior"]
        write_json(profile_path, profile)
        result = run_cli("validate-profile", "--workspace", str(self.workspace), expect=2)
        self.assertIn("not yet confirmed", result.stderr)
        run_cli(
            "confirm-evidence",
            "--workspace",
            str(self.workspace),
            "--id",
            "resume.prior",
            "--note",
            "User confirmed this is their prior resume.",
        )
        run_cli("validate-profile", "--workspace", str(self.workspace))

    def test_target_market_controls_pdf_paper_size(self) -> None:
        self.populate_profile()
        market_path = self.workspace / "market.json"
        market = json.loads(market_path.read_text(encoding="utf-8"))
        market.update(
            {
                "target_country": "GB",
                "locale": "en-GB",
                "language": "en",
                "document_type": "cv",
                "paper_size": "a4",
                "spelling": "en-GB",
            }
        )
        write_json(market_path, market)
        directory = self.import_job()
        self.prepare_complete_resume(directory)
        run_cli("render-latex", "--workspace", str(self.workspace), "--job", "example-job")
        latex = (directory / "resume.tex").read_text(encoding="utf-8")
        self.assertIn("\\documentclass[10pt,a4paper]", latex)

    def test_pdf_hash_helper_is_standard_sha256(self) -> None:
        payload = b"jobbot-skill"
        expected = hashlib.sha256(payload).hexdigest()
        self.assertEqual(len(expected), 64)

    def test_github_profile_and_repository_urls_are_distinguished(self) -> None:
        module = load_cli_module()
        self.assertEqual(
            module.parse_github_url("https://github.com/example-user"),
            ("example-user", None, "https://github.com/example-user"),
        )
        self.assertEqual(
            module.parse_github_url("https://github.com/example-user/example-repo.git"),
            ("example-user", "example-repo", "https://github.com/example-user/example-repo"),
        )

    def test_github_url_rejects_non_root_and_non_https_urls(self) -> None:
        module = load_cli_module()
        for url in (
            "http://github.com/example-user/example-repo",
            "https://github.com/example-user/example-repo/issues",
            "https://example.com/example-user/example-repo",
        ):
            with self.subTest(url=url):
                with self.assertRaises(module.UserError):
                    module.parse_github_url(url)


if __name__ == "__main__":
    unittest.main()
