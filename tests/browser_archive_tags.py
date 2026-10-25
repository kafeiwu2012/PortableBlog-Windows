"""Optional: python3 tests/browser_archive_tags.py (Playwright + Chromium)."""
import shutil
from playwright.sync_api import sync_playwright
from test_archive_tags import ArchiveTagTests, ROOT

fixture = ArchiveTagTests()
fixture.setUp()
try:
    shutil.copy(ROOT / 'index.html', fixture.blog.ROOT / 'index.html')
    (fixture.blog.ROOT / 'assets').symlink_to(ROOT / 'assets', target_is_directory=True)
    first = fixture.post(title='跨标签日记', published_at='2000-01-02T03:04:05', tags=['旅行', '摄影'])
    fixture.post(title='新日记', published_at='2025-09-20T12:00', tags=['摄影'])
    fixture.post(title='私密草稿', status='draft', tags=['私密'])
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(fixture.base)
        page.locator('#nav [data-view=archive]').click()
        page.locator('#archive-results').wait_for()
        assert page.locator('#archive-results [data-post]').count() == 2
        assert page.locator('#archive-results [data-post]').first.inner_text() == '新日记'
        page.select_option('#archive-order', 'asc')
        assert page.locator('#archive-results [data-post]').first.inner_text() == '跨标签日记'
        page.select_option('#archive-year', '2000')
        assert page.locator('#archive-results [data-post]').count() == 1
        page.select_option('#archive-month', '01')
        page.fill('#archive-day', '2000-01-02')
        page.locator('#archive-day').dispatch_event('change')
        assert page.locator('#archive-results [data-post]').count() == 1
        page.click('#archive-reset')
        assert page.locator('#archive-results [data-post]').count() == 2
        for tag, count in [('旅行', 1), ('摄影', 2)]:
            page.locator('#nav [data-view=tags]').click()
            page.locator(f'#main [data-tag="{tag}"]').click()
            page.locator('#journal-results').wait_for()
            assert page.locator('#journal-results [data-post]').count() == count
            assert page.locator(f'#journal-results [data-post="{first}"]').count() == 1
        page.locator(f'#journal-results [data-post="{first}"]').click()
        page.locator('.article .tag-links').wait_for()
        assert page.locator('.article [data-tag]').count() == 2
        page.reload()
        page.locator('.article .tag-links').wait_for()
        page.evaluate("async()=>{await api('login',{password:'test-only-password'});await go('admin')}")
        page.locator(f'#admin-post-results button[onclick="editPost(\'{first}\')"]').click()
        assert page.input_value('#rich-published') == '2000-01-02T03:04:05'
        page.fill('#rich-published', '1990-02-03T10:20:30')
        page.locator('#post-tag-options input[value="旅行"]').uncheck()
        page.fill('#new-post-tag', '生活')
        page.click('#add-post-tag')
        page.click('#rich-save')
        page.locator('#admin-post-results').wait_for()
        post = next(p for p in fixture.request('state')['posts'] if p['id'] == first)
        assert post['tags'] == ['摄影', '生活']
        assert post['published_at'] == '1990-02-03 10:20:30'
        page.select_option('#admin-post-tag', '生活')
        assert page.locator('#admin-post-results .listrow').count() == 1
        page.locator('.tabs button', has_text='标签管理').click()
        page.on('dialog', lambda dialog: dialog.accept())
        page.locator('[data-delete-tag="摄影"]').click()
        page.wait_for_function("()=>!state.tags.includes('摄影')")
        assert len(fixture.request('state')['posts']) == 3
        assert all('摄影' not in p['tags'] for p in fixture.request('state')['posts'])
        page.evaluate('id=>go("post:"+id)', first)
        page.locator('.article .article-actions .danger').click()
        page.locator('#admin-post-results').wait_for()
        assert len(fixture.request('state')['posts']) == 2
        page.evaluate('()=>go("archive")')
        page.locator('#archive-results').wait_for()
        assert page.locator('#archive-results [data-post]').count() == 2  # Owner includes draft.
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors, errors
        browser.close()
        print('PASS: date ordering/filtering; cross-tag navigation; historical date and tag edits; global tag removal keeps posts; article deletion from reading view; owner draft archive; mobile layout.')
finally:
    fixture.tearDown()
