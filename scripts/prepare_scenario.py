#!/usr/bin/env python3
"""Prepare fictional, offline agent-evaluation materials in a new external workspace."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from jobbot_skill import ROOT, UserError, cmd_init, now_iso, sha256_file, workspace_path, write_json
from workspace_fs import mkdir as make_dirs, write_text as save_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, help='New empty external evaluation directory')
    parser.add_argument('--case', required=True, choices=('experienced', 'student', 'returning', 'correction'))
    args = parser.parse_args()
    try:
        workspace = workspace_path(args.workspace)
        if workspace.exists() and any(workspace.iterdir()):
            raise UserError('Evaluation preparation requires a new empty directory; existing workspaces are never reset')
        case = json.loads((ROOT / 'evals' / 'cases' / f'{args.case}.json').read_text())
        cmd_init(argparse.Namespace(workspace=str(workspace), country=case['country']))
        inbox = workspace / 'inbox'
        make_dirs(inbox, exist_ok=False)
        for name, text in case['materials'].items():
            save_text(inbox / name, text + '\n')
        if case.get('seed'):
            profile = json.loads((workspace / 'profile.json').read_text())
            profile.update({
                'identity': {'name': 'Morgan Example', 'email': 'morgan@example.invalid', 'phone': '', 'location': 'Seattle, WA', 'residence_country': 'US', 'links': []},
                'summary_facts': [{'id': 'fact.api', 'text': 'Built Python APIs and integration tests.', 'source_ids': ['user-confirmed']}],
                'experience': [{'id': 'work.northstar', 'employer': 'Northstar Example', 'title': 'Software Engineer', 'location': 'Seattle', 'start': '2021', 'end': '2024', 'source_ids': ['user-confirmed'],
                    'bullets': [{'id': 'work.api', 'text': 'Built Python APIs and integration tests.', 'source_ids': ['user-confirmed']},
                                {'id': 'work.automation', 'text': 'Automated reporting, saving 30% of time.', 'source_ids': ['user-confirmed']}]}],
                'education': [{'id': 'edu.example', 'institution': 'Example University', 'credential': 'B.S. Computer Science', 'location': '', 'start': '2017', 'end': '2021', 'source_ids': ['user-confirmed']}],
                'skills': [{'id': 'skill.python', 'name': 'Python', 'category': 'Languages', 'source_ids': ['user-confirmed']}]})
            write_json(workspace / 'profile.json', profile)
            market = json.loads((workspace / 'market.json').read_text())
            market['confirmed'] = True
            write_json(workspace / 'market.json', market)
            preferences = json.loads((workspace / 'preferences.json').read_text())
            preferences['employment_countries'] = {'mode': 'only', 'countries': ['US']}
            preferences['locations'] = ['Seattle']
            write_json(workspace / 'preferences.json', preferences)
            onboarding = json.loads((workspace / 'onboarding.json').read_text())
            for section in onboarding['sections'].values():
                section.update({'status': 'confirmed', 'summary': 'Synthetic persona confirmed this section in a prior session.', 'confirmed_at': now_iso()})
            write_json(workspace / 'onboarding.json', onboarding)
            write_json(workspace / 'intake.json', {'schema_version': 1, 'last_reviewed_at': (datetime.now(timezone.utc) - timedelta(days=100)).isoformat(),
                       'summary': 'Synthetic prior check-in.', 'profile_sha256': sha256_file(workspace / 'profile.json'), 'preferences_sha256': sha256_file(workspace / 'preferences.json')})
        save_text(workspace / 'request.md', case['request'] + '\n\nMaterials: ' + str(inbox) + '\nWorkspace: ' + str(workspace) + '\n')
        write_json(workspace / 'evaluation.json', {'schema_version': 1, 'synthetic': True, 'case': args.case, 'prepared_at': now_iso(),
                   'case_sha256': sha256_file(ROOT / 'evals' / 'cases' / f'{args.case}.json'), 'status': 'prepared', 'agent_execution': None})
        print(f'Prepared synthetic case {args.case}: {workspace / "request.md"}. No agent execution or review is implied.')
        return 0
    except (UserError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
