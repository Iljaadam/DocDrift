"""Static assets for the fixed-fixture judge interface (no external requests)."""

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>DocDrift · Judge demo</title><link rel="stylesheet" href="/style.css"><script src="/app.js" defer></script></head>
<body><main><header><span class="eyebrow">DOC DRIFT / LIVE JUDGE DEMO</span><h1>Repair the example.<br>Keep the evidence.</h1>
<p class="intro">Run a fresh Nemotron repair of our owned documentation fixture, then verify its behavior in Nebius Sandboxes.</p></header>
<section class="panel"><div class="section-top"><h2>One fixed example</h2><span class="tag">Private access</span></div>
<p>An outdated example calls a renamed library method. The agent can inspect the fixture and try a small number of snippets. Independent checks verify the proposed repair and healthy neighboring examples.</p>
<p class="fine">This is an owned development fixture, not a held-out benchmark. You do not upload code, enter a prompt, or supply a provider key. Each completed job below is a fresh attempt; recorded evidence is labelled separately.</p>
<div class="action"><button id="run" type="button" disabled>Run fresh repair</button><span id="allowance" class="fine">Checking availability…</span></div>
<p id="availability" role="status" aria-live="polite">Connecting to the controller…</p><p id="error" class="error" role="alert"></p></section>
<section class="panel"><div class="section-top"><h2>Fresh attempts</h2><span class="fine">One worker at a time</span></div><div id="jobs"><p class="fine">No jobs loaded yet.</p></div></section>
<section class="panel"><div class="section-top"><h2>Saved demonstration · Oct 21</h2><span class="tag">Recorded evidence</span></div>
<p>Browse the saved Nemotron repair verified on Nebius Sandboxes on October 21, 2026. Opening these files makes no model or Sandbox calls and uses no fresh attempt.</p>
<p class="fine">This recorded run is separate from the fresh attempts above. Its sanitized presentation copies remain available when new runs are paused, unavailable, or expired.</p>
<div class="job-links"><a href="/saved/review.html" target="_blank" rel="noopener">Open recorded review</a><a href="/saved/evidence.zip">Download recorded evidence</a></div></section>
<footer>DocDrift · Nemotron on Nebius Token Factory · Verification on Nebius Sandboxes<br>Usage limits bound attempts; they do not establish a dollar spending ceiling. Evidence hashes check bytes, not origin or execution authenticity.</footer>
</main></body></html>"""

CSS = """*{box-sizing:border-box}body{margin:0;background:#f5f4ee;color:#192d35;font:16px/1.6 system-ui,-apple-system,sans-serif}main{max-width:980px;padding:64px 24px;margin:auto}.eyebrow{font-size:12px;font-weight:750;letter-spacing:.18em;color:#17624b}h1{font-size:clamp(36px,7vw,64px);line-height:1.08;letter-spacing:-.045em;margin:20px 0}h2{font-size:20px;margin:0}.intro{max-width:650px;font-size:20px;color:#49616b}.panel{border:1px solid #d4dcd4;border-radius:16px;background:#fff;padding:28px;margin:28px 0;box-shadow:0 5px 18px #183c3010}.section-top,.action{display:flex;gap:16px;align-items:center;justify-content:space-between}.tag{font-size:12px;color:#17624b;border:1px solid #b9d1c3;border-radius:30px;padding:4px 12px;white-space:nowrap}.fine,footer{font-size:13px;color:#5a6b70}button{font:inherit;font-weight:650;background:#17624b;color:#fff;border:0;border-radius:8px;padding:12px 20px;cursor:pointer}button:disabled{background:#c8d4ce;color:#53655d;cursor:not-allowed}a{color:#17624b;text-underline-offset:3px}a:focus,button:focus{outline:3px solid #d99c39;outline-offset:3px}.action{justify-content:flex-start;margin-top:24px;flex-wrap:wrap}#availability{font-size:14px;color:#49616b;margin-bottom:0}.error{color:#a02e24}.job{padding:20px 0;border-top:1px solid #e3e7e1}.job:first-child{border-top:0}.job-top{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}.job-id{font-family:ui-monospace,monospace;font-size:13px;overflow-wrap:anywhere}.job p{margin:6px 0}.job-links{display:flex;gap:20px;flex-wrap:wrap}.status{font-size:13px;font-weight:700;color:#17624b}footer{margin-top:36px;line-height:1.8}@media(max-width:600px){main{padding:32px 16px}.panel{padding:20px}.section-top{align-items:flex-start;flex-direction:column;gap:8px}}"""

JS = """'use strict';
const button = document.getElementById('run');
const error = document.getElementById('error');
let busy = false;
let pendingKey = null;
const descriptions = {
  paused: 'Fresh runs are paused by the operator. Saved results remain available.',
  expired: 'The judging run window has ended. Saved results remain available.',
  allowance_exhausted: 'The shared run allowance has been used.',
  budget_exhausted: 'The shared run allowance has been used.',
  queue_full: 'The queue is full. Please wait for an active attempt to finish.',
  funding_unconfirmed: 'Fresh runs are waiting for confirmed credit coverage.',
  not_ready: 'Fresh runs have not been activated yet.',
  judging_expired: 'The judging run window has ended. Saved results remain available.',
  admission_paused: 'Fresh runs are paused for operator review. Saved results remain available.',
  activation_required: 'Fresh runs have not been activated yet.',
  worker_unavailable: 'The worker is unavailable. Please try again later.',
  attempt_limit_reached: 'The shared run allowance has been used.',
  judge_authorization_changed: 'The operator must review the deployment authorization.'
};
function node(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined && content !== null) element.textContent = String(content);
  return element;
}
function renderJobs(jobs) {
  const target = document.getElementById('jobs');
  target.replaceChildren();
  if (!jobs.length) { target.append(node('p', 'fine', 'No fresh attempts yet.')); return; }
  for (const job of jobs) {
    const article = node('article', 'job');
    const top = node('div', 'job-top');
    top.append(node('span', 'job-id', job.id), node('span', 'status', job.status));
    article.append(top);
    const details = [];
    if (job.created_at) details.push('Started ' + job.created_at);
    if (job.outcome) details.push('Result: ' + job.outcome);
    details.push(String(job.model_calls || 0) + ' model calls');
    details.push(String(job.guest_operations || 0) + ' guest operations');
    article.append(node('p', 'fine', details.join(' · ')));
    if (job.error_code) article.append(node('p', 'error', 'Stopped: ' + job.error_code));
    if (job.status === 'completed' && job.has_artifacts && /^[a-f0-9]{32}$/.test(job.id)) {
      const links = node('div', 'job-links');
      for (const [name, label] of [['review.html', 'Open saved review'], ['evidence.zip', 'Download evidence']]) {
        const link = node('a', '', label);
        link.href = '/jobs/' + job.id + '/' + name;
        if (name === 'review.html') { link.target = '_blank'; link.rel = 'noopener'; }
        links.append(link);
      }
      article.append(links);
    }
    target.append(article);
  }
}
async function refresh() {
  try {
    const response = await fetch('/api/status', {cache: 'no-store', credentials: 'same-origin'});
    if (!response.ok) throw new Error('Status unavailable. Reload and check your access password.');
    const result = await response.json();
    const state = result.summary;
    const limit = Number.isInteger(state.attempts_limit) ? state.attempts_limit : 20;
    const remaining = Number.isInteger(state.attempts_remaining) ? state.attempts_remaining : null;
    const reserved = Number.isInteger(state.held_out_reserved_attempts) ? state.held_out_reserved_attempts : 0;
    document.getElementById('allowance').textContent = (remaining === null ? 'Shared allowance: ' + limit + ' fresh attempts total' : remaining + ' fresh judge attempts remaining') + (reserved ? ' · ' + reserved + ' reserved for held-out evaluation' : '');
    document.getElementById('availability').textContent = state.live_ready ? 'Ready. A fresh attempt may take a few minutes.' : (descriptions[state.admission_reason] || 'Fresh runs are not available. Saved results remain available.');
    button.disabled = busy || state.live_ready !== true;
    renderJobs(result.jobs || []);
  } catch (failure) {
    button.disabled = true;
    document.getElementById('availability').textContent = failure.message;
  }
}
button.addEventListener('click', async () => {
  if (busy) return;
  busy = true; button.disabled = true; error.textContent = '';
  if (!pendingKey) pendingKey = crypto.randomUUID();
  try {
    const response = await fetch('/api/jobs', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'Idempotency-Key': pendingKey, 'X-DocDrift-Request': '1'}, body: '{}'});
    const result = await response.json();
    if (!response.ok) {
      if (response.status < 500) pendingKey = null;
      throw new Error(descriptions[result.error] || result.message || 'The attempt could not be admitted.');
    }
    pendingKey = null;
  } catch (failure) { error.textContent = failure.message + (pendingKey ? ' Retry uses the same request ID to avoid a duplicate attempt.' : ''); }
  finally { busy = false; await refresh(); }
});
refresh();
setInterval(refresh, 4000);
"""
