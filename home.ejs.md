```{=html}
<%
const fmt = (d) => {
  if (!d) return '';
  const dt = new Date(d);
  return dt.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
};
%>
<div class="home-list">
  <% for (const item of items) { %>
  <article class="card day-card">
    <div class="card-body">
      <div class="day-meta">
        <span class="badge text-bg-light"><%= fmt(item.date) %></span>
        <% if (item.sources && item.sources.length) { %>
          <% for (const s of item.sources.slice(0,4)) { %><span class="badge text-bg-secondary"><%= s %></span><% } %>
          <% if (item.sources.length > 4) { %><span class="badge text-bg-secondary">+<%= item.sources.length - 4 %> more</span><% } %>
        <% } %>
      </div>
      <h3 class="day-title"><a class="link-primary" href="<%- item.outputHref %>"><%= item.title %></a></h3>
      <% if (item.description) { %><p class="day-desc"><%= item.description %></p><% } %>
      <a class="day-read" href="<%- item.outputHref %>">Read the edition →</a>
    </div>
  </article>
  <% } %>
</div>
```