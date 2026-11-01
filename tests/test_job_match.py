from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import test_cli


class JobMatchTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_cli.JobBotSkillCliTest(methodName="runTest")
        self.fixture.setUp()
        self.fixture.populate_profile()
        self.directory = self.fixture.import_job()
        self.workspace = self.fixture.workspace
        self.match_cli("--prepare")

    def tearDown(self):
        self.fixture.tearDown()

    def match_cli(self, *args, expect=0):
        result = subprocess.run(
            [sys.executable, str(test_cli.ROOT / "scripts" / "job_match.py"),
             "--workspace", str(self.fixture.workspace), "--job", "example-job", *args],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def fill(self, all_scored=False):
        path = self.directory / "match.json"
        record = json.loads(path.read_text())
        for item in record["dimensions"]:
            item.update(reason="Fixture evidence-based judgment", profile_evidence_ids=["fact.backend"],
                        job_references=["jd.required_qualifications[0]"])
            if all_scored:
                item.update(status="scored", value=0.8)
            elif item["id"] in {"role_alignment", "skills"}:
                item.update(status="scored", value=0.8)
            elif item["id"] == "experience_level":
                item.update(status="scored", value=0.6)
            elif item["id"] == "industry":
                item.update(status="not_applicable", value=None)
            else:
                item.update(status="unknown", value=None)
        record["strengths"] = ["Relevant API work in the archive."]
        record["gaps"] = ["Production scope needs careful wording."]
        test_cli.write_json(path, record)
        return record

    def test_weighted_match_excludes_unknown_and_inapplicable_dimensions(self):
        self.fill()
        result = json.loads(self.match_cli().stdout)
        self.assertAlmostEqual(result["score"], 76.92)
        self.assertEqual(result["tier"], "B")
        self.assertAlmostEqual(result["coverage"], 0.7647)
        self.assertEqual(result["assessment_status"], "provisional")

    def test_worker_judgments_publish_only_after_validation_and_preserve_source(self):
        path = self.directory / "match.json"
        seed = path.read_bytes()
        record = self.fill()
        worker = self.workspace / "scoring" / "fixture-batch" / "fixture-task" / "judgments.json"
        worker.parent.mkdir(parents=True)
        test_cli.write_json(worker, record)
        source_before = worker.read_bytes()
        path.write_bytes(seed)
        result = json.loads(self.match_cli("--import-judgments", str(worker)).stdout)
        self.assertEqual(result["score"], 76.92)
        published = json.loads(path.read_text())
        self.assertEqual(published["judgment_source"]["path"], "scoring/fixture-batch/fixture-task/judgments.json")
        self.assertEqual(worker.read_bytes(), source_before)
        history = list((self.directory / "match-history").glob("*.json"))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].read_bytes(), seed)
        # A stale worker cannot overwrite a newer canonical result.
        published_before = path.read_bytes()
        record["profile_sha256"] = "0" * 64
        test_cli.write_json(worker, record)
        self.match_cli("--import-judgments", str(worker), expect=2)
        self.assertEqual(path.read_bytes(), published_before)
        self.assertEqual(len(list((self.directory / "match-history").glob("*.json"))), 1)

    def test_worker_result_must_be_isolated_inside_workspace(self):
        record = self.fill()
        outside = Path(self.fixture.temp.name) / "outside-worker.json"
        test_cli.write_json(outside, record)
        before = (self.directory / "match.json").read_bytes()
        self.match_cli("--import-judgments", str(outside), expect=2)
        self.match_cli("--import-judgments", str(self.directory / "match.json"), expect=2)
        self.assertEqual((self.directory / "match.json").read_bytes(), before)

    def test_hard_conflict_cannot_be_hidden_by_high_soft_match(self):
        record = self.fill(all_scored=True)
        record["hard_constraints"] = [{
            "constraint": "US employment only", "status": "violated",
            "reason": "Fixture posting explicitly requires employment elsewhere.",
            "source_refs": ["preferences.employment_countries", "jd.location"],
        }]
        test_cli.write_json(self.directory / "match.json", record)
        result = json.loads(self.match_cli().stdout)
        self.assertEqual(result["eligibility"], "ineligible")
        self.assertEqual(result["assessment_status"], "ineligible")
        self.assertIsNone(result["score"])
        self.assertIsNone(result["tier"])

    def test_evaluation_failure_or_missing_information_does_not_become_zero(self):
        record = self.fill()
        for item in record["dimensions"]:
            item.update(status="unknown", value=None)
        test_cli.write_json(self.directory / "match.json", record)
        result = json.loads(self.match_cli().stdout)
        self.assertEqual(result["assessment_status"], "insufficient")
        self.assertIsNone(result["score"])
        record["dimensions"][0].update(status="scored", value=True)
        test_cli.write_json(self.directory / "match.json", record)
        before = (self.directory / "match.json").read_bytes()
        self.match_cli(expect=2)
        self.assertEqual((self.directory / "match.json").read_bytes(), before)

    def test_changed_inputs_require_reassessment_and_refresh_retains_history(self):
        self.fill()
        self.match_cli()
        before = (self.directory / "match.json").read_bytes()
        preferences = json.loads((self.workspace / "preferences.json").read_text())
        preferences["locations"] = ["Seattle, WA"]
        test_cli.write_json(self.workspace / "preferences.json", preferences)
        result = self.match_cli(expect=2)
        self.assertIn("preferences_sha256 changed", result.stderr)
        self.assertEqual((self.directory / "match.json").read_bytes(), before)
        self.match_cli("--prepare", expect=2)
        history_before = len(list((self.directory / "match-history").glob("*.json")))
        self.match_cli("--prepare", "--force")
        history = list((self.directory / "match-history").glob("*.json"))
        self.assertEqual(len(history), history_before + 1)
        self.assertTrue(any(path.read_bytes() == before for path in history))

    def test_repeated_checks_preserve_reviewed_bytes_timestamp_and_mtime(self):
        self.fill()
        self.match_cli()
        path = self.directory / "match.json"
        record = json.loads(path.read_text())
        record["prepared_at"] = "2020-01-01T00:00:00+00:00"
        record["scored_at"] = "2020-01-02T00:00:00+00:00"
        test_cli.write_json(path, record)
        before, stamp = path.read_bytes(), path.stat().st_mtime_ns
        history_before = list((self.directory / "match-history").glob("*.json"))
        self.match_cli("--verify")
        self.match_cli()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, stamp)
        self.assertEqual(list((self.directory / "match-history").glob("*.json")), history_before)

    def test_verify_is_read_only_even_when_recalculation_is_needed(self):
        path = self.directory / "match.json"
        self.fill()
        before = path.read_bytes()
        self.match_cli("--verify", expect=2)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.directory / "match-history").exists())
        self.match_cli()
        record = json.loads(path.read_text())
        record["score"] = 1
        test_cli.write_json(path, record)
        before = path.read_bytes()
        self.match_cli("--verify", expect=2)
        self.assertEqual(path.read_bytes(), before)
        self.match_cli("--verify", "--prepare", expect=2)
        self.assertEqual(path.read_bytes(), before)

    def test_closed_job_is_distinct_from_match_and_status_refresh_stales_assessment(self):
        self.fill(all_scored=True)
        test_cli.run_cli("record-job-check", "--workspace", str(self.workspace), "--job", "example-job",
                         "--availability", "closed", "--source", "fixture:closed", "--summary", "Posting explicitly closed.")
        self.assertIn("job_status_sha256 changed", self.match_cli(expect=2).stderr)
        self.match_cli("--prepare", "--force")
        self.fill(all_scored=True)
        result = json.loads(self.match_cli().stdout)
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["tier"], "A")
        self.assertEqual(result["assessment_status"], "not_current")

    def test_invalid_judgments_fail_closed(self):
        original = self.fill()
        cases = []
        for field, value in (("value", float("nan")), ("value", 10**400), ("status", []), ("weight", -0.1), ("profile_evidence_ids", ["invented.fact"])):
            record = json.loads(json.dumps(original))
            record["dimensions"][0][field] = value
            cases.append(record)
        record = json.loads(json.dumps(original))
        record["dimensions"][0]["id"] = record["dimensions"][1]["id"]
        cases.append(record)
        for record in cases:
            with self.subTest(record=record):
                test_cli.write_json(self.directory / "match.json", record)
                self.match_cli(expect=2)

    def test_required_fields_and_explicit_nulls_are_validated(self):
        original = self.fill()
        cases = []
        for field in ("prepared_at", "job_status_sha256"):
            record = json.loads(json.dumps(original))
            del record[field]
            cases.append(record)
        record = json.loads(json.dumps(original))
        del record["dimensions"][2]["value"]
        cases.append(record)
        record = json.loads(json.dumps(original))
        record["prepared_at"] = "2026-01-01"
        cases.append(record)
        for record in cases:
            test_cli.write_json(self.directory / "match.json", record)
            self.match_cli(expect=2)

    def test_unknown_constraints_expired_sources_and_zero_weight_unknowns_remain_provisional(self):
        test_cli.run_cli("record-job-check", "--workspace", str(self.workspace), "--job", "example-job",
                         "--availability", "open", "--source", "fixture:current", "--summary", "Source explicitly open.")
        self.match_cli("--prepare", "--force")
        record = self.fill(all_scored=True)
        self.assertEqual(json.loads(self.match_cli().stdout)["assessment_status"], "complete")
        record["hard_constraints"] = [{"constraint": "Employment location", "status": "unknown",
                                        "reason": "Exact arrangement not provided.", "source_refs": ["jd.location"]}]
        test_cli.write_json(self.directory / "match.json", record)
        result = json.loads(self.match_cli().stdout)
        self.assertEqual(result["eligibility"], "unknown")
        self.assertEqual(result["assessment_status"], "provisional")
        record["hard_constraints"] = []
        record["dimensions"][0]["weight"] += record["dimensions"][3]["weight"]
        record["dimensions"][3].update(weight=0, status="unknown", value=None)
        test_cli.write_json(self.directory / "match.json", record)
        self.assertEqual(json.loads(self.match_cli().stdout)["assessment_status"], "provisional")
        metadata = json.loads((self.directory / "job.json").read_text())
        metadata["expires_at"] = "2020-01-01T00:00:00Z"
        test_cli.write_json(self.directory / "job.json", metadata)
        self.match_cli("--prepare", "--force")
        self.fill(all_scored=True)
        result = json.loads(self.match_cli().stdout)
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["assessment_status"], "provisional")

    def test_displayed_score_and_tier_use_consistent_boundaries(self):
        for value, score, tier in ((0.8, 80, "A"), (0.65, 65, "B"), (0.5, 50, "C"), (0.499, 49.9, "D"), (0.799999, 80, "A")):
            with self.subTest(value=value):
                record = self.fill(all_scored=True)
                for item in record["dimensions"]:
                    item["value"] = value
                test_cli.write_json(self.directory / "match.json", record)
                result = json.loads(self.match_cli().stdout)
                self.assertEqual(result["score"], score)
                self.assertEqual(result["tier"], tier)


if __name__ == "__main__":
    unittest.main()
