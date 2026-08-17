```{=html}
<%
const catCounts = {};
items.forEach(i => (i.categories||[]).forEach(c => catCounts[c]=(catCounts[c]||0)+1));
const cats = Object.keys(catCounts).sort();
const maxCat = Math.max(1, ...Object.values(catCounts));
const srcs = [...new Set(items.map(i=>i.source))].sort();
const doms = [...new Set(items.map(i=>i.domain))].sort();
const tg = new Set(); items.forEach(i=>(i.tags||[]).forEach(t=>tg.add(t)));
const tags = [...tg].sort();
const total = items.length;
const words = items.reduce((a,i)=>a+(i.tldr||[]).join(' ').split(/\s+/).filter(Boolean).length,0);
const readMin = Math.max(1, Math.round(words/200));
%>

<div class="digest-stats">
  <div class="stat"><i class="bi bi-newspaper"></i><span class="stat-num"><%= total %></span><span class="stat-lbl">stories</span></div>
  <div class="stat"><i class="bi bi-collection"></i><span class="stat-num"><%= cats.length %></span><span class="stat-lbl">topics</span></div>
  <div class="stat"><i class="bi bi-globe2"></i><span class="stat-num"><%= srcs.length %></span><span class="stat-lbl">sources</span></div>
  <div class="stat"><i class="bi bi-tags"></i><span class="stat-num"><%= tags.length %></span><span class="stat-lbl">tags</span></div>
  <div class="stat"><i class="bi bi-clock"></i><span class="stat-num"><%= readMin %></span><span class="stat-lbl">min read</span></div>
</div>

<div class="digest-filters">
  <div class="filter-group">
    <span class="filter-label"><i class="bi bi-funnel"></i> Source</span>
    <button class="filter-chip" data-group="source" data-value="all">All</button>
    <% for (const s of srcs) { %><button class="filter-chip" data-group="source" data-value="<%- s %>"><%= s %></button><% } %>
  </div>
  <div class="filter-group">
    <span class="filter-label"><i class="bi bi-globe"></i> Domain</span>
    <button class="filter-chip" data-group="domain" data-value="all">All</button>
    <% for (const d of doms) { %><button class="filter-chip" data-group="domain" data-value="<%- d %>"><%= d %></button><% } %>
  </div>
  <div class="filter-group">
    <span class="filter-label"><i class="bi bi-tag"></i> Tag</span>
    <button class="filter-chip" data-group="tag" data-value="all">All</button>
    <% for (const t of tags) { %><button class="filter-chip" data-group="tag" data-value="<%- t %>"><%= t %></button><% } %>
  </div>
  <div class="filter-clear"><button class="filter-chip clear" id="digest-clear">Clear all</button><span id="digest-count" class="filter-count"></span></div>
</div>

<div class="digest-cloud">
  <span class="filter-label"><i class="bi bi-cloud"></i> Topics</span>
  <% for (const c of cats) { %>
    <button class="cat-chip" data-group="cat" data-value="<%- c %>" style="font-size:<%= 0.78 + 0.55*(catCounts[c]/maxCat) %>rem"><%= c %> <span class="cat-n"><%= catCounts[c] %></span></button>
  <% } %>
</div>

<div class="digest-list list" id="digest-list">
<% for (const item of items) { %>
  <article class="digest-item" <%= metadataAttrs(item) %>
    data-source="<%- (item.source||'').toLowerCase() %>"
    data-domain="<%- (item.domain||'').toLowerCase() %>"
    data-tags="<%- (item.tags||[]).join(' ') %>"
    data-cats="<%- (item.categories||[]).join(' ') %>">

    <% if (item.image) { %>
    <a class="digest-thumb" href="<%- item.link %>" aria-label="Open article"><img src="<%- item.image %>" alt="" loading="lazy" referrerpolicy="no-referrer"></a>
    <% } %>

    <div class="digest-body">
      <h3 class="digest-title"><a href="<%- item.link %>" class="listing-title" target="_blank" rel="noopener"><%= item.title %></a></h3>

      <div class="digest-meta">
        <span class="digest-source"><i class="bi bi-newspaper"></i> <%= item.source %></span>
        <span class="digest-domain"><i class="bi bi-link-45deg"></i> <%= item.domain %></span>
        <span class="digest-date"><i class="bi bi-calendar3"></i> <%= item.date %></span>
      </div>

      <div class="digest-cats">
        <% for (const c of (item.categories||[])) { %><span class="digest-cat"><%= c %></span><% } %>
      </div>

      <div class="lbl tldr">TLDR</div>
      <% for (const p of (item.tldr||[])) { %><p><%= p %></p><% } %>

      <% if (item.mermaid) { %>
      <pre class="mermaid"><%- item.mermaid %></pre>
      <% } %>

      <div class="lbl why">Why read it</div>
      <p><%= item.why %></p>

      <div class="digest-tags">
        <% for (const t of (item.tags||[])) { %><span class="digest-tag">#<%= t %></span><% } %>
      </div>
    </div>
  </article>
<% } %>
</div>

<script>
(function(){
  var state = {source:'all', domain:'all', tag:'all', cat:'all'};
  var chips = document.querySelectorAll('.filter-chip[data-group], .cat-chip[data-group]');
  var items = Array.prototype.slice.call(document.querySelectorAll('#digest-list .digest-item'));
  var countEl = document.getElementById('digest-count');
  function apply(){
    var shown = 0;
    items.forEach(function(it){
      var ok = true;
      ['source','domain','tag','cat'].forEach(function(g){
        if(state[g]==='all') return;
        var attr;
        if(g==='cat') attr = it.getAttribute('data-cats')||'';
        else if(g==='tag') attr = it.getAttribute('data-tags')||'';
        else attr = it.getAttribute('data-'+g)||'';
        if(attr.indexOf(state[g].toLowerCase())===-1) ok = false;
      });
      it.style.display = ok ? '' : 'none';
      if(ok) shown++;
    });
    if(countEl) countEl.textContent = shown + ' / ' + items.length + ' shown';
    chips.forEach(function(ch){
      var g = ch.getAttribute('data-group');
      if(state[g]===ch.getAttribute('data-value')) ch.classList.add('active');
      else ch.classList.remove('active');
    });
  }
  chips.forEach(function(ch){
    ch.addEventListener('click', function(){
      var g = ch.getAttribute('data-group');
      var v = ch.getAttribute('data-value');
      if(state[g]===v && g!=='all'){ state[g]='all'; } else { state[g]=v; }
      apply();
    });
  });
  var clear = document.getElementById('digest-clear');
  if(clear) clear.addEventListener('click', function(){ state={source:'all',domain:'all',tag:'all',cat:'all'}; apply(); });
  apply();
})();
</script>
```
