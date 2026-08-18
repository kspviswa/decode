```{=html}
<% for (const item of items) { %>
  <article class="story">
    <div class="story-head">
      <% if (item.source) { %><span class="badge text-bg-primary"><%= item.source %></span><% } %>
      <h3 class="story-headline"><a href="<%- item.link %>" target="_blank" rel="noopener"><%= item.title %></a></h3>
    </div>

    <div class="story-body">
      <% for (const p of (item.tldr||[])) { %><p><%= p %></p><% } %>

      <% if (item.mermaid) { %>
      <pre class="mermaid"><%- item.mermaid %></pre>
      <% } %>

      <p class="story-why"><span class="why-label">Why read it</span> <%= item.why %></p>
    </div>
  </article>
<% } %>
```