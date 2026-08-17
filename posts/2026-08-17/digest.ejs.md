```{=html}
<% for (const item of items) { %>
  <article class="story">
    <h3 class="story-headline"><a href="<%- item.link %>" target="_blank" rel="noopener"><%= item.title %></a></h3>

    <% if (item.image) { %>
    <div class="story-image-wrapper">
      <img src="<%- item.image %>" alt="" loading="lazy" referrerpolicy="no-referrer">
    </div>
    <% } %>

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