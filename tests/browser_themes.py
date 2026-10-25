"""Optional: python3 tests/browser_themes.py (Playwright + Chromium)."""
import shutil
from playwright.sync_api import sync_playwright
from test_archive_tags import ArchiveTagTests, ROOT

fixture = ArchiveTagTests()
fixture.setUp()
try:
    shutil.copy(ROOT / 'index.html', fixture.blog.ROOT / 'index.html')
    (fixture.blog.ROOT / 'assets').symlink_to(ROOT / 'assets', target_is_directory=True)
    post_id = fixture.post(title='山间日记 · 记录生活的光', format='html', body='<p>晨光穿过树林，留下温柔的影子。</p><blockquote>收藏日常的细节。</blockquote><p><code>print("hello")</code></p><table><tbody><tr><td>日期</td><td>天气</td></tr></tbody></table><div class="blog-formula" data-formula="x^2+y^2=z^2">x^2+y^2=z^2</div>', tags=['旅行'])
    for n in range(3):
        fixture.post(title=f'日常片刻 {n+1}', body='用文字与影像记录生活。', tags=['旅行'])
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(fixture.base)
        page.evaluate("async()=>{await api('login',{password:'test-only-password'});await go('admin');tab('themes')}")
        page.locator('#theme-form').wait_for()
        assert page.locator('.theme-choice').count() == 5
        for theme in fixture.request('state')['themes']:
            page.locator(f'input[name=theme][value={theme["id"]}]').check()
            page.click('#apply-theme')
            page.wait_for_function('(id)=>state.settings.theme===id', arg=theme['id'])
            page.locator('#apply-theme:enabled').wait_for()
            page.reload()
            page.locator('.tabs button',has_text='主题模板').click()
            page.locator('#theme-form').wait_for()
            assert page.locator(f'input[name=theme][value={theme["id"]}]').is_checked()
            assert page.evaluate('getComputedStyle(document.body).color') == 'rgb(37, 43, 40)'  # Admin stays readable.
            for route in ('home', 'blog', 'post:'+post_id, 'archive', 'tags'):
                page.evaluate('(route)=>go(route)', route)
                assert page.get_attribute('body', 'data-theme') == theme['id']
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (theme['id'], route)
                if route == 'blog':
                    columns = page.evaluate('getComputedStyle(document.querySelector(".journal-grid")).gridTemplateColumns.split(" ").length')
                    assert columns == {'minimal': 3, 'paper': 1, 'forest': 2, 'night': 2, 'magazine': 2}[theme['id']]
                    if theme['id'] in ('forest', 'magazine'):
                        page.screenshot(path='/tmp/blog-theme-'+theme['id']+'.png', full_page=True)
                if route.startswith('post:'):
                    assert page.locator('.rich-document .katex').count() == 1
                    assert page.locator('.rich-document table').count() == 1
                    if theme['id'] == 'night':
                        assert page.evaluate('getComputedStyle(document.querySelector(".rich-document")).color') == 'rgb(231, 233, 238)'
                        page.screenshot(path='/tmp/blog-theme-night.png', full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (theme['id'], route, 'mobile')
                page.set_viewport_size({'width': 1280, 'height': 900})
            page.evaluate("async()=>{await go('admin');tab('themes')}")
        page.fill('#theme-accent', '#123456')
        page.click('#theme-reset-colors')
        assert page.input_value('#theme-accent') == fixture.request('state')['themes'][-1]['accent']
        page.fill('#theme-accent', '#123456')
        page.fill('#theme-background', '#eeeeee')
        page.click('#apply-theme')
        page.wait_for_function("()=>state.settings.accent==='#123456'")
        assert fixture.request('state')['settings']['background'] == '#eeeeee'
        assert not errors, errors
        browser.close()
        print('PASS: five theme choices, saved selection/reload, admin readability, distinct layouts, five public routes at desktop/mobile widths, night formulas/tables, default reset and custom colors.')
finally:
    fixture.tearDown()
