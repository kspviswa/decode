```{=html}
<%
// Map a story's primary category to a sketchy-theme link color.
const linkColor = (cats) => {
  const c = (cats || [])[0] || '';
  if (['ai-security','security'].includes(c)) return 'link-danger';
  if (['5g','6g','5g-core','spectrum','slicing','tsn','ai-ran','network-intelligence','industrial'].includes(c)) return 'link-info';
  if (['digital-twin','world-models','simulation','generative'].includes(c)) return 'link-success';
  if (['m-and-a'].includes(c)) return 'link-warning';
  if (['ci-cd'].includes(c)) return 'link-secondary';
  return 'link-primary'; // ai-infra, llm, local-llm, open-weights, vision, vlm, openai, agents, edge-inference
};
%>
<% for (const item of items) { %>
  <article class="card story-card">
    <div class="card-body">
      <div class="story-head">
        <% if (item.source) { %><span class="badge text-bg-primary"><%= item.source %></span><% } %>
        <h3 class="story-headline"><a class="<%- linkColor(item.categories) %>" href="<%- item.link %>" target="_blank" rel="noopener"><%= item.title %></a></h3>
      </div>

      <div class="story-body">
        <% for (const p of (item.tldr||[])) { %><p><%= p %></p><% } %>

        <% if (item.mermaid) { %>
        <pre class="mermaid"><%- item.mermaid %></pre>
        <% } %>

        <p class="story-why"><span class="why-label">Why read it</span> <%= item.why %></p>
      </div>
    </div>
  </article>
<% } %>
```