"""Conservative local-document HTML allowlist. No executable or remote embeds."""
from html import escape
from html.parser import HTMLParser
import json, re
ALLOWED={'p','br','h1','h2','h3','h4','strong','b','em','i','u','s','blockquote','pre','code','ul','ol','li','a','img','video','audio','hr','span','div','sub','sup','table','thead','tbody','tfoot','tr','td','th','caption'}
VOID={'br','img','hr'}
BLOCKED={'script','style','iframe','object','embed','svg','math','template'}
CLASS=re.compile(r'ql-(?:align-(?:center|right|justify)|indent-[1-8]|font-(?:serif|sans|monospace)|size-(?:small|large|huge)|direction-rtl|syntax)\Z')
MEDIA=re.compile(r'/media/([a-f0-9]{32})\Z')
COLOR=re.compile(r'(?:#[a-fA-F0-9]{3,8}|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)|[a-zA-Z]{1,20})\Z')
def safe_style(value):
    clean=[]
    for declaration in value.split(';'):
        key,sep,val=declaration.partition(':');key=key.strip().lower();val=val.strip()
        if key in ('color','background-color') and COLOR.fullmatch(val): clean.append(f'{key}:{val}')
        elif key=='text-align' and val in ('left','center','right','justify'): clean.append(f'{key}:{val}')
        elif key=='font-weight' and val in ('bold','normal','400','700'): clean.append(f'{key}:{val}')
        elif key=='font-style' and val in ('italic','normal'): clean.append(f'{key}:{val}')
        elif key=='text-decoration' and val in ('underline','line-through','none'): clean.append(f'{key}:{val}')
        elif key=='font-family':
            fonts={'serif':'serif','sans-serif':'sans-serif','monospace':'monospace'}
            if val in fonts:clean.append(f'{key}:{val}')
    return ';'.join(clean)
class Cleaner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.out=[];self.stack=[];self.blocked=[];self.media=[]
    def handle_starttag(self,tag,attrs):
        if tag in BLOCKED:self.blocked.append(tag);return
        if self.blocked or tag not in ALLOWED:return
        attrs=dict(attrs);clean=[]
        if tag in ('img','video','audio'):
            src=attrs.get('src','');match=MEDIA.fullmatch(src)
            if not match and not (tag=='img' and src=='/assets/cover.svg'):return
            clean.append(('src',src))
            if match:self.media.append(match[1])
            if tag in ('video','audio'):clean.extend([('controls',''),('preload','metadata')])
            if tag=='img':
                clean.append(('alt',attrs.get('alt','')[:300]))
                width=attrs.get('width','')
                if re.fullmatch(r'(?:[1-9]\d{0,3}|(?:[1-9]\d?|100)%)',width):clean.append(('width',width))
        if tag=='a':
            href=attrs.get('href','').strip()
            if re.match(r'(?i)^(?:https?://|mailto:|#)',href) and not re.search(r'[\x00-\x20]',href):
                clean.extend([('href',href),('target','_blank'),('rel','noopener noreferrer')])
            elif MEDIA.fullmatch(href):
                clean.append(('href',href));self.media.append(MEDIA.fullmatch(href)[1])
        if tag in ('td','th'):
            for name in ('colspan','rowspan'):
                value=attrs.get(name,'')
                if re.fullmatch(r'[1-9]\d?',value):clean.append((name,value))
            row=attrs.get('data-row','')
            if re.fullmatch(r'[a-zA-Z0-9-]{1,80}',row):clean.append(('data-row',row))
        if tag=='div' and 'blog-formula' in attrs.get('class','').split():
            source=attrs.get('data-formula','')
            if 0<len(source)<=8000:
                clean.extend([('class','blog-formula'),('data-formula',source)])
        classes=' '.join(x for x in attrs.get('class','').split() if CLASS.fullmatch(x))
        if classes:clean.append(('class',classes))
        style=safe_style(attrs.get('style',''))
        if style:clean.append(('style',style))
        self.out.append('<'+tag+''.join(' '+k+'="'+escape(str(v),quote=True)+'"' for k,v in clean)+'>')
        if tag not in VOID:self.stack.append(tag)
    def handle_endtag(self,tag):
        if self.blocked:
            if tag in self.blocked:
                while self.blocked:
                    if self.blocked.pop()==tag:break
            return
        if tag in self.stack:
            while self.stack:
                current=self.stack.pop();self.out.append('</'+current+'>')
                if current==tag:break
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)
    def handle_data(self,data):
        if not self.blocked:self.out.append(escape(data))
    def finish(self):
        while self.stack:self.out.append('</'+self.stack.pop()+'>')
        return ''.join(self.out),list(dict.fromkeys(self.media))
def sanitize(body):
    parser=Cleaner();parser.feed(body);parser.close();return parser.finish()
def typography(value):
    if value is None:value={}
    if not isinstance(value,dict):raise ValueError('排版设置格式不正确')
    result={'font':value.get('font','serif'),'size':value.get('size',18),'line':value.get('line',2),'spacing':value.get('spacing','airy')}
    if result['font'] not in ('serif','sans','monospace') or result['size'] not in (16,18,20,22,24) or result['line'] not in (1.6,1.8,2,2.2) or result['spacing'] not in ('compact','normal','airy'):raise ValueError('排版设置超出支持范围')
    return json.dumps(result)
