```{=html}
<%
// Newspaper sections — each is a native sketchy .card with a colored
// .text-bg-* header. Stories bucket into sections by primary category.
const sections = [
  { key: 'networks',  name: 'Networks · 5G & 6G',      color: 'info',     cats: ['5g','6g','5g-core','spectrum','slicing','tsn','ai-ran','network-intelligence','industrial'] },
  { key: 'security',  name: 'Security',                color: 'danger',   cats: ['ai-security','security'] },
  { key: 'ai',        name: 'AI & Models',             color: 'success',  cats: ['ai-infra','llm','open-weights','local-llm','benchmarks','vision','vlm','openai','ai-agents','llm-agents','edge-inference','ci-cd'] },
  { key: 'business',  name: 'Business & Funding',      color: 'warning',  cats: ['m-and-a'] },
  { key: 'research',  name: 'Research & World Models', color: 'secondary',cats: ['digital-twin','world-models','generative','simulation','agents'] },
];
const bucket = (item) => {
  const c = item.categories || [];
  for (const s of sections) if (c.some(x => s.cats.includes(x))) return s.key;
  return 'research';
};
const grouped = {};
for (const it of items) { (grouped[bucket(it)] = grouped[bucket(it)] || []).push(it); }
%>
<% for (const s of sections) { const list = grouped[s.key] || []; if (!list.length) continue; %>
<section class="sec-card">
  <div class="card sec-<%- s.key %>">
    <div class="card-header text-bg-<%- s.color %>"><%= s.name %></div>
    <div class="card-body">
      <% for (const item of list) { %>
      <article class="story">
        <div class="story-head">
          <% if (item.source) { %><span class="badge text-bg-primary"><%= item.source %></span><% } %>
          <h3 class="story-headline"><a class="link-<%- s.color %>" href="<%- item.link %>" target="_blank" rel="noopener"><%= item.title %></a></h3>
        </div>
        <div class="story-body">
          <% for (const p of (item.tldr||[])) { %><p><%= p %></p><% } %>
          <% if (item.mermaid) { %>
          <pre class="mermaid"><%- item.mermaid %></pre>
          <% } %>
        </div>
        <div class="alert alert-<%- s.color %> story-why" role="alert">
          <span class="why-label">Why read it</span> <%= item.why %>
        </div>
      </article>
      <% } %>
    </div>
  </div>
</section>
<% } %>
```