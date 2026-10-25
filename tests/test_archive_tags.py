"""API regression tests with isolated SQLite data and a real HTTP server."""
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1] / 'PortableBlog'


class ArchiveTagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        for name in ('blog.py', 'richtext.py'):
            shutil.copy(ROOT / name, root / name)
        spec = importlib.util.spec_from_file_location('archive_fixture', root / 'blog.py')
        self.blog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.blog)
        self.blog.init()
        self.server = self.blog.Server(('127.0.0.1', 0), self.blog.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.public = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.request('setup', {'password': 'test-only-password'})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, public=False):
        req = urllib.request.Request(self.base + '/api/' + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type': 'application/json', 'X-Blog-Request': '1', 'Origin': self.base})
        client = self.public if public else self.client
        with client.open(req) as response:
            return json.load(response)

    def post(self, **changes):
        value = dict(title='测试文章', body='正文', status='published', category='', attachments=[])
        value.update(changes)
        return self.request('post', value)['id']

    def test_historical_date_sorting_and_original_creation_preserved(self):
        newer = self.post(published_at='2020-02-29T10:30', tags=['旅行'])
        older = self.post(published_at='1999-12-31T23:59:59', tags=['生活'])
        before = self.request('state')['posts']
        self.assertEqual([p['id'] for p in before], [newer, older])
        created = before[0]['created']
        self.post(id=newer, published_at='1980-01-01T08:00:00')
        after = self.request('state')['posts']
        self.assertEqual([p['id'] for p in after], [older, newer])
        self.assertEqual(after[1]['created'], created)
        self.assertEqual(after[1]['tags'], ['旅行'])  # Legacy clients do not erase labels.

    def test_many_tags_edit_and_global_deletion_keeps_articles(self):
        first = self.post(tags=['旅行', '摄影', '旅行'])
        second = self.post(tags=['摄影'])
        state = self.request('state')
        self.assertEqual(next(p for p in state['posts'] if p['id'] == first)['tags'], ['旅行', '摄影'])
        self.assertEqual(sum('摄影' in p['tags'] for p in state['posts']), 2)
        self.post(id=first, tags=['摄影', '生活'])
        self.request('delete-tag', {'name': '摄影'})
        state = self.request('state')
        self.assertEqual(len(state['posts']), 2)
        self.assertNotIn('摄影', state['tags'])
        self.assertTrue(all('摄影' not in p['tags'] for p in state['posts']))
        self.assertEqual(next(p for p in state['posts'] if p['id'] == second)['tags'], [])
        self.request('delete-post', {'id': first})
        self.assertEqual([p['id'] for p in self.request('state')['posts']], [second])

    def test_draft_tags_hidden_and_mutations_require_login(self):
        self.post(status='draft', tags=['秘密'])
        self.post(tags=['公开'])
        self.request('add-tag', {'name': '未使用'})
        public = self.request('state', public=True)
        self.assertEqual(public['tags'], ['公开'])
        self.assertEqual(len(public['posts']), 1)
        for endpoint, data in [('add-tag', {'name': 'x'}), ('delete-tag', {'name': '公开'}), ('delete-post', {'id': public['posts'][0]['id']})]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request(endpoint, data, public=True)
            self.assertEqual(error.exception.code, 401)

    def test_invalid_dates_tags_and_transaction_rollback(self):
        for date in ('2023-02-29T10:00', '2020-13-01T10:00', 'not-a-date', 123, None, False):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post(published_at=date, tags=['不能写入'])
            self.assertEqual(error.exception.code, 400)
        for tags in ('text', ['x'] * 21, [''], ['x' * 41], [123], ['bad\nname']):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post(tags=tags)
            self.assertEqual(error.exception.code, 400)
        self.assertEqual(self.request('state')['posts'], [])
        self.assertEqual(self.request('state')['tags'], [])

    def test_old_database_migration_is_repeatable(self):
        with self.blog.connect() as c:
            c.execute('DROP TABLE posts')
            c.execute('CREATE TABLE posts(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,category TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,attachments TEXT NOT NULL)')
            c.execute('INSERT INTO posts VALUES (?,?,?,?,?,?,?,?)', ('legacy', '旧文', '原正文', '', 'published', '2001-02-03 04:05:06', '2001-02-03 04:05:06', '[]'))
        self.blog.init()
        self.blog.init()
        post = self.request('state')['posts'][0]
        self.assertEqual(post['published_at'], '2001-02-03 04:05:06')
        self.assertEqual(post['body'], '原正文')
        self.assertEqual(post['tags'], [])


if __name__ == '__main__':
    unittest.main()
