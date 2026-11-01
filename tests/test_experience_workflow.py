from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest

import test_cli


class ExperienceWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_cli.JobBotSkillCliTest(methodName='runTest')
        self.fixture.setUp()
        self.fixture.populate_profile()
        self.workspace = self.fixture.workspace

    def tearDown(self):
        self.fixture.tearDown()

    def profile(self, employed=False):
        path = self.workspace / 'profile.json'
        profile = json.loads(path.read_text())
        profile['schema_version'] = 3
        if not employed:
            profile['experience'] = []
        for group in ('projects', 'research', 'coursework', 'activities'):
            profile[group] = []
        profile['projects'] = [{'id': 'project.sensor', 'name': 'Sensor monitor', 'organization': 'Independent project',
            'start': '2025', 'end': '2026', 'source_ids': ['user-confirmed'], 'related_ids': ['course.embedded'],
            'bullets': [{'id': 'project.sensor.test', 'text': 'Built and tested a sensor monitor.', 'source_ids': ['user-confirmed']}]}]
        profile['coursework'] = [{'id': 'course.embedded', 'name': 'Embedded Systems', 'start': '2025', 'end': '2025',
            'source_ids': ['user-confirmed'], 'related_ids': ['project.sensor'],
            'bullets': [{'id': 'course.embedded.lab', 'text': 'Debugged timing behavior in lab assignments.', 'source_ids': ['user-confirmed']}]}]
        test_cli.write_json(path, profile)
        return profile

    def plan(self):
        directory = self.fixture.import_job()
        self.fixture.confirm_onboarding()
        self.prepare(directory)
        return directory

    def prepare(self, directory, force=False):
        test_cli.run_cli('prepare-resume', '--workspace', str(self.workspace), '--job', 'example-job', *(['--force'] if force else []))
        path = directory / 'resume.json'
        value = json.loads(path.read_text())
        value['summary'] = [{'text': 'Maintained backend services.', 'evidence_ids': ['fact.backend']}]
        for group in ('projects', 'coursework'):
            if value[group]:
                identifier = 'project.sensor.test' if group == 'projects' else 'course.embedded.lab'
                text = 'Built and tested a sensor monitor.' if group == 'projects' else 'Debugged timing behavior in lab assignments.'
                value[group][0]['bullets'] = [{'text': text, 'evidence_ids': [identifier]}]
        test_cli.write_json(path, value)
        return value

    def rule(self, *args):
        return test_cli.run_cli('set-writing-rule', '--workspace', str(self.workspace), '--confirmation', 'Synthetic user explicitly requested this rule.', *args)

    def test_first_class_nonemployment_entries_link_without_fake_employers(self):
        profile = self.profile()
        test_cli.run_cli('validate-profile', '--workspace', str(self.workspace))
        directory = self.plan()
        test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job')
        test_cli.run_cli('render-latex', '--workspace', str(self.workspace), '--job', 'example-job')
        tex = (directory / 'resume.tex').read_text()
        self.assertIn('Sensor monitor', tex)
        self.assertIn('Embedded Systems', tex)
        self.assertNotIn('Example Co', tex)
        self.assertNotIn('Professional Experience}', tex)
        self.assertNotIn('employer', profile['projects'][0])

    def test_legacy_upgrade_preserves_original_and_leaves_facts_intact(self):
        path = self.workspace / 'profile.json'
        before = path.read_bytes()
        test_cli.run_cli('upgrade-profile', '--workspace', str(self.workspace))
        value = json.loads(path.read_text())
        self.assertEqual(value['schema_version'], 3)
        self.assertEqual(value['experience'], json.loads(before)['experience'])
        history = list((self.workspace / 'history' / 'profile.json').glob('*.json'))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].read_bytes(), before)
        after = path.read_bytes()
        test_cli.run_cli('upgrade-profile', '--workspace', str(self.workspace))
        self.assertEqual(path.read_bytes(), after)

    def test_unknown_relationship_or_unconfirmed_project_source_is_rejected(self):
        value = self.profile()
        value['projects'][0]['related_ids'] = ['invented']
        test_cli.write_json(self.workspace / 'profile.json', value)
        result = test_cli.run_cli('validate-profile', '--workspace', str(self.workspace), expect=2)
        self.assertIn('related_id', result.stderr)
        value['projects'][0]['related_ids'] = []
        value['projects'][0]['source_ids'] = ['invented']
        test_cli.write_json(self.workspace / 'profile.json', value)
        test_cli.run_cli('validate-profile', '--workspace', str(self.workspace), expect=2)

    def test_project_cannot_borrow_an_unrelated_fact_as_its_only_evidence(self):
        self.profile()
        directory = self.plan()
        value = json.loads((directory / 'resume.json').read_text())
        value['projects'][0]['bullets'][0]['evidence_ids'] = ['fact.backend']
        test_cli.write_json(directory / 'resume.json', value)
        test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job', expect=2)

    def test_employment_requires_evidence_from_that_employer(self):
        self.profile(employed=True)
        directory = self.plan()
        value = json.loads((directory / 'resume.json').read_text())
        value['experience'][0]['bullets'] = [{'text': 'Built an API.', 'evidence_ids': ['project.sensor.test']}]
        test_cli.write_json(directory / 'resume.json', value)
        result = test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job', expect=2)
        self.assertIn('that employer', result.stderr)
        value['experience'][0]['bullets'][0]['evidence_ids'] = ['exp.example.api', 'skill.python']
        test_cli.write_json(directory / 'resume.json', value)
        test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job')

    def test_rules_exclude_entries_and_child_facts_but_preserve_the_archive(self):
        self.profile()
        before = (self.workspace / 'profile.json').read_bytes()
        self.rule('--id', 'private', '--instruction', 'Do not put the sensor project on resumes.', '--exclude', 'project.sensor')
        directory = self.plan()
        value = json.loads((directory / 'resume.json').read_text())
        self.assertEqual(value['projects'], [])
        value['summary'] = [{'text': 'Built a sensor monitor.', 'evidence_ids': ['project.sensor.test']}]
        test_cli.write_json(directory / 'resume.json', value)
        result = test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job', expect=2)
        self.assertIn('excluded', result.stderr)
        self.assertEqual((self.workspace / 'profile.json').read_bytes(), before)

    def test_writing_rule_changes_stale_plans_and_retirement_preserves_history(self):
        self.profile(employed=True)
        directory = self.plan()
        old = (directory / 'resume.json').read_bytes()
        self.rule('--id', 'voice', '--instruction', 'Avoid claiming AI experience.', '--forbid', 'AI')
        result = test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job', expect=2)
        self.assertIn('Writing rules changed', result.stderr)
        self.assertEqual((directory / 'resume.json').read_bytes(), old)
        self.prepare(directory, force=True)
        # A word-level ban must not accidentally reject 'Maintained'.
        test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job')
        value = json.loads((directory / 'resume.json').read_text())
        value['summary'][0]['text'] = 'AI engineer.'
        test_cli.write_json(directory / 'resume.json', value)
        test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job', expect=2)
        self.rule('--id', 'voice', '--retire')
        self.assertTrue(list((self.workspace / 'history' / 'writing-rules.json').glob('*.json')))
        rules = json.loads(test_cli.run_cli('writing-rules', '--workspace', str(self.workspace)).stdout)
        self.assertEqual(rules['rules'], [])

    def test_scoped_rules_apply_only_to_the_requested_market_or_job(self):
        self.profile()
        self.rule('--id', 'other-market', '--instruction', 'Exclude this project for GB.', '--scope', 'market', '--target', 'GB', '--exclude', 'project.sensor')
        self.rule('--id', 'other-job', '--instruction', 'Exclude this course only for another job.', '--scope', 'job', '--target', 'other', '--exclude', 'course.embedded')
        directory = self.plan()
        value = json.loads((directory / 'resume.json').read_text())
        self.assertTrue(value['projects'])
        self.assertTrue(value['coursework'])
        test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job')

    def test_all_experience_groups_render_for_a_working_candidate(self):
        value = self.profile(employed=True)
        for group in ('research', 'activities'):
            value[group] = [{'id': group + '.entry', 'name': group + ' work', 'start': '', 'end': '',
                'source_ids': ['user-confirmed'], 'bullets': [{'id': group + '.fact', 'text': 'Delivered a documented contribution.', 'source_ids': ['user-confirmed']}]}]
        test_cli.write_json(self.workspace / 'profile.json', value)
        directory = self.plan()
        plan = json.loads((directory / 'resume.json').read_text())
        for group in ('research', 'activities'):
            plan[group][0]['bullets'] = [{'text': 'Delivered a documented contribution.', 'evidence_ids': [group + '.fact']}]
        plan['experience'][0]['bullets'] = [{'text': 'Built an API.', 'evidence_ids': ['exp.example.api']}]
        test_cli.write_json(directory / 'resume.json', plan)
        test_cli.run_cli('render-latex', '--workspace', str(self.workspace), '--job', 'example-job')
        tex = (directory / 'resume.tex').read_text()
        for term in ('Example Co', 'Sensor monitor', 'research work', 'activities work'):
            self.assertIn(term, tex)

    def test_original_template_builds_and_retains_text_in_english_and_chinese(self):
        if not all(shutil.which(tool) for tool in ('pdflatex', 'xelatex', 'pdftotext')):
            self.skipTest('TeX/Poppler tools unavailable')
        value = self.profile()
        directory = self.plan()
        for language, name in (('en', 'Example Candidate'), ('en', '李示例'), ('zh', '示例求职者')):
            with self.subTest(language=language):
                value['identity']['name'] = name
                test_cli.write_json(self.workspace / 'profile.json', value)
                market = json.loads((self.workspace / 'market.json').read_text())
                market['language'] = language
                test_cli.write_json(self.workspace / 'market.json', market)
                self.prepare(directory, force=True)
                test_cli.run_cli('render-latex', '--workspace', str(self.workspace), '--job', 'example-job')
                test_cli.run_cli('render-pdf', '--workspace', str(self.workspace), '--job', 'example-job')
                result = subprocess.run(['pdftotext', str(directory / 'resume.pdf'), '-'], capture_output=True, text=True, check=True)
                normalized = ''.join(result.stdout.split())
                self.assertIn(''.join(name.split()), normalized)
                self.assertIn('Sensormonitor', normalized)
                self.assertIn('candidate@example.com', normalized)
        self.assertTrue(list((directory / 'history' / 'resume.pdf').glob('*.pdf')))
        self.assertTrue(list((directory / 'command-logs').glob('*.json')))

    def test_modified_tex_requires_rerender_before_compilation(self):
        self.profile()
        directory = self.plan()
        test_cli.run_cli('render-latex', '--workspace', str(self.workspace), '--job', 'example-job')
        with (directory / 'resume.tex').open('a') as stream:
            stream.write('\n% unexpected change\n')
        result = test_cli.run_cli('render-pdf', '--workspace', str(self.workspace), '--job', 'example-job', expect=2)
        self.assertIn('Rendered inputs changed', result.stderr)

    def test_forbidden_phrases_cover_location_contact_categories_and_section_labels(self):
        self.profile()
        self.rule('--id', 'confidential', '--instruction', 'Do not publish SecretTown.', '--forbid', 'SecretTown')
        directory = self.plan()
        profile_path = self.workspace / 'profile.json'
        original = json.loads(profile_path.read_text())
        market_path = self.workspace / 'market.json'
        original_market = json.loads(market_path.read_text())
        for field in ('project_location', 'email', 'category', 'section_label'):
            with self.subTest(field=field):
                value = json.loads(json.dumps(original))
                market = json.loads(json.dumps(original_market))
                if field == 'project_location':
                    value['projects'][0]['location'] = 'SecretTown'
                elif field == 'email':
                    value['identity']['email'] = 'SecretTown@example.invalid'
                elif field == 'category':
                    value['skills'][0]['category'] = 'SecretTown'
                else:
                    market['section_labels'] = {'projects': 'SecretTown'}
                test_cli.write_json(profile_path, value)
                test_cli.write_json(market_path, market)
                plan = self.prepare(directory, force=True)
                plan['profile_skill_ids'] = ['skill.python']
                test_cli.write_json(directory / 'resume.json', plan)
                result = test_cli.run_cli('validate-resume', '--workspace', str(self.workspace), '--job', 'example-job', expect=2)
                self.assertIn('forbidden', result.stderr)
