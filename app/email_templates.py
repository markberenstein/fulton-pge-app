{% extends "base.html" %}
{% block content %}
<div class="card">
  <h2>Reimbursement email drafts</h2>
  <p class="muted">Copy each into a Buildium message to the tenant. Attach the PDF report below to each.</p>
  <a class="btn" href="{{ url_for('report', run_id=run_id) }}" target="_blank" rel="noopener">Download PDF report to attach</a>
</div>

{% for d in drafts %}
<div class="card">
  <h3>{{ d.tenant }} <span class="muted">— {{ d.amount }}</span></h3>
  <p class="muted">{{ d.address }}</p>
  <label>Subject</label>
  <input type="text" readonly value="{{ d.subject }}" id="subject-{{ loop.index }}">
  <label>Body</label>
  <textarea readonly rows="10" style="width:100%;padding:8px;border:1px solid #ccc;border-radius:4px;font-family:inherit;" id="body-{{ loop.index }}">{{ d.body }}</textarea>
  <button type="button" onclick="copyField('subject-{{ loop.index }}')">Copy subject</button>
  <button type="button" onclick="copyField('body-{{ loop.index }}')">Copy body</button>
</div>
{% endfor %}

<p><a href="{{ url_for('dashboard', run_id=run_id) }}">&larr; Back to dashboard</a></p>

<script>
function copyField(id) {
  const el = document.getElementById(id);
  el.select();
  el.setSelectionRange(0, 99999);
  navigator.clipboard.writeText(el.value);
}
</script>
{% endblock %}
