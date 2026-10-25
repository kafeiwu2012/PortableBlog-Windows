"""Theme persistence, backwards compatibility and authorization."""
import unittest
import urllib.error
import test_archive_tags as fixtures


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ArchiveTagTests()
        self.fixture.setUp()
        self.request = self.fixture.request

    def tearDown(self):
        self.fixture.tearDown()

    def test_theme_catalog_and_defaults(self):
        state = self.request('state', public=True)
        self.assertEqual(state['settings']['theme'], 'minimal')
        self.assertEqual(len(state['themes']), 5)
        self.assertEqual(len({t['id'] for t in state['themes']}), 5)
        self.assertTrue(all({'name', 'description', 'accent', 'background'} <= t.keys() for t in state['themes']))

    def test_switch_all_themes_preserves_content_and_unrelated_settings(self):
        self.fixture.post(tags=['旅行'], published_at='2000-01-02T12:00')
        before = self.request('state')
        for theme in before['themes']:
            self.request('theme', {'theme': theme['id']})
            self.fixture.blog.init()  # Startup must not reset a saved theme.
            after = self.request('state', public=True)
            for key in ('theme', 'accent', 'background'):
                self.assertEqual(after['settings'][key], theme['id'] if key == 'theme' else theme[key])
            self.assertEqual(after['posts'], before['posts'])
            self.assertEqual(after['pages'], before['pages'])
            for key in before['settings'].keys() - {'theme', 'accent', 'background'}:
                self.assertEqual(after['settings'][key], before['settings'][key])

    def test_invalid_theme_or_color_is_rejected_atomically(self):
        before = self.request('state')['settings']
        for data in ({'theme': '../night'}, {'theme': 'unknown'}, {'theme': {}}, {'theme': 'night', 'accent': 'red'}, {'theme': 'night', 'background': 'url(https://example.com)'}, {'theme': 'paper', 'accent': None}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('theme', data)
            self.assertEqual(error.exception.code, 400)
            self.assertEqual(self.request('state')['settings'], before)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('theme', {'theme': 'night'}, public=True)
        self.assertEqual(error.exception.code, 401)
        self.assertEqual(self.request('state')['settings'], before)

    def test_custom_colors_and_existing_settings_keep_selected_theme(self):
        self.request('theme', {'theme': 'forest', 'accent': '#123456', 'background': '#eeeeee'})
        state = self.request('state')
        self.assertEqual(state['settings']['accent'], '#123456')
        settings = state['settings']
        self.request('settings', settings)
        self.assertEqual(self.request('state')['settings']['theme'], 'forest')

    def test_legacy_configuration_keeps_custom_colors(self):
        with self.fixture.blog.connect() as c:
            c.execute("DELETE FROM settings WHERE key='theme'")
            self.fixture.blog.save_setting(c, 'accent', '#123456')
            self.fixture.blog.save_setting(c, 'background', '#eeeeee')
        self.fixture.blog.init()
        settings = self.request('state')['settings']
        self.assertEqual(settings['theme'], 'minimal')
        self.assertEqual(settings['accent'], '#123456')
        self.assertEqual(settings['background'], '#eeeeee')


if __name__ == '__main__':
    unittest.main()
