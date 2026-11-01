from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import test_cli


class IntakeFolderTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_cli.JobBotSkillCliTest(methodName='runTest')
        self.fixture.setUp()
        self.workspace = self.fixture.workspace
        self.folder = Path(self.fixture.temp.name) / 'materials'
        self.folder.mkdir()

    def tearDown(self):
        self.fixture.tearDown()

    def scan(self, *args, expect=0):
        result = subprocess.run([sys.executable, str(test_cli.ROOT / 'scripts' / 'intake_folder.py'),
            '--workspace', str(self.workspace), '--folder', str(self.folder), *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else result

    def test_hash_scan_imports_only_new_bytes_and_never_confirms_facts(self):
        path = self.folder / 'resume.md'
        path.write_text('Built a backend service.')
        (self.folder / 'duplicate.txt').write_bytes(path.read_bytes())
        before = (self.workspace / 'profile.json').read_bytes()
        first = self.scan('--import')
        ids = {row['source_id'] for row in first['files'].values()}
        self.assertEqual(len(ids), 1)
        identifier = ids.pop()
        manifest = json.loads((self.workspace / 'evidence' / 'manifest.json').read_text())
        imported = next(s for s in manifest['sources'] if s['id'] == identifier)
        self.assertFalse(imported['ownership_confirmed'])
        self.assertEqual((self.workspace / 'profile.json').read_bytes(), before)
        notes_path = self.workspace / 'evidence' / 'reviews' / f'{identifier}.json'
        notes = json.loads(notes_path.read_text())
        self.assertEqual(notes['status'], 'pending')
        notes.update({'status': 'reviewed', 'summary': 'Read the supplied document.'})
        test_cli.write_json(notes_path, notes)
        second = self.scan('--import')
        self.assertTrue(all(row['status'] == 'unchanged' and row['processing'] == 'reviewed' for row in second['files'].values()))
        self.assertEqual(len(list((self.workspace / 'evidence' / 'files').iterdir())), 1)
        self.assertEqual(len(list((self.workspace / 'evidence' / 'intake-scans').glob('*.json'))), 2)

    def test_same_size_same_mtime_change_gets_new_snapshot_and_missing_keeps_history(self):
        path = self.folder / 'notes.md'
        path.write_text('version one')
        first = self.scan('--import')['files']['notes.md']
        stamp = path.stat()
        path.write_text('version two')
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        changed = self.scan('--import')['files']['notes.md']
        self.assertEqual(changed['status'], 'changed')
        self.assertNotEqual(changed['source_id'], first['source_id'])
        self.assertEqual(changed['history'][0]['source_id'], first['source_id'])
        path.unlink()
        missing = self.scan('--import')['files']['notes.md']
        self.assertEqual(missing['status'], 'missing')
        self.assertEqual(missing['source_id'], changed['source_id'])
        self.assertEqual(len(list((self.workspace / 'evidence' / 'files').iterdir())), 2)

    def test_scan_without_import_keeps_unprocessed_files_actionable(self):
        (self.folder / 'scan.png').write_bytes(b'synthetic image bytes, not a decoded image')
        first = self.scan()['files']['scan.png']
        second = self.scan()['files']['scan.png']
        self.assertEqual(first['status'], 'new')
        self.assertEqual(second['status'], 'unchanged')
        self.assertEqual(second['processing'], 'not_imported')
        self.assertIsNone(second['source_id'])
        imported = self.scan('--import')['files']['scan.png']
        self.assertEqual(imported['processing'], 'pending_read')
        self.assertTrue(imported['source_id'])

    def test_symlinks_are_not_followed_and_output_cannot_escape(self):
        outside = Path(self.fixture.temp.name) / 'private.txt'
        outside.write_text('Unrelated private material')
        (self.folder / 'linked.txt').symlink_to(outside)
        result = self.scan('--import')
        self.assertEqual(result['files']['linked.txt']['status'], 'skipped_symlink')
        self.assertEqual(len(list((self.workspace / 'evidence' / 'files').iterdir())), 0)
        destination = Path(self.fixture.temp.name) / 'elsewhere'
        destination.mkdir()
        (self.workspace / 'evidence' / 'intake-scans').rename(self.workspace / 'evidence' / 'previous-scans')
        (self.workspace / 'evidence' / 'intake-scans').symlink_to(destination, target_is_directory=True)
        self.scan('--import', expect=2)
        self.assertFalse(list(destination.iterdir()))

    def test_corrupted_import_is_reported_and_does_not_silently_reuse_it(self):
        (self.folder / 'notes.txt').write_text('Candidate notes.')
        first = self.scan('--import')
        source_id = first['files']['notes.txt']['source_id']
        manifest = json.loads((self.workspace / 'evidence' / 'manifest.json').read_text())
        source = next(s for s in manifest['sources'] if s['id'] == source_id)
        (self.workspace / source['locator']).write_text('Unexpected modification')
        result = self.scan('--import', expect=2)
        self.assertEqual(result['files']['notes.txt']['status'], 'error')
        self.assertIn('changed', result['files']['notes.txt']['error'])

    def test_managed_workspace_outputs_cannot_become_an_intake_source(self):
        self.folder = self.workspace / 'evidence'
        before = (self.workspace / 'evidence' / 'manifest.json').read_bytes()
        self.scan('--import', expect=2)
        self.assertEqual((self.workspace / 'evidence' / 'manifest.json').read_bytes(), before)
        self.assertFalse((self.workspace / 'evidence' / 'intake.json').exists())

    def test_cas_root_and_nested_directories_cannot_be_imported(self):
        root = self.workspace / 'objects'
        blob = root / 'sha256' / 'ab' / ('ab' * 32)
        blob.parent.mkdir(parents=True)
        blob.write_bytes(b'Internal generated resume snapshot; never an intake source.')
        blob.chmod(0o400)
        alias = Path(self.fixture.temp.name) / 'objects-alias'
        alias.symlink_to(blob.parent, target_is_directory=True)
        before = {str(path.relative_to(self.workspace)): path.read_bytes()
                  for path in self.workspace.rglob('*') if path.is_file()}
        for folder in (root, root / 'sha256', blob.parent, alias):
            with self.subTest(folder=folder):
                self.folder = folder
                result = self.scan('--import', expect=2)
                self.assertIn('managed workspace outputs', result.stderr)
                after = {str(path.relative_to(self.workspace)): path.read_bytes()
                         for path in self.workspace.rglob('*') if path.is_file()}
                self.assertEqual(after, before)

    def test_materials_folder_named_objects_is_allowed_outside_managed_root(self):
        self.folder = self.workspace / 'inbox' / 'objects'
        self.folder.mkdir(parents=True)
        (self.folder / 'project.txt').write_text('User-supplied project description.')
        result = self.scan('--import')
        self.assertEqual(result['files']['project.txt']['processing'], 'pending_read')
