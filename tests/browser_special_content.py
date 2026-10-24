"""Optional browser regression: python3 tests/browser_special_content.py
Requires Playwright and Chromium; uses a temporary database, never user data.
"""
import os,sys,tempfile,shutil,subprocess,time,json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='blog-special-') as tmp:
 app=Path(tmp)/'PortableBlog';app.mkdir()
 for name in ('blog.py','richtext.py','index.html'):shutil.copy(root/'PortableBlog'/name,app/name)
 (app/'assets').symlink_to(root/'PortableBlog/assets',target_is_directory=True)
 server=subprocess.Popen([sys.executable,str(app/'blog.py'),'--no-browser'],env={**os.environ,'BLOG_PORT':'18765'},stdout=subprocess.DEVNULL)
 try:
  with sync_playwright() as p:
   b=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
   page=b.new_page();errors=[];failures=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('response',lambda r: failures.append(r.url) if r.status>=400 else None)
   for attempt in range(30):
    try:page.goto('http://127.0.0.1:18765');break
    except Exception:time.sleep(.1)
   page.wait_for_function('typeof richEditor === "function"')
   page.evaluate("async()=>{await api('setup',{password:'browser-test-only'});await refresh();document.body.innerHTML+='<div id=admin-content></div>';richEditor('post')}")
   page.fill('#rich-title','表格与公式验证')
   page.click('#insert-table');page.fill('#table-rows','2');page.fill('#table-cols','2');page.click('dialog button[type=submit]')
   cell=page.locator('.ql-editor td').first;cell.click();page.keyboard.type('cell-one')
   page.select_option('#table-action','insertRowBelow');assert page.locator('.ql-editor tr').count()==3
   page.select_option('#table-action','insertColumnRight');assert page.locator('.ql-editor tr').first.locator('td').count()==3
   page.select_option('#table-action','deleteColumn');assert page.locator('.ql-editor tr').first.locator('td').count()==2
   page.select_option('#table-action','deleteRow');assert page.locator('.ql-editor tr').count()==2
   page.locator('.ql-editor td').first.click();page.keyboard.type('persisted-cell')
   page.evaluate('activeQuill.setSelection(activeQuill.getLength()-1,0)')
   for example in ('fraction','integral','matrix','aligned'):
    page.click('#insert-formula');page.select_option('#math-example',example);assert page.locator('#special-error').inner_text()=='';page.click('dialog button[type=submit]')
   assert page.locator('.ql-editor .blog-formula').count()==4
   page.locator('.ql-editor .blog-formula').first.dblclick();page.fill('#math-source',r'\frac{1}{2}');page.click('dialog button[type=submit]');assert page.locator('.ql-editor .blog-formula').first.get_attribute('data-formula')==r'\frac{1}{2}'
   page.click('#editor-undo');assert page.locator('.ql-editor .blog-formula').first.get_attribute('data-formula')!=r'\frac{1}{2}'
   page.click('#editor-redo');assert page.locator('.ql-editor .blog-formula').first.get_attribute('data-formula')==r'\frac{1}{2}'
   page.click('#insert-formula');page.fill('#math-source',r'\notARealCommand{x}');page.click('dialog button[type=submit]');assert page.locator('dialog[open]').count()==1;assert page.locator('#special-error').inner_text();page.click('#special-cancel')
   page.click('#preview-mode');assert page.locator('#rich-preview table').count()==1;assert page.locator('#rich-preview .katex').count()==4
   page.select_option('#rich-status','published');page.click('#rich-save');page.wait_for_function("()=>state.posts.some(p=>p.title==='表格与公式验证')")
   post=page.evaluate("state.posts.find(p=>p.title==='表格与公式验证')");assert 'data-row=' in post['body'] and 'data-formula=' in post['body'];assert 'katex-html' not in post['body']
   page.reload();page.wait_for_function('typeof richEditor === "function"');page.evaluate("async(id)=>{await refresh();document.body.innerHTML+='<div id=admin-content></div>';richEditor('post',id)}",post['id'])
   assert page.locator('.ql-editor table').count()==1;assert page.locator('.ql-editor td').count()==4;assert 'persisted-cell' in page.locator('.ql-editor').inner_text();assert page.locator('.ql-editor .katex').count()==4
   page.evaluate("id=>article(id)",post['id']);assert page.locator('.article table').count()==1;assert page.locator('.article .katex').count()==4
   page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
   page.evaluate('document.fonts.ready');assert not errors,errors;assert not failures,failures
   print('PASS: table cell input and row/column actions; four formula examples; source re-edit; undo/redo; invalid formula rejected; preview; API save; reload; public/mobile render; all assets loaded without errors.')
   b.close()
 finally:server.terminate();server.wait()
