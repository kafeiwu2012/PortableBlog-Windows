/* Chronological browsing and many-to-many article labels, entirely offline. */
function postDate(post){
 if(post.published_at||post.created)return post.published_at||post.created;
 const d=new Date(),pad=n=>String(n).padStart(2,'0');
 return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
function publicTags(){return [...new Set(published().flatMap(p=>p.tags||[]))].sort((a,b)=>a.localeCompare(b,'zh-CN'))}
function tagLinks(post){return `<div class="tag-links">${(post.tags||[]).map(tag=>`<button type="button" data-tag="${esc(tag)}">#${esc(tag)}</button>`).join('')}</div>`}
document.addEventListener('click',event=>{const button=event.target.closest('[data-tag]');if(button){event.stopPropagation();go('tag:'+button.dataset.tag)}});
function renderTags(){
 const tags=publicTags();
 $('#main').innerHTML=`<section class="site-page"><h1>文章标签</h1><p class="muted">一篇文章可以出现在多个标签下。</p><div class="tag-links">${tags.map(tag=>`<button data-tag="${esc(tag)}">${esc(tag)} <small>(${published().filter(p=>(p.tags||[]).includes(tag)).length})</small></button>`).join('')||'<p>暂无已发布文章的标签。</p>'}</div><button onclick="go('archive')">按时间浏览全部文章</button></section>`;
}
function renderArchive(){
 const posts=state.admin?state.posts:published();
 const years=[...new Set(posts.map(p=>postDate(p).slice(0,4)))].sort().reverse();
 $('#main').innerHTML=`<section class="site-page"><h1>时间归档</h1><p class="muted">共 ${posts.length} 篇${state.admin?'（含草稿，仅后台可见）':'已发布文章'}，按发布时间排列。</p><div class="archive-filters"><label>年份<select id="archive-year"><option value="">全部年份</option>${years.map(y=>`<option>${esc(y)}</option>`).join('')}</select></label><label>月份<select id="archive-month"><option value="">全部月份</option>${Array.from({length:12},(_,i)=>`<option value="${String(i+1).padStart(2,'0')}">${i+1} 月</option>`).join('')}</select></label><label>具体日期<input id="archive-day" type="date"></label><label>排列<select id="archive-order"><option value="desc">最新在前</option><option value="asc">最早在前</option></select></label><button id="archive-reset">清除筛选</button></div><div id="archive-results"></div></section>`;
 function results(){
  const year=$('#archive-year').value,month=$('#archive-month').value,day=$('#archive-day').value,ascending=$('#archive-order').value==='asc';
  const visible=posts.filter(p=>{const date=postDate(p);return (!year||date.startsWith(year+'-'))&&(!month||date.slice(5,7)===month)&&(!day||date.slice(0,10)===day)}).sort((a,b)=>{const cmp=postDate(a).localeCompare(postDate(b))||a.id.localeCompare(b.id);return ascending?cmp:-cmp});
  let last='';
  $('#archive-results').innerHTML=`<p class="muted">显示 ${visible.length} 篇</p>`+(visible.map(p=>{const month=postDate(p).slice(0,7);const heading=month!==last?`<h2 class="archive-year">${esc(month.replace('-',' 年 '))} 月</h2>`:'';last=month;return `${heading}<div class="listrow"><div class="name"><button data-post="${p.id}">${esc(p.title)}</button>${tagLinks(p)}</div><time datetime="${postDate(p).replace(' ','T')}">${postDate(p).slice(0,10)}</time>${p.status==='draft'?'<span class="badge">草稿</span>':''}</div>`}).join('')||'<p>没有符合日期的文章。</p>');
  $('#archive-results').querySelectorAll('[data-post]').forEach(button=>button.onclick=()=>go('post:'+button.dataset.post));
 }
 for(const id of ['year','month','day','order'])$('#archive-'+id).onchange=results;
 $('#archive-reset').onclick=()=>{for(const id of ['year','month','day'])$('#archive-'+id).value='';results()};results();
}
async function managePost(id){await go('admin');if(view==='admin')editPost(id)}
function postList(){
 $('#admin-content').innerHTML=`<div class="toolbar"><span class="muted">共 ${state.posts.length} 篇文章 · 草稿仅后台可见</span><div class="row"><button onclick="go('archive')">时间归档</button><button class="primary" onclick="editPost()">＋ 写文章</button></div></div><label>按标签筛选<select id="admin-post-tag"><option value="">全部标签</option>${(state.tags||[]).map(tag=>`<option value="${esc(tag)}">${esc(tag)}</option>`).join('')}</select></label><div id="admin-post-results" class="panel"></div>`;
 function results(){const tag=$('#admin-post-tag').value;const posts=state.posts.filter(p=>!tag||(p.tags||[]).includes(tag));$('#admin-post-results').innerHTML=posts.map(p=>`<div class="listrow"><div class="name"><strong>${esc(p.title)}</strong><div class="muted">发布：${postDate(p)} · ${esc(p.category||'未分类')} · ${p.status==='draft'?'草稿':'已发布'}</div>${tagLinks(p)}</div><button onclick="go('post:${p.id}')">预览</button><button onclick="editPost('${p.id}')">编辑 / 标签</button><button class="danger" onclick="deletePost('${p.id}')">删除文章</button></div>`).join('')||'暂无符合条件的文章。'}
 $('#admin-post-tag').onchange=results;results();
}
function tagsPage(){
 $('#admin-content').innerHTML=`<section class="panel"><h3>标签管理</h3><p class="help">一篇文章可关联多个标签。在文章编辑页勾选或取消标签；删除标签只解除关联，保留所有文章。</p><form id="new-tag-form" class="row"><input id="new-tag-name" maxlength="40" placeholder="新标签名称" aria-label="新标签名称" required><button type="submit">添加标签</button></form><div id="tag-management">${(state.tags||[]).map(tag=>`<div class="listrow"><span class="name">${esc(tag)} <small>(${state.posts.filter(p=>(p.tags||[]).includes(tag)).length} 篇)</small></span><button type="button" data-tag="${esc(tag)}">查看已发布文章</button><button type="button" class="danger" data-delete-tag="${esc(tag)}">删除标签</button></div>`).join('')||'<p>暂无标签，可以添加或在编辑文章时创建。</p>'}</div></section>`;
 $('#new-tag-form').onsubmit=async event=>{event.preventDefault();try{await api('add-tag',{name:$('#new-tag-name').value});await refresh();tagsPage();notice('标签已添加')}catch(error){notice(error.message)}};
 $('#tag-management').querySelectorAll('[data-delete-tag]').forEach(button=>button.onclick=async()=>{const name=button.dataset.deleteTag;if(!confirm(`删除标签“${name}”？所有文章会保留，只移除该标签。`))return;try{await api('delete-tag',{name});await refresh();tagsPage();notice('标签已删除，文章保留')}catch(error){notice(error.message)}});
}
