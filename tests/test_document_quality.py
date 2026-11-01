from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest

import test_cli


class DocumentQualityTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_cli.JobBotSkillCliTest(methodName="runTest")
        self.fixture.setUp()
        self.fixture.populate_profile()
        self.directory = self.fixture.import_job()
        self.fixture.prepare_complete_resume(self.directory)
        self.workspace = self.fixture.workspace
        self.render_fixture("initial")

    def tearDown(self):
        self.fixture.tearDown()

    def command(self, *args, expect=0):
        result = subprocess.run(
            [sys.executable, str(test_cli.ROOT / "scripts" / "document_quality.py"),
             "--workspace", str(self.workspace), "--job", "example-job", *args],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def render_fixture(self, marker):
        test_cli.run_cli("render-latex", "--workspace", str(self.workspace), "--job", "example-job")
        # Opaque synthetic artifact bytes test bookkeeping, not PDF/image decoding or model judgment.
        (self.directory / "resume.pdf").write_bytes(b"fixture-pdf:" + marker.encode())
        (self.directory / "resume.txt").write_text("Fixture resume text " + marker)
        pages = self.directory / "audit-pages"
        pages.mkdir(exist_ok=True)
        (pages / "page-1.png").write_bytes(b"fixture-image:" + marker.encode())
        files = {"profile_sha256": self.workspace / "profile.json", "market_sha256": self.workspace / "market.json",
                 "jd_sha256": self.directory / "jd.json", "resume_json_sha256": self.directory / "resume.json",
                 "latex_sha256": self.directory / "resume.tex", "pdf_sha256": self.directory / "resume.pdf"}
        hashes = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in files.items()}
        test_cli.write_json(self.directory / "artifacts.json", {"schema_version": 1, **hashes})
        test_cli.write_json(self.directory / "audit.json", {
            "schema_version": 1, "job_id": "example-job", **hashes, "pages": ["audit-pages/page-1.png"],
            "content": {"status": "pending", "summary": "", "issues": []},
            "visual": {"status": "pending", "summary": "", "issues": [], "reviewed_pages": []},
        })

    def start(self, *args):
        result = json.loads(self.command("--prepare", "--writer-id", "fixture-primary", *args).stdout)
        self.packet_path = self.workspace / result["packet"]
        self.packet = json.loads(self.packet_path.read_text())
        return result

    def report(self, role, score=90, high=False, unavailable=False, reviewer_id=None):
        path = self.workspace / self.packet["report_paths"][role]
        value = {
            "schema_version": 1, "role": role,
            "packet_sha256": hashlib.sha256(self.packet_path.read_bytes()).hexdigest(),
            "pdf_sha256": self.packet["pdf_sha256"], "execution_kind": "session",
            "reviewer_id": reviewer_id or f"fixture-{role}-session",
            "status": "unavailable" if unavailable else "completed",
            "score": None if unavailable else score, "summary": "Synthetic fixture review only.",
            "issues": ([{"severity": "high" if high else "medium", "category": "layout", "locator": "resume.pdf#page1",
                         "message": "Fixture issue to address.", "suggestion": "Shorten the fixture sentence."}]
                       if high or (score is not None and score < 80) else []),
        }
        if role == "visual" and not unavailable:
            value["reviewed_page_hashes"] = self.packet["pages"]
        test_cli.write_json(path, value)
        return path

    def material_report(self):
        path = self.report("content", 100)
        value = json.loads(path.read_text())
        value["next_action"] = "collect_evidence"
        value["issues"] = [{
            "severity": "medium", "category": "material_gap", "locator": "profile.json#/experience/0",
            "message": "The source describes a project but omits the candidate's contribution.",
            "suggestion": "Which component did you implement, and what evidence describes the result?",
        }]
        test_cli.write_json(path, value)
        return path

    def test_material_gap_blocks_perfect_scores_and_finalization(self):
        self.start()
        self.material_report()
        self.report("visual", 100)
        outcome = json.loads(self.command().stdout)
        self.assertEqual(outcome["overall_score"], 100)
        self.assertEqual(outcome["decision"], "needs_material")
        self.assertEqual(outcome["next_action"], "collect_evidence")
        self.assertNotIn("audit_sections", outcome)
        self.assertEqual(outcome["issues"][0]["category"], "material_gap")
        self.command("--verify", expect=2)
        test_cli.run_cli("finalize-audit", "--workspace", str(self.workspace), "--job", "example-job", expect=2)
        audit = json.loads((self.directory / "audit.json").read_text())
        self.assertEqual(audit["content"]["status"], "pending")
        state = json.loads((self.directory / "quality-loop.json").read_text())
        self.assertEqual(len(state["rounds"]), 1)
        self.assertEqual(outcome["rewrites_used"], 0)

    def test_material_collection_at_budget_limit_stays_exhausted(self):
        settings = json.loads((self.workspace / "workspace.json").read_text())
        settings["document_quality"]["max_rewrites"] = 0
        test_cli.write_json(self.workspace / "workspace.json", settings)
        self.start()
        self.material_report()
        self.report("visual", 100)
        outcome = json.loads(self.command().stdout)
        self.assertEqual(outcome["decision"], "exhausted")
        self.assertEqual(outcome["next_action"], "collect_evidence")
        before = (self.directory / "quality-loop.json").read_bytes()
        prefs = self.workspace / "preferences.json"
        value = json.loads(prefs.read_text())
        value["notes"] = ["Focused answer supplied after material request."]
        test_cli.write_json(prefs, value)
        result = self.command("--prepare", "--writer-id", "fixture-primary", "--new-version", "--reason", "Focused answer", expect=2)
        self.assertIn("budget exhausted", result.stderr)
        self.assertEqual((self.directory / "quality-loop.json").read_bytes(), before)

    def test_material_collection_waits_for_missing_or_unavailable_visual_review(self):
        self.start()
        self.material_report()
        for unavailable in (False, True):
            with self.subTest(unavailable=unavailable):
                if unavailable:
                    self.report("visual", unavailable=True)
                outcome = json.loads(self.command().stdout)
                self.assertEqual(outcome["decision"], "blocked")
                self.assertEqual(outcome["next_action"], "collect_evidence")
                self.assertIsNone(outcome["overall_score"])
        self.report("visual", 100)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "needs_material")
        state = json.loads((self.directory / "quality-loop.json").read_text())
        self.assertEqual(len(state["rounds"]), 1)

    def test_blocked_collection_report_cannot_be_replaced_to_erase_material_gate(self):
        self.start()
        content = self.material_report()
        original_content = content.read_bytes()
        outcome = json.loads(self.command().stdout)
        self.assertEqual(outcome["decision"], "blocked")
        self.report("visual", 100)
        state_path = self.directory / "quality-loop.json"
        outcome_path = self.packet_path.parent / "outcome.json"
        saved_paths = (state_path, outcome_path, self.directory / "quality.json", self.directory / "audit.json")
        saved = {path: path.read_bytes() for path in saved_paths}
        history_path = self.packet_path.parent / "history" / "outcome.json"
        before_history = sorted(history_path.glob("*.json"))
        for replacement in ("passed", "unavailable", "deleted"):
            with self.subTest(replacement=replacement):
                if replacement == "deleted":
                    content.unlink()
                else:
                    self.report("content", 100, unavailable=replacement == "unavailable")
                self.assertIn("completed content review requesting material collection changed", self.command(expect=2).stderr)
                self.command("--verify", expect=2)
                self.assertEqual({path: path.read_bytes() for path in saved_paths}, saved)
                self.assertEqual(sorted(history_path.glob("*.json")), before_history)
        content.write_bytes(original_content)
        completed = json.loads(self.command().stdout)
        self.assertEqual(completed["decision"], "needs_material")
        self.assertEqual(completed["next_action"], "collect_evidence")
        self.assertEqual(completed["review_files"][self.packet["report_paths"]["content"]],
                         outcome["review_files"][self.packet["report_paths"]["content"]])
        state = json.loads(state_path.read_text())
        self.assertEqual(len(state["rounds"]), 1)
        self.assertEqual(state["round_limit"], 3)
        self.assertEqual(completed["rewrites_used"], 0)
        historical = [json.loads(path.read_text()) for path in history_path.glob("*.json")]
        self.assertTrue(any(item["decision"] == "blocked" and item.get("next_action") == "collect_evidence"
                            for item in historical))

    def test_noncollection_blocked_review_can_still_clarify_missing_feedback(self):
        self.start()
        content = self.report("content", 60)
        value = json.loads(content.read_text())
        value["issues"] = []
        test_cli.write_json(content, value)
        self.report("visual", 100)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "blocked")
        self.report("content", 60)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "rewrite")
        self.assertEqual(len(json.loads((self.directory / "quality-loop.json").read_text())["rounds"]), 1)

    def test_collect_evidence_requires_completed_content_and_actionable_material_gap(self):
        self.start()
        content = self.material_report()
        self.report("visual", 100)
        original = json.loads(content.read_text())
        cases = [
            {"next_action": "ask_user"}, {"next_action": None}, {"next_action": []},
            {"status": "unavailable", "score": None}, {"issues": []},
            {"issues": [{**original["issues"][0], "severity": "low"}]},
            {"issues": [{**original["issues"][0], "category": "layout"}]},
            *[{"issues": [{**original["issues"][0], field: " "}]} for field in ("locator", "message", "suggestion")],
        ]
        for patch in cases:
            with self.subTest(patch=patch):
                test_cli.write_json(content, {**original, **patch})
                self.command(expect=2)
        test_cli.write_json(content, original)
        visual = self.report("visual", 100)
        value = json.loads(visual.read_text())
        value.update(next_action="collect_evidence", issues=original["issues"])
        test_cli.write_json(visual, value)
        self.assertIn("Only a completed content review", self.command(expect=2).stderr)

    def test_legacy_absent_and_explicit_noncollection_actions_remain_readable(self):
        self.start()
        content = self.report("content", 100)
        self.report("visual", unavailable=True)
        for action in (None, "none", "rewrite"):
            value = json.loads(content.read_text())
            if action is not None:
                value["next_action"] = action
            test_cli.write_json(content, value)
            self.assertEqual(json.loads(self.command().stdout)["decision"], "blocked")
        value["next_action"] = "none"
        test_cli.write_json(content, value)
        self.report("visual", 100)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "passed")
        self.command("--verify")

    def test_material_collection_verification_rejects_forged_pass(self):
        self.start()
        self.material_report()
        self.report("visual", 100)
        outcome = json.loads(self.command().stdout)
        # Even rewriting stored decisions and keeping report hashes/scores consistent cannot pass this gate.
        outcome["decision"] = "passed"
        outcome.pop("next_action")
        test_cli.write_json(self.directory / "quality.json", outcome)
        state_path = self.directory / "quality-loop.json"
        state = json.loads(state_path.read_text())
        state["rounds"][-1]["decision"] = "passed"
        state["rounds"][-1].pop("next_action")
        test_cli.write_json(state_path, state)
        self.assertIn("requires material collection", self.command("--verify", expect=2).stderr)

    def test_material_collection_requires_context_change_and_preserves_round_history(self):
        self.start()
        self.material_report()
        self.report("visual", 100)
        self.command()
        prior_packet = self.packet_path
        prior_outcome = prior_packet.parent / "outcome.json"
        prior_bytes = prior_packet.read_bytes(), prior_outcome.read_bytes()
        state_path = self.directory / "quality-loop.json"
        before = state_path.read_bytes()
        args = ("--prepare", "--writer-id", "fixture-primary", "--new-version", "--reason", "Focused follow-up")
        self.command(*args, expect=2)
        prefs = self.workspace / "preferences.json"
        value = json.loads(prefs.read_text())
        prefs.write_text(json.dumps(value, separators=(",", ":")))
        self.command(*args, expect=2)
        self.revise("Wording only cannot answer the missing question")
        self.assertIn("substantive context changes", self.command(*args, expect=2).stderr)
        self.assertEqual(state_path.read_bytes(), before)
        value["notes"] = ["Focused answer supplied after material request."]
        test_cli.write_json(prefs, value)
        self.start("--new-version", "--reason", "Focused answer recorded in context")
        state = json.loads(state_path.read_text())
        self.assertEqual(len(state["rounds"]), 2)
        self.assertEqual(state["round_limit"], 3)
        self.assertEqual(state["rounds"][0]["decision"], "needs_material")
        self.assertEqual(self.packet["round_index"], 1)
        self.assertEqual((prior_packet.read_bytes(), prior_outcome.read_bytes()), prior_bytes)
        self.report("content", 100)
        self.report("visual", 100)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "passed")
        self.command("--verify")

    def test_passing_panel_binds_snapshot_and_final_audit_without_extra_model(self):
        self.start()
        self.report("content", 90)
        self.report("visual", 85)
        outcome = json.loads(self.command().stdout)
        self.assertEqual(outcome["decision"], "passed")
        self.assertEqual(outcome["overall_score"], 88)
        self.command("--verify")
        test_cli.run_cli("finalize-audit", "--workspace", str(self.workspace), "--job", "example-job")
        self.command("--verify")
        self.assertEqual(json.loads((self.directory / "audit.json").read_text())["content"], outcome["audit_sections"]["content"])

    def test_rewrite_budget_and_feedback_are_required_and_preserved(self):
        settings = json.loads((self.workspace / "workspace.json").read_text())
        settings["document_quality"]["max_rewrites"] = 1
        test_cli.write_json(self.workspace / "workspace.json", settings)
        self.start()
        self.report("content", 70)
        self.report("visual", 70)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "rewrite")
        self.command("--prepare", "--writer-id", "fixture-primary", expect=2)
        prior_round = self.packet["round_id"]
        prior_pdf = self.workspace / next(item["snapshot_path"] for item in self.packet["files"] if item["original_path"].endswith("resume.pdf"))
        prior_bytes = prior_pdf.read_bytes()
        plan = json.loads((self.directory / "resume.json").read_text())
        plan["summary"][0]["text"] = "Backend engineer building reliable Python APIs."
        test_cli.write_json(self.directory / "resume.json", plan)
        self.render_fixture("revision-one")
        notes = self.directory / "revision-notes.json"
        test_cli.write_json(notes, {"previous_round_id": prior_round, "changes": [
            {"finding_locator": "resume.pdf#page1", "action": "shortened summary", "explanation": "Addressed fixture feedback."}]})
        self.start("--revision-notes", str(notes))
        self.report("content", 70)
        self.report("visual", 70)
        outcome = json.loads(self.command().stdout)
        self.assertEqual(outcome["decision"], "exhausted")
        self.assertEqual(outcome["rewrites_used"], 1)
        self.assertEqual(prior_pdf.read_bytes(), prior_bytes)
        self.command("--prepare", "--writer-id", "fixture-primary", "--revision-notes", str(notes), expect=2)
        test_cli.run_cli("finalize-audit", "--workspace", str(self.workspace), "--job", "example-job", expect=2)

    def test_low_role_score_or_high_issue_cannot_be_hidden_by_average(self):
        self.start()
        self.report("content", 100)
        self.report("visual", 60)
        outcome = json.loads(self.command().stdout)
        self.assertGreater(outcome["overall_score"], 80)
        self.assertEqual(outcome["decision"], "rewrite")

    def test_high_severity_blocks_even_with_perfect_scores(self):
        self.start()
        self.report("content", 100, high=True)
        self.report("visual", 100)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "rewrite")

    def test_unavailable_review_blocks_without_zero_or_consuming_rewrite(self):
        self.start()
        self.report("content", 90)
        self.report("visual", unavailable=True)
        outcome = json.loads(self.command().stdout)
        self.assertEqual(outcome["decision"], "blocked")
        self.assertIsNone(outcome["overall_score"])
        self.assertEqual(outcome["rewrites_used"], 0)
        self.report("visual", 90)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "passed")
        history = self.packet_path.parent / 'history' / 'outcome.json'
        old_outcomes = [json.loads(path.read_text()) for path in history.glob('*.json')]
        self.assertTrue(any(value['decision'] == 'blocked' for value in old_outcomes))

    def test_changed_images_and_completed_reports_invalidate_approval(self):
        self.start()
        content_path = self.report("content", 90)
        self.report("visual", 90)
        self.command()
        report = json.loads(content_path.read_text())
        report["summary"] = "Changed after approval."
        test_cli.write_json(content_path, report)
        self.command("--verify", expect=2)
        test_cli.run_cli("finalize-audit", "--workspace", str(self.workspace), "--job", "example-job", expect=2)

    def test_visual_coverage_and_independent_identity_are_required(self):
        self.start()
        self.report("content", 90, reviewer_id="fixture-primary")
        visual_path = self.report("visual", 90)
        self.command(expect=2)
        self.report("content", 90)
        report = json.loads(visual_path.read_text())
        report["reviewed_page_hashes"] = {}
        test_cli.write_json(visual_path, report)
        self.command(expect=2)
        self.report("visual", 90)
        (self.directory / "audit-pages" / "page-1.png").write_bytes(b"changed fixture")
        self.command(expect=2)

    def test_explicit_session_route_is_not_silently_replaced_with_a_subagent(self):
        settings = json.loads((self.workspace / "workspace.json").read_text())
        settings["document_quality"]["execution"] = "session"
        test_cli.write_json(self.workspace / "workspace.json", settings)
        self.start()
        content = self.report("content", 90)
        self.report("visual", 90)
        value = json.loads(content.read_text())
        value["execution_kind"] = "subagent"
        test_cli.write_json(content, value)
        self.assertIn("frozen session/subagent choice", self.command(expect=2).stderr)
        self.report("content", 90)
        self.assertEqual(json.loads(self.command().stdout)["decision"], "passed")

    def test_snapshot_storage_cannot_follow_a_symlink_outside_the_workspace(self):
        outside = self.workspace.parent / "outside-quality"
        outside.mkdir()
        (self.directory / "quality-rounds").symlink_to(outside, target_is_directory=True)
        self.command("--prepare", "--writer-id", "fixture-primary", expect=2)
        self.assertEqual(list(outside.iterdir()), [])

    def revise(self, marker):
        plan = json.loads((self.directory / 'resume.json').read_text())
        plan['summary'][0]['text'] = 'Backend engineer building Python APIs. ' + marker
        test_cli.write_json(self.directory / 'resume.json', plan)
        self.render_fixture(marker)

    def test_pending_round_can_be_superseded_without_losing_shared_budget(self):
        self.start()
        first = self.packet
        self.command('--prepare', '--writer-id', 'fixture-primary', '--new-version', '--reason', 'User asks for revision', expect=2)
        self.revise('User-requested wording')
        self.start('--new-version', '--reason', 'User requests a revised summary')
        state = json.loads((self.directory / 'quality-loop.json').read_text())
        self.assertEqual(len(state['rounds']), 2)
        self.assertEqual(state['rounds'][0]['decision'], 'pending')
        self.assertEqual(state['versions'][1]['parent_id'], state['versions'][0]['id'])
        self.assertEqual(state['round_limit'], 3)
        prior_source = next(item for item in first['files'] if item['original_path'] == 'profile.json')
        current_source = next(item for item in self.packet['files'] if item['original_path'] == 'profile.json')
        self.assertEqual(prior_source['snapshot_path'], current_source['snapshot_path'])

    def test_passed_version_can_be_corrected_and_requires_fresh_panel(self):
        self.start()
        self.report('content')
        self.report('visual')
        self.command()
        first_packet = self.packet_path.read_bytes()
        # A context correction must refresh the plan and renderer, but must not require changing old frozen originals back.
        preferences = json.loads((self.workspace / 'preferences.json').read_text())
        preferences['notes'] = ['User now prefers a smaller team.']
        test_cli.write_json(self.workspace / 'preferences.json', preferences)
        self.revise('Revised by the user')
        self.start('--new-version', '--reason', 'User corrected preferences and wording')
        self.command('--verify', expect=2)
        self.report('content')
        self.report('visual')
        self.assertEqual(json.loads(self.command().stdout)['decision'], 'passed')
        self.command('--verify')
        state = json.loads((self.directory / 'quality-loop.json').read_text())
        self.assertEqual((self.workspace / state['rounds'][0]['packet_path']).read_bytes(), first_packet)

    def test_exhausted_budget_requires_explicit_grant_and_keeps_history(self):
        settings = json.loads((self.workspace / 'workspace.json').read_text())
        settings['document_quality']['max_rewrites'] = 0
        test_cli.write_json(self.workspace / 'workspace.json', settings)
        self.start()
        self.report('content', 60)
        self.report('visual', 60)
        self.assertEqual(json.loads(self.command().stdout)['decision'], 'exhausted')
        self.revise('Explicit extra revision')
        self.command('--prepare', '--writer-id', 'fixture-primary', '--new-version', '--reason', 'User requests revision', expect=2)
        self.start('--new-version', '--reason', 'User authorizes one additional draft', '--grant-rounds', '1')
        state = json.loads((self.directory / 'quality-loop.json').read_text())
        self.assertEqual(state['round_limit'], 2)
        self.assertEqual(len(state['rounds']), 2)
        self.assertEqual(state['rounds'][0]['decision'], 'exhausted')
        self.assertEqual(state['events'][-1]['type'], 'budget_grant')

    def test_handoff_records_actual_identity_and_prevents_old_writer_review(self):
        self.start()
        self.command('--handoff', '--writer-id', 'fixture-next-primary', '--reason', 'Resume in another session')
        state = json.loads((self.directory / 'quality-loop.json').read_text())
        self.assertEqual(state['writer_id'], 'fixture-next-primary')
        self.assertEqual(set(state['producer_ids']), {'fixture-primary', 'fixture-next-primary'})
        self.assertEqual(len(state['rounds']), 1)
        self.report('content', reviewer_id='fixture-primary')
        self.report('visual')
        self.command(expect=2)
        self.report('content')
        self.assertEqual(json.loads(self.command().stdout)['decision'], 'passed')
        self.revise('Continued in actual next session')
        self.command('--prepare', '--writer-id', 'fixture-primary', '--new-version', '--reason', 'Revision', expect=2)
        self.command('--prepare', '--writer-id', 'fixture-next-primary', '--new-version', '--reason', 'Requested revision')

    def test_corrupted_content_addressed_object_is_never_reused(self):
        self.start()
        item = next(item for item in self.packet['files'] if item['original_path'] == 'profile.json')
        blob = self.workspace / item['snapshot_path']
        blob.chmod(0o600)
        blob.write_bytes(b'corrupt')
        self.revise('Revision after corrupt blob')
        self.command('--prepare', '--writer-id', 'fixture-primary', '--new-version', '--reason', 'Revision', expect=2)

    def test_blocked_round_can_resume_as_a_corrected_version(self):
        self.start()
        self.report('content')
        self.report('visual', unavailable=True)
        self.assertEqual(json.loads(self.command().stdout)['decision'], 'blocked')
        self.revise('Corrected after unavailable review')
        self.start('--new-version', '--reason', 'User requests correction while review unavailable')
        state = json.loads((self.directory / 'quality-loop.json').read_text())
        self.assertEqual(state['rounds'][0]['decision'], 'blocked')
        self.assertEqual(len(state['rounds']), 2)

    def test_legacy_state_can_handoff_without_resetting_rounds(self):
        self.start()
        path = self.directory / 'quality-loop.json'
        state = json.loads(path.read_text())
        state['schema_version'] = 1
        for key in ('document_id', 'producer_ids', 'round_limit', 'events', 'versions'):
            state.pop(key)
        test_cli.write_json(path, state)
        self.command('--handoff', '--writer-id', 'fixture-next-primary', '--reason', 'Continue legacy loop')
        upgraded = json.loads(path.read_text())
        self.assertEqual(upgraded['schema_version'], 2)
        self.assertEqual(len(upgraded['rounds']), 1)
        self.assertEqual(upgraded['round_limit'], 3)
        self.assertEqual(set(upgraded['producer_ids']), {'fixture-primary', 'fixture-next-primary'})

    def test_profile_correction_refreshes_bindings_and_preserves_old_profile(self):
        self.start()
        first = self.packet
        self.report('content')
        self.report('visual')
        self.command()
        old_profile = (self.workspace / 'profile.json').read_bytes()
        profile = json.loads(old_profile)
        profile['identity']['phone'] = '555-0199'
        test_cli.write_json(self.workspace / 'profile.json', profile)
        plan = json.loads((self.directory / 'resume.json').read_text())
        test_cli.run_cli('prepare-resume', '--workspace', str(self.workspace), '--job', 'example-job', '--force')
        seed = json.loads((self.directory / 'resume.json').read_text())
        plan['profile_sha256'] = seed['profile_sha256']
        test_cli.write_json(self.directory / 'resume.json', plan)
        self.render_fixture('corrected-contact')
        self.start('--new-version', '--reason', 'User corrects contact phone')
        old_blob = next(item['snapshot_path'] for item in first['files'] if item['original_path'] == 'profile.json')
        self.assertEqual((self.workspace / old_blob).read_bytes(), old_profile)
        self.command('--verify', expect=2)

    def check_json_formatting_gate(self, legacy=False):
        self.start()
        if legacy:
            # Simulate packets written before normalized identities existed.
            packet = json.loads(self.packet_path.read_text())
            packet.pop('effective_input_version')
            packet.pop('effective_input_hashes')
            test_cli.write_json(self.packet_path, packet)
            state_path = self.directory / 'quality-loop.json'
            state = json.loads(state_path.read_text())
            state['rounds'][-1]['packet_sha256'] = hashlib.sha256(self.packet_path.read_bytes()).hexdigest()
            test_cli.write_json(state_path, state)
            self.packet = packet
        self.report('content', 60)
        self.report('visual', 60)
        self.command()
        state_path = self.directory / 'quality-loop.json'
        before_state = state_path.read_bytes()
        before_rounds = sorted(path.name for path in state_path.parent.joinpath('quality-rounds').iterdir())
        before_artifacts = {name: (self.directory / name).read_bytes() for name in
                            ('resume.tex', 'resume.pdf', 'resume.txt', 'audit-pages/page-1.png')}
        path = self.directory / 'resume.json'
        plan = json.loads(path.read_text())
        notes = self.directory / 'formatting-notes.json'
        test_cli.write_json(notes, {'previous_round_id': self.packet['round_id'], 'changes': [
            {'finding_locator': 'resume.json', 'action': 'format JSON', 'explanation': 'Serialization only.'}]})
        for options in ({'separators': (',', ':')}, {'indent': 4}):
            path.write_text(json.dumps(dict(reversed(list(plan.items()))), **options) + '\n')
            self.render_fixture('initial')
            self.assertEqual(json.loads(path.read_text()), plan)
            self.assertEqual({name: (self.directory / name).read_bytes() for name in before_artifacts}, before_artifacts)
            for args in (('--new-version', '--reason', 'JSON formatting only'), ('--revision-notes', str(notes))):
                with self.subTest(options=options, route=args[0]):
                    self.command('--prepare', '--writer-id', 'fixture-primary', *args, expect=2)
                    self.assertEqual(state_path.read_bytes(), before_state)
                    self.assertEqual(sorted(p.name for p in state_path.parent.joinpath('quality-rounds').iterdir()), before_rounds)

    def test_json_formatting_cannot_obtain_a_new_panel(self):
        self.check_json_formatting_gate()

    def test_legacy_packet_rejects_json_formatting_without_replacing_history(self):
        self.check_json_formatting_gate(legacy=True)

    def test_source_json_formatting_and_refreshed_plan_bindings_do_not_grant_a_round(self):
        self.start()
        before = (self.directory / 'quality-loop.json').read_bytes()
        path = self.workspace / 'profile.json'
        path.write_text(json.dumps(json.loads(path.read_text()), separators=(',', ':')))
        plan_path = self.directory / 'resume.json'
        plan = json.loads(plan_path.read_text())
        plan['profile_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        test_cli.write_json(plan_path, plan)
        prefs = self.workspace / 'preferences.json'
        prefs.write_text(json.dumps(json.loads(prefs.read_text()), separators=(',', ':')))
        self.render_fixture('initial')
        self.command('--prepare', '--writer-id', 'fixture-primary', '--new-version', '--reason', 'Reformat input JSON', expect=2)
        self.assertEqual((self.directory / 'quality-loop.json').read_bytes(), before)

    def test_source_change_without_wording_change_still_allows_review(self):
        self.start()
        path = self.workspace / 'preferences.json'
        value = json.loads(path.read_text())
        value['locations'] = ['Portland, OR']
        test_cli.write_json(path, value)
        self.render_fixture('initial')
        self.start('--new-version', '--reason', 'User changes preferred city')
        self.assertEqual(self.packet['round_index'], 1)

    def test_section_order_change_still_allows_new_version(self):
        self.start()
        path = self.directory / 'resume.json'
        value = json.loads(path.read_text())
        value['section_order'].reverse()
        test_cli.write_json(path, value)
        self.render_fixture('new-layout')
        self.start('--new-version', '--reason', 'User changes section order')
        self.assertEqual(self.packet['round_index'], 1)

    def test_normalized_change_gate_does_not_relax_exact_approval_bindings(self):
        self.start()
        self.report('content')
        self.report('visual')
        self.command()
        path = self.directory / 'resume.json'
        path.write_text(json.dumps(json.loads(path.read_text()), separators=(',', ':')))
        self.command('--verify', expect=2)
        test_cli.run_cli('finalize-audit', '--workspace', str(self.workspace), '--job', 'example-job', expect=2)


if __name__ == "__main__":
    unittest.main()
