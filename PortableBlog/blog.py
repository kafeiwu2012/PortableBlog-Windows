#!/usr/bin/env python3
"""Portable Blog: standard-library-only local publishing."""
import base64, hashlib, hmac, io, json, mimetypes, os, re, secrets, shutil, sqlite3, sys, threading, time, urllib.parse, webbrowser, zipfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from richtext import sanitize, typography
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
MEDIA = DATA / 'media'
MEDIA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'blog.sqlite3'
LOCK = threading.RLock()
SESSIONS = {}
THEMES = [
    {'id':'minimal','name':'极简留白','description':'白底、宽留白与三栏图文，延续原有简洁风格。','accent':'#111111','background':'#ffffff'},
    {'id':'paper','name':'暖纸书卷','description':'米色纸张、宋体标题与单栏文章，适合散文和长篇日记。','accent':'#805233','background':'#f5efdf'},
    {'id':'forest','name':'森林手记','description':'柔绿背景、圆角双栏卡片，适合旅行与生活影像。','accent':'#285943','background':'#edf4ee'},
    {'id':'night','name':'深夜阅读','description':'深色背景、暖金点缀与双栏卡片，适合夜间阅读。','accent':'#efc77e','background':'#171b24'},
    {'id':'magazine','name':'杂志排版','description':'醒目标题、线条分隔与首篇大图布局，适合专题与摄影。','accent':'#b63826','background':'#faf9f6'},
]
ALLOWED = {'.jpg','.jpeg','.png','.gif','.webp','.avif','.bmp','.mp4','.webm','.ogg','.mov','.m4v','.mp3','.wav','.pdf','.txt'}
def connect():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    return c
def init():
    with connect() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS posts(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,category TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,attachments TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pages(slug TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,attachments TEXT NOT NULL,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY,name TEXT NOT NULL,file TEXT NOT NULL,type TEXT NOT NULL,size INTEGER NOT NULL,created TEXT NOT NULL);''')
        for table in ('posts','pages'):
            columns={r[1] for r in c.execute('PRAGMA table_info('+table+')')}
            if 'format' not in columns: c.execute("ALTER TABLE "+table+" ADD COLUMN format TEXT NOT NULL DEFAULT 'plain'")
            if 'typography' not in columns: c.execute("ALTER TABLE "+table+" ADD COLUMN typography TEXT NOT NULL DEFAULT '{}'")
        columns={r[1] for r in c.execute('PRAGMA table_info(posts)')}
        if 'published_at' not in columns:
            c.execute("ALTER TABLE posts ADD COLUMN published_at TEXT NOT NULL DEFAULT ''")
            c.execute("UPDATE posts SET published_at=created")
        if 'tags' not in columns:c.execute("ALTER TABLE posts ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
        c.execute('CREATE TABLE IF NOT EXISTS tags(name TEXT PRIMARY KEY)')
        defaults={'theme':'minimal','title':'我的私人博客','subtitle':'欢迎来到我的小小宇宙。','accent':'#111111','background':'#ffffff','categories':['生活记录','学习笔记','旅行'],'menus':[{'label':'Home','target':'home'},{'label':'About','target':'page:about'},{'label':'Blog','target':'blog'},{'label':'Contact','target':'page:contact'},{'label':'旅行','target':'category:旅行'}], 'blog_heading':'欢迎来玩。','footer_text':'记录生活，收藏时光。','page_size':9}
        for k,v in defaults.items(): c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(k,json.dumps(v,ensure_ascii=False)))
        if not c.execute("SELECT 1 FROM settings WHERE key='_pages_initialized'").fetchone():
            # Upgrade only untouched v1 defaults; custom menus and colors remain intact.
            current={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM settings')}
            old_menu=[{'label':'首页','target':'home'},{'label':'文章归档','target':'archive'},{'label':'媒体收藏','target':'media'}]
            if current.get('menus')==old_menu:
                save_setting(c,'menus',[{'label':'Home','target':'home'},{'label':'About','target':'page:about'},{'label':'Blog','target':'blog'},{'label':'Contact','target':'page:contact'}]+old_menu[1:])
            if current.get('accent')=='#335c49': save_setting(c,'accent','#111111')
            if current.get('background')=='#f6f3ed': save_setting(c,'background','#ffffff')
            for slug,title,body in [('home','Home','Hi, welcome to my universe.\n\n[[cover]]\n\n欢迎来到我的小小宇宙。\n这里收藏我的生活、旅途与日常片刻。'),('about','About','关于我\n\n这里是我的私人博客。\n用文字和影像，留下值得记住的日子。'),('contact','Contact','保持联系\n\n你可以在后台的“独立页面”中填写联系方式。')]:
                c.execute('INSERT OR IGNORE INTO pages (slug,title,body,attachments,status) VALUES (?,?,?,?,?)',(slug,title,body,'[]','published'))
            save_setting(c,'_pages_initialized',True)

def setting(k,default=None):
    with connect() as c:
        row=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone()
        return json.loads(row[0]) if row else default
def save_setting(c,k,v): c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(k,json.dumps(v,ensure_ascii=False)))
def clean_tags(value):
    if not isinstance(value,list) or len(value)>20:raise ValueError('每篇文章最多 20 个标签')
    result=[]
    for item in value:
        if not isinstance(item,str):raise ValueError('标签必须是文字')
        item=item.strip()
        if not 1<=len(item)<=40 or any(ord(ch)<32 or ord(ch)==127 for ch in item):raise ValueError('标签需为 1 至 40 个字，不能包含控制字符')
        if item not in result:result.append(item)
    return result

def publication_time(value):
    if not isinstance(value,str):raise ValueError('发布时间格式不正确')
    value=value.replace('T',' ')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}',value):value+=':00'
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',value):raise ValueError('请填写有效的发布时间')
    try:datetime.strptime(value,'%Y-%m-%d %H:%M:%S')
    except ValueError:raise ValueError('请填写有效的发布时间') from None
    return value

def now(): return time.strftime('%Y-%m-%d %H:%M:%S')
def password_hash(p,salt): return hashlib.scrypt(p.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
class Server(ThreadingHTTPServer):
    daemon_threads=True
class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,fmt,*args): pass
    def respond(self,status,body=b'',mime='application/json; charset=utf-8',headers=None):
        if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False).encode()
        if isinstance(body,str): body=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers()
        if self.command!='HEAD': self.wfile.write(body)
    def auth(self):
        cookie=self.headers.get('Cookie','')
        m=re.search(r'(?:^|;\s*)blog_session=([a-f0-9]+)',cookie)
        return bool(m and SESSIONS.get(m[1],0)>time.time())
    def valid_host(self):
        return self.headers.get('Host') in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port))
    def do_GET(self):
        try: self.get()
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception: self.respond(500,{'error':'读取失败，请检查数据文件或重启服务。'})
    def do_HEAD(self): self.do_GET()
    def get(self):
        if not self.valid_host(): return self.respond(403,{'error':'不允许的访问地址'})
        url=urllib.parse.urlsplit(self.path); path=url.path
        if path=='/': return self.respond(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
        if path.startswith('/assets/'):
            target=(ROOT/urllib.parse.unquote(path.lstrip('/'))).resolve()
            if not target.is_relative_to((ROOT/'assets').resolve()) or not target.is_file(): return self.respond(404,{'error':'文件不存在'})
            return self.respond(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        if path=='/api/state':
            with connect() as c:
                settings={r['key']:json.loads(r['value']) for r in c.execute('SELECT * FROM settings') if r['key']!='password' and not r['key'].startswith('_')}
                posts=[dict(r) for r in c.execute('SELECT * FROM posts ORDER BY published_at DESC,created DESC,id') if self.auth() or r['status']=='published']
                pages=[dict(r) for r in c.execute('SELECT * FROM pages ORDER BY slug') if self.auth() or r['status']=='published']
                media=[dict(r) for r in c.execute('SELECT * FROM media ORDER BY created DESC')]
                if not self.auth():
                    visible={a for p in posts+pages for a in json.loads(p['attachments'])}
                    media=[m for m in media if m['id'] in visible]
            for p in posts+pages:
                p['attachments']=json.loads(p['attachments'])
                p['typography']=json.loads(p['typography'])
            for p in posts:p['tags']=json.loads(p['tags'])
            with connect() as c:
                tags=[r[0] for r in c.execute('SELECT name FROM tags ORDER BY name')]
            if not self.auth():tags=[tag for tag in tags if any(tag in p['tags'] for p in posts)]
            return self.respond(200,{'themes':THEMES,'tags':tags,'settings':settings,'posts':posts,'pages':pages,'media':media,'admin':self.auth(),'needs_setup':setting('password') is None})
        if path.startswith('/media/'):
            ident=path.split('/')[-1]
            with connect() as c:
                row=c.execute('SELECT * FROM media WHERE id=?',(ident,)).fetchone()
                if row and not self.auth():
                    public=any(ident in json.loads(p[0]) for p in c.execute("SELECT attachments FROM posts WHERE status='published'"))
                    public=public or any(ident in json.loads(p[0]) for p in c.execute("SELECT attachments FROM pages WHERE status='published'"))
                    if not public: row=None
            if not row: return self.respond(404,{'error':'文件不存在或尚未发布'})
            file=MEDIA/row['file']
            if not file.is_file(): return self.respond(404,{'error':'文件丢失'})
            size=file.stat().st_size; start=0; end=size-1; status=200
            ran=self.headers.get('Range')
            if ran:
                m=re.fullmatch(r'bytes=(\d*)-(\d*)',ran)
                if not m or not any(m.groups()): return self.respond(416,b'',headers={'Content-Range':f'bytes */{size}'})
                if m[1]: start=int(m[1]); end=min(int(m[2]),end) if m[2] else end
                else: start=max(0,size-int(m[2]))
                if start>end or start>=size: return self.respond(416,b'',headers={'Content-Range':f'bytes */{size}'})
                status=206
            self.send_response(status); self.send_header('Content-Type',row['type']); self.send_header('Content-Length',str(end-start+1)); self.send_header('Accept-Ranges','bytes'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Cache-Control','no-store')
            self.send_header('Content-Disposition',"inline; filename*=UTF-8''"+urllib.parse.quote(row['name']))
            if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command!='HEAD':
                with file.open('rb') as f:
                    f.seek(start); remaining=end-start+1
                    while remaining:
                        b=f.read(min(1024*1024,remaining))
                        if not b: break
                        self.wfile.write(b); remaining-=len(b)
            return
        if path=='/api/backup':
            if not self.auth(): return self.respond(401,{'error':'请先登录'})
            # Consistent DB snapshot; media cannot be mutated during backup creation.
            import tempfile
            with LOCK, tempfile.TemporaryDirectory(dir=DATA) as temp:
                dest=Path(temp)/'blog.sqlite3'
                with connect() as src, sqlite3.connect(dest) as dst: src.backup(dst)
                archive=Path(temp)/'backup.zip'
                with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                    z.write(dest,'data/blog.sqlite3')
                    for f in MEDIA.iterdir():
                        if f.is_file(): z.write(f,'data/media/'+f.name)
                size=archive.stat().st_size
                self.send_response(200); self.send_header('Content-Type','application/zip'); self.send_header('Content-Length',str(size)); self.send_header('Content-Disposition','attachment; filename="blog-backup-'+time.strftime('%Y%m%d-%H%M%S')+'.zip"'); self.end_headers()
                if self.command!='HEAD':
                    with archive.open('rb') as f: shutil.copyfileobj(f,self.wfile)
            return
        self.respond(404,{'error':'页面不存在'})
    def do_POST(self):
        try:
            if not self.valid_host(): return self.respond(403,{'error':'访问地址不正确'})
            expected={'http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)}
            if self.headers.get('Origin') not in expected or self.headers.get('X-Blog-Request')!='1': return self.respond(403,{'error':'请求来源校验失败'})
            length=int(self.headers.get('Content-Length','0'))
            if length<0: return self.respond(400,{'error':'无效长度'})
            path=urllib.parse.urlsplit(self.path).path
            if path=='/api/upload':
                if not self.auth(): return self.respond(401,{'error':'请先登录'})
                if length>1024**3: return self.respond(413,{'error':'单文件最大支持 1GB'})
                name=urllib.parse.unquote(self.headers.get('X-Filename','file'))
                name=name.replace('\\','/').split('/')[-1][:240]; ext=Path(name).suffix.lower()
                if ext not in ALLOWED: return self.respond(400,{'error':'支持常见图片、视频、音频、PDF 和 TXT 文件；不支持该格式'})
                ident=secrets.token_hex(16); filename=ident+ext; target=MEDIA/filename
                with LOCK:
                    try:
                        with target.open('xb') as f:
                            remaining=length
                            while remaining:
                                chunk=self.rfile.read(min(1024*1024,remaining))
                                if not chunk: raise ValueError('文件上传中断')
                                f.write(chunk); remaining-=len(chunk)
                        mime=mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                        with connect() as c: c.execute('INSERT INTO media VALUES (?,?,?,?,?,?)',(ident,name,filename,mime,length,now()))
                    except Exception:
                        target.unlink(missing_ok=True); raise
                return self.respond(200,{'id':ident})
            if length>4*1024**2: return self.respond(413,{'error':'文本内容过大'})
            data=json.loads(self.rfile.read(length) or b'{}')
            with LOCK:
                if path in ('/api/setup','/api/login'):
                    password=data.get('password','')
                    if not isinstance(password,str) or len(password)>256: raise ValueError('密码长度不正确')
                    current=setting('password')
                    if path=='/api/setup':
                        if current: return self.respond(409,{'error':'后台已经初始化，请登录'})
                        if len(password)<8: raise ValueError('请设置至少 8 位密码')
                        salt=secrets.token_hex(16)
                        with connect() as c: save_setting(c,'password',{'salt':salt,'hash':password_hash(password,salt)})
                    elif not current or not hmac.compare_digest(password_hash(password,current['salt']),current['hash']):
                        time.sleep(0.5); return self.respond(401,{'error':'密码错误'})
                    token=secrets.token_hex(32); SESSIONS[token]=time.time()+12*3600
                    return self.respond(200,{'ok':True},headers={'Set-Cookie':f'blog_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'})
                if not self.auth(): return self.respond(401,{'error':'登录已过期，请重新登录'})
                if path=='/api/logout':
                    for token in re.findall(r'blog_session=([a-f0-9]+)',self.headers.get('Cookie','')): SESSIONS.pop(token,None)
                    return self.respond(200,{'ok':True},headers={'Set-Cookie':'blog_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
                if path=='/api/page':
                    slug=str(data.get('slug',''))
                    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,59}',slug): raise ValueError('页面标识只能使用小写字母、数字和短横线，最多 60 位')
                    title=str(data.get('title','')).strip()[:200]
                    if not title: raise ValueError('请填写页面标题')
                    body=str(data.get('body',''))
                    fmt=data.get('format','plain')
                    if fmt not in ('plain','html'): raise ValueError('文本格式不正确')
                    style=typography(data.get('typography'))
                    attachments=list(dict.fromkeys(re.findall(r'\[\[media:([a-f0-9]{32})\]\]',body)))
                    if fmt=='html': body,attachments=sanitize(body)
                    status=data.get('status','draft')
                    if status not in ('draft','published'): raise ValueError('页面状态不正确')
                    with connect() as c:
                        valid={r[0] for r in c.execute('SELECT id FROM media')}
                        if any(x not in valid for x in attachments): raise ValueError('页面引用的媒体不存在')
                        c.execute('INSERT OR REPLACE INTO pages (slug,title,body,attachments,status,format,typography) VALUES (?,?,?,?,?,?,?)',(slug,title,body,json.dumps(attachments),status,fmt,style))
                    return self.respond(200,{'ok':True})
                if path=='/api/delete-page':
                    slug=data.get('slug')
                    if slug=='home': raise ValueError('首页不能删除，可编辑首页内容')
                    with connect() as c:
                        menus=setting('menus',[])
                        if any(m['target']=='page:'+str(slug) for m in menus): raise ValueError('请先在菜单设置中移除此页面的导航项')
                        c.execute('DELETE FROM pages WHERE slug=?',(slug,))
                    return self.respond(200,{'ok':True})
                if path=='/api/post':
                    title=str(data.get('title','')).strip()[:200]
                    if not title: raise ValueError('请填写文章标题')
                    ident=data.get('id') or secrets.token_hex(16)
                    body=str(data.get('body',''))
                    fmt=data.get('format','plain')
                    if fmt not in ('plain','html'): raise ValueError('文本格式不正确')
                    style=typography(data.get('typography'))
                    inline=[]
                    if fmt=='html':body,inline=sanitize(body)
                    status=data.get('status','draft')
                    if status not in ('draft','published'): raise ValueError('文章状态不正确')
                    category=str(data.get('category',''))
                    if category and category not in setting('categories'): raise ValueError('请选择已有类目')
                    attachments=data.get('attachments',[])
                    if not isinstance(attachments,list): raise ValueError('附件格式错误')
                    attachments=list(dict.fromkeys(attachments+inline))
                    with connect() as c:
                        valid={r[0] for r in c.execute('SELECT id FROM media')}
                        if any(x not in valid for x in attachments): raise ValueError('附件不存在')
                        existing=c.execute('SELECT created,published_at,tags FROM posts WHERE id=?',(ident,)).fetchone()
                        published_value=data.get('published_at','')
                        published_at=publication_time((existing['published_at'] if existing else now()) if published_value=='' else published_value)
                        tags=clean_tags(data.get('tags',json.loads(existing['tags']) if existing else []))
                        for tag in tags:c.execute('INSERT OR IGNORE INTO tags(name) VALUES (?)',(tag,))
                        c.execute('INSERT OR REPLACE INTO posts (id,title,body,category,status,created,updated,attachments,format,typography,published_at,tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(ident,title,body,category,status,existing['created'] if existing else now(),now(),json.dumps(list(dict.fromkeys(attachments))),fmt,style,published_at,json.dumps(tags,ensure_ascii=False)))
                    return self.respond(200,{'id':ident})
                if path=='/api/theme':
                    selected=next((theme for theme in THEMES if theme['id']==data.get('theme')),None)
                    if selected is None:raise ValueError('请选择有效的主题模板')
                    colors={key:data.get(key,selected[key]) for key in ('accent','background')}
                    if any(not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value) for value in colors.values()):raise ValueError('颜色格式不正确')
                    with connect() as c:
                        save_setting(c,'theme',selected['id'])
                        for key,value in colors.items():save_setting(c,key,value)
                elif path=='/api/add-tag':
                    tag=clean_tags([data.get('name')])[0]
                    with connect() as c:c.execute('INSERT OR IGNORE INTO tags(name) VALUES (?)',(tag,))
                elif path=='/api/delete-tag':
                    tag=clean_tags([data.get('name')])[0]
                    with connect() as c:
                        c.execute('DELETE FROM tags WHERE name=?',(tag,))
                        for row in c.execute('SELECT id,tags FROM posts').fetchall():
                            tags=json.loads(row['tags'])
                            if tag in tags:c.execute('UPDATE posts SET tags=? WHERE id=?',(json.dumps([x for x in tags if x!=tag],ensure_ascii=False),row['id']))
                elif path=='/api/delete-post':
                    with connect() as c: c.execute('DELETE FROM posts WHERE id=?',(data.get('id'),))
                elif path=='/api/delete-media':
                    ident=data.get('id')
                    with connect() as c:
                        if any(ident in json.loads(r[0]) for r in c.execute('SELECT attachments FROM posts UNION ALL SELECT attachments FROM pages')): raise ValueError('文件正在被文章或页面使用，请先移除引用')
                        row=c.execute('SELECT file FROM media WHERE id=?',(ident,)).fetchone()
                        if row: (MEDIA/row[0]).unlink(missing_ok=True)
                        c.execute('DELETE FROM media WHERE id=?',(ident,))
                elif path=='/api/settings':
                    cats=data.get('categories',[]); menus=data.get('menus',[])
                    if not isinstance(cats,list) or len(cats)>100 or any(not isinstance(x,str) or not x.strip() or len(x)>80 for x in cats): raise ValueError('类目格式不正确，最多 100 个')
                    if not isinstance(menus,list) or len(menus)>20: raise ValueError('菜单最多 20 项')
                    with connect() as c: page_targets={'page:'+r[0] for r in c.execute('SELECT slug FROM pages')}
                    targets={'home','blog','archive','tags','media'}|{'category:'+x for x in cats}|page_targets
                    for m in menus:
                        if not isinstance(m,dict) or m.get('target') not in targets or not str(m.get('label','')).strip(): raise ValueError('菜单目标需为首页、博客、归档、媒体、现有页面或类目')
                    if 'page_size' in data and (type(data['page_size']) is not int or not 1<=data['page_size']<=60): raise ValueError('每页文章数需为 1 至 60')
                    for k in ('accent','background'):
                        if not re.fullmatch(r'#[0-9a-fA-F]{6}',str(data.get(k,''))): raise ValueError('颜色格式不正确')
                    with connect() as c:
                        # Deleted categories become uncategorized; articles remain intact.
                        for r in c.execute('SELECT id,category FROM posts').fetchall():
                            if r['category'] and r['category'] not in cats: c.execute("UPDATE posts SET category='' WHERE id=?",(r['id'],))
                        for k in ('title','subtitle','accent','background','categories','menus','blog_heading','footer_text','page_size'):
                            if k not in data: continue
                            value=data.get(k,'')
                            if k in ('title','subtitle','blog_heading','footer_text'): value=str(value)[:300]
                            save_setting(c,k,value)
                elif path=='/api/password':
                    current=setting('password'); old=str(data.get('old','')); new=str(data.get('password',''))
                    if not hmac.compare_digest(password_hash(old,current['salt']),current['hash']): raise ValueError('原密码错误')
                    if not 8<=len(new)<=256: raise ValueError('新密码需为 8 至 256 位')
                    salt=secrets.token_hex(16)
                    with connect() as c: save_setting(c,'password',{'salt':salt,'hash':password_hash(new,salt)})
                    SESSIONS.clear()
                else: return self.respond(404,{'error':'接口不存在'})
            self.respond(200,{'ok':True})
        except (ValueError,TypeError,KeyError) as e: self.respond(400,{'error':str(e)})
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception: self.respond(500,{'error':'保存失败。请检查磁盘空间及文件夹写入权限。'})
        finally:
            # Rejecting large uploads must not leave unread bytes on a reused connection.
            self.close_connection=True

def main():
    init()
    port=int(os.environ.get('BLOG_PORT','8765'))
    try: server=Server(('127.0.0.1',port),Handler)
    except OSError:
        print('Port is busy. Close the previous Blog window, or set BLOG_PORT to another port.')
        return 1
    print(f'Portable Blog: http://127.0.0.1:{port}\nData: {DATA}\nPress Ctrl+C to stop. Close this window before copying the folder.',flush=True)
    if '--no-browser' not in sys.argv: threading.Timer(0.8,lambda:webbrowser.open(f'http://127.0.0.1:{port}')).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0
if __name__=='__main__': sys.exit(main())
