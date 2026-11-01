#!/usr/bin/env python3
"""Inventory a supplied folder by content hash and optionally import new evidence."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from jobbot_skill import (
    ROOT, UserError, append_evidence_source, evidence_snapshot, load_evidence_sources,
    now_iso, read_json, retain_file, sha256_bytes, validate_source_review,
    workspace_path, write_json,
)
from workspace_fs import MANAGED_DIRECTORIES, mkdir as make_dirs, write_bytes as save_bytes

MAX_FILE_BYTES = 20_000_000


def local(workspace, path):
    if not path.resolve().is_relative_to(workspace):
        raise UserError("Intake outputs must remain inside the workspace")
    return path


def reading_status(workspace, source):
    digest, _ = evidence_snapshot(workspace, source)
    notes = local(workspace, workspace / 'evidence' / 'reviews' / f"{source['id']}.json")
    if not notes.exists():
        return 'pending_read'
    value = read_json(notes)
    validate_source_review(value, source['id'], digest)
    return 'reviewed' if value['status'] == 'reviewed' else 'pending_read'


def scan(workspace, folder, import_files=False, source_type='other'):
    if not folder.is_dir():
        raise UserError('The supplied intake folder does not exist')
    if folder == workspace or folder == ROOT or ROOT in folder.parents:
        raise UserError('Choose a materials subfolder, not the workspace or skill source root')
    if folder.is_relative_to(workspace) and folder.relative_to(workspace).parts[0] in MANAGED_DIRECTORIES:
        raise UserError('Do not scan managed workspace outputs; choose a dedicated materials/inbox folder')
    sources = load_evidence_sources(workspace)
    index_path = local(workspace, workspace / 'evidence' / 'intake.json')
    index = read_json(index_path) if index_path.exists() else {'schema_version': 1, 'folders': {}}
    if index.get('schema_version') != 1 or not isinstance(index.get('folders'), dict):
        raise UserError('Invalid intake index')
    folder_id = sha256_bytes(str(folder).encode())[:20]
    old_folder = index['folders'].get(folder_id, {})
    if not isinstance(old_folder, dict) or not isinstance(old_folder.get('files', {}), dict):
        raise UserError('Invalid saved folder record')
    previous = old_folder.get('files', {})
    if any(not isinstance(row, dict) or not isinstance(row.get('history', []), list) for row in previous.values()):
        raise UserError('Invalid saved intake file record')
    files, diagnostics = {}, []
    by_hash = {s.get('sha256'): s for s in sources.values() if s['type'] not in {'github', 'user_statement'}}
    def walk_error(error):
        diagnostics.append({'path': str(error.filename), 'status': 'error', 'error': str(error)})
    for directory, dirs, names in os.walk(folder, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        keep = []
        for name in sorted(dirs):
            path = parent / name
            if path.is_symlink() or name in {'.git', '.history', '__pycache__'} or path.resolve() in {workspace, ROOT}:
                diagnostics.append({'path': str(path.relative_to(folder)), 'status': 'skipped_directory'})
            else:
                keep.append(name)
        dirs[:] = keep
        for name in sorted(names):
            path = parent / name
            relative = str(path.relative_to(folder))
            old = previous.get(relative, {})
            history = list(old.get('history', []))
            row = {'path': relative, 'status': 'error', 'source_id': None, 'history': history}
            try:
                if path.is_symlink() or not path.resolve().is_relative_to(folder):
                    row['status'] = 'skipped_symlink'
                elif not path.is_file():
                    row['status'] = 'skipped_special_file'
                elif path.stat().st_size > MAX_FILE_BYTES:
                    row['status'] = 'oversize'
                else:
                    data = path.read_bytes()
                    if len(data) > MAX_FILE_BYTES or path.is_symlink() or not path.resolve().is_relative_to(folder):
                        raise UserError('File changed or exceeded the limit during capture')
                    digest = sha256_bytes(data)
                    row.update({'sha256': digest, 'bytes': len(data),
                                'status': 'new' if not old.get('sha256') else 'unchanged' if digest == old['sha256'] else 'changed',
                                'processing': 'not_imported'})
                    if old.get('sha256') and old['sha256'] != digest:
                        history.append({k: old[k] for k in ('sha256', 'source_id', 'observed_at') if k in old})
                    source = by_hash.get(digest)
                    if source:
                        row.update({'source_id': source['id'], 'processing': reading_status(workspace, source)})
                    elif import_files:
                        identifier = 'intake.' + digest[:24]
                        if identifier in sources:
                            raise UserError('Intake source ID collision; preserve existing source and resolve explicitly')
                        suffix = path.suffix.lower()[:16]
                        destination = local(workspace, workspace / 'evidence' / 'files' / f'{identifier}{suffix}')
                        if destination.exists():
                            raise UserError('Existing evidence destination is not indexed; resolve before import')
                        make_dirs(destination.parent)
                        save_bytes(destination, data)
                        source = {'id': identifier, 'type': source_type, 'label': name,
                                  'locator': str(destination.relative_to(workspace)), 'imported_at': now_iso(),
                                  'sha256': digest, 'ownership_confirmed': False}
                        append_evidence_source(workspace, source)
                        sources[identifier] = source
                        by_hash[digest] = source
                        notes = local(workspace, workspace / 'evidence' / 'reviews' / f'{identifier}.json')
                        if not notes.exists():
                            write_json(notes, {'schema_version': 1, 'source_id': identifier, 'source_sha256': digest,
                                               'prepared_at': now_iso(), 'status': 'pending', 'summary': '',
                                               'observations': [], 'candidate_facts': [], 'questions': []})
                        row.update({'source_id': identifier, 'processing': 'pending_read'})
                    row['observed_at'] = now_iso()
            except (OSError, UserError) as exc:
                row.update({'status': 'error', 'error': str(exc)})
            files[relative] = row
    for relative, old in previous.items():
        if relative not in files:
            unavailable = any(d['status'] == 'error' and (folder / relative).is_relative_to(Path(d['path'])) for d in diagnostics)
            files[relative] = {**old, 'status': 'unavailable' if unavailable else 'missing'}
    report = {'schema_version': 1, 'scan_id': uuid.uuid4().hex, 'scanned_at': now_iso(),
              'folder_id': folder_id, 'folder': str(folder), 'import_requested': import_files,
              'files': files, 'diagnostics': diagnostics}
    report_path = local(workspace, workspace / 'evidence' / 'intake-scans' / f"{report['scan_id']}.json")
    write_json(report_path, report)
    index['folders'][folder_id] = {'folder': str(folder), 'last_scan': str(report_path.relative_to(workspace)), 'files': files}
    retain_file(index_path)
    write_json(index_path, index)
    return {**report, 'report_path': str(report_path.relative_to(workspace))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--folder', required=True)
    parser.add_argument('--import', dest='import_files', action='store_true', help='Copy new content and prepare pending reading notes; never confirms facts')
    parser.add_argument('--type', default='other', choices=('resume', 'portfolio', 'certificate', 'transcript', 'other'))
    args = parser.parse_args()
    try:
        result = scan(workspace_path(args.workspace), Path(args.folder).expanduser().resolve(), args.import_files, args.type)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if any(r['status'] == 'error' for r in result['files'].values()) or any(d['status'] == 'error' for d in result['diagnostics']) else 0
    except (UserError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
