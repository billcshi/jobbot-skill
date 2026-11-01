"""HTTP and workspace-boundary regressions; all network traffic is mocked."""
from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import sys
import unittest
from email.message import Message
from unittest.mock import MagicMock, patch

import test_cli

sys.path.insert(0, str(test_cli.ROOT / 'scripts'))
import public_http
import workspace_fs


class PublicHttpTest(unittest.TestCase):
    def test_connection_pins_numeric_address_and_preserves_tls_hostname(self):
        raw = MagicMock()
        raw.getpeername.return_value = ('93.184.216.34', 443)
        context = MagicMock()
        connection = public_http.PinnedHTTPSConnection('example.org', context=context)
        with patch.object(public_http, 'public_addresses', return_value=['93.184.216.34']), patch.object(socket, 'socket', return_value=raw):
            connection.connect()
        raw.connect.assert_called_once_with(('93.184.216.34', 443))
        context.wrap_socket.assert_called_once_with(raw, server_hostname='example.org')

    def test_rebinding_and_wrong_peer_fail_before_tls(self):
        with patch.object(socket, 'getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]), patch.object(socket, 'socket') as factory:
            with self.assertRaises(public_http.FetchError):
                public_http.PinnedHTTPSConnection('example.org').connect()
            factory.assert_not_called()
        raw, context = MagicMock(), MagicMock()
        raw.getpeername.return_value = ('127.0.0.1', 443)
        with patch.object(public_http, 'public_addresses', return_value=['93.184.216.34']), patch.object(socket, 'socket', return_value=raw):
            with self.assertRaises(public_http.FetchError):
                public_http.PinnedHTTPSConnection('example.org', context=context).connect()
        context.wrap_socket.assert_not_called()
        raw.close.assert_called_once()

    def test_redirect_strips_credentials_and_bounds_response(self):
        first, second = MagicMock(), MagicMock()
        first.getresponse.return_value.status = 302
        first.getresponse.return_value.headers = {'Location': 'https://other.example/page'}
        response = second.getresponse.return_value
        response.status = 200
        response.headers = Message()
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.read.return_value = b'hello'
        with patch.object(public_http, 'public_addresses', return_value=['93.184.216.34']), patch.object(public_http, 'PinnedHTTPSConnection', side_effect=[first, second]):
            result = public_http.fetch('https://example.org/', {'Authorization': 'secret', 'Cookie': 'secret'}, max_bytes=5)
        self.assertEqual(result[1], b'hello')
        self.assertNotIn('Authorization', second.request.call_args.kwargs['headers'])
        self.assertNotIn('Cookie', second.request.call_args.kwargs['headers'])
        response.read.assert_called_once_with(6)
        first.close.assert_called_once()
        second.close.assert_called_once()
        response.read.return_value = b'123456'
        with patch.object(public_http, 'public_addresses', return_value=['93.184.216.34']), patch.object(public_http, 'PinnedHTTPSConnection', return_value=second):
            with self.assertRaisesRegex(public_http.FetchError, 'exceeded'):
                public_http.fetch('https://example.org/', max_bytes=5)

    def test_each_dns_result_is_public_and_unsafe_redirect_is_rejected(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443)) for ip in ['93.184.216.34', '10.0.0.1']]
        with patch.object(socket, 'getaddrinfo', return_value=addresses):
            with self.assertRaises(public_http.FetchError):
                public_http.validate_url('https://example.org/')
        for value in ['http://example.org', 'https://user:pass@example.org', 'https://example.org:8443', 'https://example.org/\n']:
            with self.subTest(value=value), self.assertRaises(public_http.FetchError):
                public_http.validate_url(value)

    def test_dns_rebinding_between_url_check_and_connection_is_rejected(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with patch.object(socket, 'getaddrinfo', side_effect=[public, private]), patch.object(socket, 'socket') as factory:
            with self.assertRaises(public_http.FetchError):
                public_http.fetch('https://example.org/')
            factory.assert_not_called()


class WorkspaceAndGithubTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_cli.JobBotSkillCliTest(methodName='runTest')
        self.fixture.setUp()
        self.workspace = self.fixture.workspace
        self.module = test_cli.load_cli_module()
        self.module.workspace_path(str(self.workspace))

    def tearDown(self):
        self.fixture.tearDown()

    def github(self, url='https://github.com/example', **kwargs):
        self.module.cmd_import_github(argparse.Namespace(workspace=str(self.workspace), url=url, id='github-test', label=None, max_pages=kwargs.get('max_pages', 10)))

    def test_outputs_reject_symlinks_and_predictable_temp_file(self):
        outside = self.workspace.parent / 'outside'
        outside.mkdir()
        jobs = self.workspace / 'jobs'
        jobs.rmdir()
        jobs.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.module.write_json(jobs / 'escape.json', {})
        jobs.unlink()
        jobs.mkdir()
        victim = outside / 'victim'
        victim.write_text('unchanged')
        (self.workspace / 'writing-rules.json.tmp').symlink_to(victim)
        with self.assertRaises(OSError):
            self.module.write_json(self.workspace / 'writing-rules.json', {})
        self.assertEqual(victim.read_text(), 'unchanged')
        self.assertEqual(list(outside.iterdir()), [victim])

    @unittest.skipUnless(os.name == 'posix', 'POSIX permission test')
    def test_new_files_and_directories_are_private_under_permissive_umask(self):
        previous = os.umask(0)
        try:
            path = self.workspace / 'nested' / 'private.json'
            self.module.write_json(path, {})
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_github_never_borrows_ambient_token_and_rejects_private_content(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'should-not-be-used'}), patch.object(self.module, 'http_get_bytes', return_value=('https://api.github.com/users/example', b'{}', 'application/json', 'utf-8')) as fetch:
            self.module.github_api_get('/users/example')
        self.assertNotIn('Authorization', fetch.call_args.kwargs.get('headers', {}))
        with patch.object(self.module, 'github_api_get', return_value=b'{"private":true,"visibility":"private"}') as api:
            with self.assertRaisesRegex(self.module.UserError, 'public'):
                self.github('https://github.com/example/repository')
        self.assertEqual(api.call_count, 1)
        self.assertEqual(list((self.workspace / 'evidence' / 'github').glob('*')), [])
        self.assertEqual(list((self.workspace / 'evidence/github-attempts').rglob('repository.json')), [])

    def test_profile_paginates_and_records_incomplete_coverage(self):
        page = [{'id': i, 'private': False} for i in range(100)]
        for limit, expected_complete in [(1, False), (2, True)]:
            with self.subTest(limit=limit):
                def api(path, **kwargs):
                    if '/repos?' not in path:
                        return b'{}'
                    return json.dumps(page if path.endswith('&page=1') else [{'id': 100, 'private': False}]).encode()
                args = argparse.Namespace(workspace=str(self.workspace), url='https://github.com/example', id=f'github-{limit}', label=None, max_pages=limit)
                with patch.object(self.module, 'github_api_get', side_effect=api):
                    self.module.cmd_import_github(args)
                source = self.module.load_evidence_sources(self.workspace)[f'github-{limit}']
                self.assertEqual(source['coverage']['complete'], expected_complete)
                self.assertEqual(source['coverage']['repositories_saved'], 100 if limit == 1 else 101)
                digest, paths = self.module.evidence_snapshot(self.workspace, source)
                self.assertEqual(digest, source['sha256'])
                self.assertTrue(any('repositories-page-1.json' in path for path in paths))
                if limit == 1:
                    self.assertEqual(source['coverage']['next_page'], 2)

    def test_render_tool_refuses_symlink_outputs(self):
        outside = self.workspace.parent / 'tool-output'
        outside.write_text('untouched')
        (self.workspace / 'resume.pdf').symlink_to(outside)
        with self.assertRaises(OSError):
            workspace_fs.check_tree(self.workspace)
        self.assertEqual(outside.read_text(), 'untouched')

    def test_failed_later_github_page_retains_partial_capture_without_publication(self):
        page = json.dumps([{'id': i, 'private': False} for i in range(100)]).encode()
        def api(path, **kwargs):
            if path.endswith('&page=2'):
                raise self.module.UserError('fixture: page two failed')
            return page if '/repos?' in path else b'{"login":"example"}'
        with patch.object(self.module, 'github_api_get', side_effect=api):
            with self.assertRaisesRegex(self.module.UserError, 'page two failed'):
                self.github(max_pages=2)
        attempts = list((self.workspace / 'evidence/github-attempts/github-test').glob('*'))
        self.assertEqual(len(attempts), 1)
        attempt = attempts[0]
        self.assertEqual((attempt / 'repositories-page-1.json').read_bytes(), page)
        self.assertEqual(json.loads((attempt / 'profile.json').read_text())['login'], 'example')
        receipt = json.loads((attempt / 'attempt.json').read_text())
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(len(receipt['captures']), 2)
        self.assertIn('page two failed', receipt['failure']['message'])
        self.assertNotIn('github-test', self.module.load_evidence_sources(self.workspace))
        self.assertFalse((self.workspace / 'evidence/github/example__profile').exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX hard-link test')
    def test_append_and_tool_outputs_refuse_hard_links(self):
        outside = self.workspace.parent / 'outside-inode'
        outside.write_text('untouched')
        linked = self.workspace / 'checks.jsonl'
        os.link(outside, linked)
        with self.assertRaises(OSError):
            workspace_fs.append_text(linked, 'overwrite')
        with self.assertRaises(OSError):
            workspace_fs.check_tree(self.workspace)
        self.assertEqual(outside.read_text(), 'untouched')


if __name__ == '__main__':
    unittest.main()
