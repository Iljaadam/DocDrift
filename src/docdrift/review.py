"""Render saved run evidence as a portable, read-only HTML review."""

from __future__ import annotations

import difflib
import json
from html import escape
from pathlib import Path


_ARTIFACT_LIMIT = 512 * 1024


def _escape(value: object) -> str:
    return escape(str(value), quote=True)


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _records(value: object) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _read(root: Path, name: str, notices: list[str]) -> str | None:
    """Read only fixed artifacts inside the run, without following escaped links."""
    path = root / name
    try:
        if not path.resolve().is_relative_to(root.resolve()):
            notices.append(f'{name}: artifact points outside this run; omitted.')
            return None
        if not path.is_file():
            return None
        with path.open('rb') as stream:
            data = stream.read(_ARTIFACT_LIMIT + 1)
        if len(data) > _ARTIFACT_LIMIT:
            notices.append(f'{name}: review display limited to 512 KiB; consult the evidence archive.')
        return data[:_ARTIFACT_LIMIT].decode('utf-8', errors='replace')
    except OSError:
        notices.append(f'{name}: could not read saved artifact.')
        return None


def _json(root: Path, name: str, notices: list[str]) -> dict:
    content = _read(root, name, notices)
    if content is None:
        return {}
    try:
        value = json.loads(content)
    except ValueError:
        notices.append(f'{name}: saved JSON is unreadable; related details are unavailable.')
        return {}
    if not isinstance(value, dict):
        notices.append(f'{name}: expected a JSON object; related details are unavailable.')
        return {}
    return value


def _pre(value: object, *, class_name: str = '') -> str:
    return f'<pre class="{class_name}"><code>{_escape(value)}</code></pre>'


def _facts(items: list[tuple[str, object]]) -> str:
    return '<dl class="facts">' + ''.join(
        f'<div><dt>{_escape(key)}</dt><dd>{_escape(value if value is not None else "Not recorded")}</dd></div>'
        for key, value in items
    ) + '</dl>'


def _flag(value: object) -> str:
    label, tone = ('Passed', 'good') if value is True else ('Failed', 'bad') if value is False else ('Not recorded', 'muted')
    return f'<span class="pill {tone}">{label}</span>'


def _section(identifier: str, title: str, body: str) -> str:
    return f'<section id="{identifier}"><h2>{title}</h2>{body}</section>'


def _diff(content: str) -> str:
    lines = []
    for line in content.splitlines():
        tone = 'added' if line.startswith('+') and not line.startswith('+++') else 'removed' if line.startswith('-') and not line.startswith('---') else 'context'
        lines.append(f'<span class="{tone}">{_escape(line)}</span>')
    return '<pre class="diff"><code>' + ''.join(lines) + '</code></pre>'


def _operation(record: dict, ordinal: int) -> str:
    result, checks = _mapping(record.get('result')), _mapping(record.get('checks'))
    phase = record.get('phase', 'Unknown phase')
    identity = record.get('case_id') or record.get('operation_id') or result.get('operation_id') or 'Identity not recorded'
    facts = _facts([
        ('Operation ID', result.get('operation_id') or record.get('operation_id')),
        ('Image ID', result.get('image_id')),
        ('State', result.get('state', record.get('state'))),
        ('Exit code', result.get('exit_code')),
        ('Elapsed seconds', result.get('elapsed_seconds')),
        ('Timed out', result.get('timed_out')),
    ])
    errors = checks.get('errors') or checks.get('observable_errors') or []
    rows = ''.join(f'<li>{_escape(item)}</li>' for item in errors if isinstance(item, str))
    coverage = checks.get('coverage', [])
    detail = facts + ('<ul class="errors">' + rows + '</ul>' if rows else '')
    if coverage:
        detail += '<p>Recorded checks: ' + _escape(', '.join(str(item) for item in coverage)) + '.</p>'
    if 'known_repair_ast_match' in checks:
        detail += '<p>Known repair AST match (informational): ' + _escape(checks['known_repair_ast_match']) + '.</p>'
    for stream in ['stdout', 'stderr']:
        truncated = result.get(f'{stream}_truncated') is True
        detail += f'<h4>{stream}' + (' · capture truncated' if truncated else '') + '</h4>'
        detail += _pre(result.get(stream) or '(empty or not recorded)')
    return (
        f'<details class="operation" id="operation-{ordinal}"><summary>'
        f'<span>{_escape(phase)} <small>{_escape(identity)}</small></span>'
        f'<span class="check-label">Execution {_flag(checks.get("execution_passed"))} '
        f'Output {_flag(checks.get("observable_passed"))} Behavior {_flag(checks.get("behavior_passed"))}</span>'
        f'</summary><div class="operation-body">{detail}</div></details>'
    )


def render_review(report: dict, run_root: Path, *, archive_available: bool | None = None) -> str:
    """Return self-contained HTML from saved evidence; never run or change anything.

    ``run_root`` is the directory containing report.json and evidence.zip. Links
    remain relative to that directory and to the same files in an extracted ZIP.
    A saved verdict is displayed with its limits; this renderer is not a verifier.
    An exporter may declare its new archive available without changing the saved
    run's evidence-export outcome or verification verdict.
    """
    notices: list[str] = []
    root = Path(run_root)
    ledger = _json(root, 'ledger.json', notices)
    metadata = _mapping(ledger.get('metadata'))
    repair = _json(root, 'repair.json', notices)
    profile = _json(root, 'profile/profile.json', notices)
    original = _read(root, 'original.py', notices)
    repaired = _read(root, 'repaired.py', notices)
    proposal = _read(root, 'replacement.py', notices)
    patch = _read(root, 'repair.patch', notices)
    results = _records(report.get('results'))
    provenance = _mapping(report.get('provenance')) or _mapping(metadata.get('provenance'))
    environment = _mapping(report.get('environment'))
    usage = _mapping(report.get('usage'))
    inference = _mapping(repair.get('usage')) or _mapping(metadata.get('inference_usage'))
    source = report.get('repair_source', metadata.get('repair_source', 'Not recorded'))
    source_text = str(source)
    if source_text.startswith('synthetic_') or repair.get('live_inference') is False:
        repair_label = 'Synthetic model replay'
    elif source_text.startswith('model_'):
        repair_label = 'Live model repair'
    elif source == 'supplied_manual_patch':
        repair_label = 'Supplied manual patch'
    else:
        repair_label = 'Repair source not established'
    adapter = report.get('adapter', metadata.get('adapter', 'Not recorded'))
    local = adapter == 'local_docker'
    runtime = 'Local Docker' if local else str(adapter)
    profile_name = profile.get('name', 'Profile name not recorded')
    owned = str(profile_name).startswith('owned-')
    fixture_label = 'Owned fixture' if owned else 'Repository snapshot; ownership not recorded'
    status = report.get('status', 'incomplete')
    verdict = report.get('repair_verdict', 'unattempted')
    verified = status == 'completed' and verdict == 'behavior_verified' and report.get('protected_hashes_preserved') is not False and report.get('evidence_exported') is not False
    if verified:
        headline, tone = 'Behavior verified', 'good'
    elif status == 'rejected' or verdict == 'rejected':
        headline, tone = 'Repair rejected', 'bad'
    elif status != 'completed':
        headline, tone = 'Verification incomplete', 'warn'
    elif verdict == 'execution_passed':
        headline, tone = 'Execution passed; behavior unverified', 'warn'
    else:
        headline, tone = 'No verified repair', 'muted'
    final = [item for item in results if item.get('phase') in {'final_repaired', 'healthy_regression'}]
    executed = sum(_mapping(item.get('checks')).get('execution_passed') is True for item in final)
    behavior = sum(_mapping(item.get('checks')).get('behavior_passed') is True for item in final)
    baseline = next((item for item in results if item.get('phase') == 'baseline_target'), None)
    if original is None and baseline:
        example = next((item for item in _records(report.get('examples')) if item.get('id') == baseline.get('example_id')), {})
        original = example.get('code')
    if not patch and original is not None and repaired is not None:
        patch = ''.join(difflib.unified_diff(original.splitlines(keepends=True), repaired.splitlines(keepends=True), fromfile='original.py', tofile='repaired.py'))

    if archive_available is None:
        archive_available = report.get('evidence_exported') is True or (report.get('evidence_exported') is not False and (root / 'evidence.zip').is_file())
    download = '<a class="button" href="evidence.zip" download>Download evidence ZIP <span aria-hidden="true">↗</span></a>' if archive_available else '<span class="archive-unavailable">Evidence archive unavailable</span>'
    run_id = report.get('run_id', 'Not recorded')
    header = f'''<header><div class="brand"><span class="brand-mark" aria-hidden="true">D/</span> DocDrift <span>evidence review</span></div>
<div class="hero"><div><p class="eyebrow">{_escape(fixture_label)} · {_escape(runtime)}</p><h1>{headline}</h1>
<p class="subtitle">One documentation example. A frozen contract. A reviewable result.</p></div>{download}</div>
<div class="run-line">Run <code>{_escape(run_id)}</code> <span class="pill {tone}">{_escape(status)}</span></div></header>'''
    summary = '<div class="metrics">' + ''.join(
        f'<article><p>{label}</p><strong>{_escape(value)}</strong><small>{_escape(note)}</small></article>'
        for label, value, note in [
            ('Execution checks', f'{executed} / {len(final)}' if final else 'Not run', 'Recorded final target + regression checks'),
            ('Behavior checks', f'{behavior} / {len(final)}' if final else 'Not run', 'Recorded final checks; see coverage limits'),
            ('Repair source', repair_label, source_text),
            ('Model calls', usage.get('inference_calls', inference.get('model_calls', 'Not recorded')), 'Token usage below'),
        ]
    ) + '</div>'
    findings = _facts([('Saved status', status), ('Saved repair verdict', verdict), ('Diagnosis', report.get('diagnosis')), ('Protected hashes preserved', report.get('protected_hashes_preserved'))])
    if report.get('finding'):
        findings += '<p class="finding">' + _escape(report['finding']) + '</p>'
    if not verified:
        findings += '<p>The saved run does not establish a completed behavior-verified repair.</p>'
    summary += _section('outcome', 'Recorded outcome', findings)

    if baseline:
        initial = _mapping(baseline.get('result'))
        error = initial.get('stderr') or '\n'.join(str(value) for value in _mapping(baseline.get('checks')).get('observable_errors', [])) or 'No original error was recorded.'
        original_failure = _facts([('Failure kind', report.get('original_failure_kind')), ('Original exit code', initial.get('exit_code')), ('Original operation ID', initial.get('operation_id'))]) + _pre(error)
    else:
        original_failure = '<p>The original failure was not captured in this report.</p>'
    original_failure += '<p>Reproduction phases and all captured logs appear in the operation details below.</p>'

    code = '<div class="code-pair"><div><h3>Original example</h3>'
    code += _pre(original) if original is not None else '<p class="empty">Original snippet unavailable.</p>'
    code += '</div><div><h3>' + ('Repaired example' if repaired is not None else 'Proposed example') + '</h3>'
    code += _pre(repaired if repaired is not None else proposal) if repaired is not None or proposal is not None else '<p class="empty">No candidate snippet was saved.</p>'
    code += '</div></div><h3>Documentation diff</h3>'
    code += _diff(patch) if patch else '<p class="empty">No patch was saved. The candidate may have been rejected before a documentation change.</p>'

    preservation = _mapping(report.get('healthy_preservation'))
    regression_records = [record for record in results if record.get('phase') == 'healthy_regression']
    regression = _facts([('Required healthy examples', preservation.get('required_examples')), ('Required healthy cases', preservation.get('required_cases')), ('Recorded regression cases', len(regression_records)), ('All declared regressions passed', preservation.get('all_passed'))])
    if not preservation:
        regression += '<p>Healthy preservation was not established in the saved report.</p>'

    provenance_body = _facts([
        ('Source classification', fixture_label), ('Frozen profile', profile_name), ('Snapshot kind', provenance.get('kind')),
        ('Origin', provenance.get('origin')), ('Pinned Git commit', provenance.get('commit')),
        ('Snapshot archive SHA-256', provenance.get('archive_sha256')), ('Recorded execution adapter', adapter),
        ('Provider qualification', report.get('provider_qualification')), ('Image reference', environment.get('image', metadata.get('image'))),
        ('Immutable image ID', environment.get('image_id')), ('Python', environment.get('python_version')),
        ('Execution network', environment.get('network')), ('Created at', ledger.get('created_at')),
    ])
    if local:
        provenance_body += '<p class="qualification">Execution used local Docker. This run does not establish Nebius Sandbox access or competition eligibility.</p>'
    else:
        provenance_body += '<p class="qualification">Execution and provider qualification are shown as recorded; this review does not probe provider access.</p>'
    if owned:
        provenance_body += '<p>This is a DocDrift-owned fixture, not evidence of a repair to an independent public project.</p>'
    hash_groups = [('Snapshot file hashes', provenance.get('files')), ('Frozen profile hashes', report.get('frozen_profile_hashes')), ('Patched file hashes', report.get('patched_file_hashes'))]
    for title, values in hash_groups:
        if isinstance(values, dict) and values:
            provenance_body += '<details><summary>' + title + '</summary>' + _facts(list(values.items())) + '</details>'

    token_total = inference.get('prompt_tokens', 0) + inference.get('completion_tokens', 0) if all(type(inference.get(key)) is int for key in ['prompt_tokens', 'completion_tokens']) else None
    usage_body = _facts([
        ('Model', repair.get('model', metadata.get('model'))), ('Strategy', repair.get('strategy')),
        ('Repair source', source), ('Live inference recorded', repair.get('live_inference')),
        ('Inference calls', usage.get('inference_calls', inference.get('model_calls'))), ('Prompt tokens', inference.get('prompt_tokens')),
        ('Completion tokens', inference.get('completion_tokens')), ('Total recorded tokens', token_total),
        ('Model exploration snippet runs', inference.get('snippet_runs')), ('Final verification operations', usage.get('compute_operations')),
        ('Calls marked paid in the ledger', usage.get('paid_calls')),
    ])
    usage_body += '<p>Tokens and calls are recorded usage, not a dollar estimate or a statement about the current account balance. Calls marked paid identify live inference requests against account credits; they do not report personal spending.</p>'
    if usage.get('operation_count_scope'):
        usage_body += '<p>' + _escape(usage['operation_count_scope']) + '.</p>'

    operation_body = '<p>Expand a phase for its operation and image IDs, check findings, stdout, and stderr. Execution success and behavior acceptance are separate results.</p>'
    operation_body += ''.join(_operation(item, index) for index, item in enumerate(results)) or '<p class="empty">No completed check records were saved.</p>'
    seen = {str(_mapping(item.get('result')).get('operation_id')) for item in results}
    pending = [item for item in _records(ledger.get('operations')) if str(item.get('operation_id')) not in seen]
    if pending:
        operation_body += '<h3>Other accepted operations</h3><p>These ledger entries have no corresponding check record in the report.</p>'
        operation_body += ''.join(_operation(item, len(results) + index) for index, item in enumerate(pending))

    limits = '<p>Acceptance covers only declared inputs and recorded checks. It is not a proof for every input or protection against deliberately obfuscated code. The static must-flow check trusts straight-line top-level code and can reject legitimate complex rewrites.</p>'
    limits += '<p>Current behavior checks compare frozen JSON outputs, require the declared API call, and check that its result reaches printed output. Inspect each operation’s recorded coverage when reviewing historical runs; a known-repair AST match is informational.</p>'
    if report.get('coverage_note'):
        limits += '<details open><summary>Saved coverage note</summary><p>' + _escape(report['coverage_note']) + '</p></details>'
    if notices:
        limits += '<h3>Artifact notices</h3><ul>' + ''.join('<li>' + _escape(notice) + '</li>' for notice in notices) + '</ul>'
    links = [('report.json', 'Machine-readable report'), ('ledger.json', 'Run ledger'), ('commands.json', 'Recorded commands'), ('manifest.json', 'SHA-256 manifest')]
    files = '<p>The archive contains saved source, checks, patch, logs, and a SHA-256 manifest for its listed members. This HTML is a view of that evidence, not a fresh verification.</p><div class="file-links">'
    files += ''.join(f'<a href="{name}">{label}</a>' for name, label in links)
    files += '</div>'
    sections = summary + _section('failure', 'Original failure', original_failure) + _section('patch', 'Proposed documentation repair', code) + _section('regressions', 'Healthy example preservation', regression) + _section('provenance', 'Provenance & execution', provenance_body) + _section('usage', 'Model & usage', usage_body) + _section('operations', 'Operations & logs', operation_body) + _section('limits', 'Coverage & limitations', limits) + _section('evidence', 'Inspect the evidence', files)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DocDrift review · {_escape(run_id)}</title><style>{_CSS}</style></head><body>
<div class="shell">{header}<nav aria-label="Review sections"><a href="#outcome">Outcome</a><a href="#patch">Repair</a><a href="#provenance">Provenance</a><a href="#operations">Logs</a><a href="#limits">Limits</a></nav><main>{sections}</main>
<footer>DocDrift · frozen inputs, bounded repair, independent checks · review generated from saved evidence</footer></div></body></html>'''


_CSS = '''
:root{color-scheme:light;--ink:#162b38;--muted:#586d77;--line:#dbe3e5;--paper:#fff;--green:#17674b;--mint:#e7f2ec;--red:#a33635;--amber:#82530d}
*{box-sizing:border-box}body{margin:0;background:#f3f5f4;color:var(--ink);font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.shell{max-width:1200px;margin:auto;padding:38px 36px}header{padding:0 0 25px;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:10px;font-size:20px;font-weight:750;letter-spacing:-.5px}.brand>span:last-child{font-size:13px;color:var(--muted);font-weight:450;letter-spacing:0}.brand-mark{background:var(--ink);color:#fff;border-radius:9px;width:38px;height:38px;text-align:center;line-height:38px}.hero{display:flex;align-items:center;justify-content:space-between;gap:26px;margin-top:35px}.eyebrow{text-transform:uppercase;letter-spacing:1.5px;font-size:11px;font-weight:700;color:var(--green)}h1{font-size:clamp(28px,4vw,44px);line-height:1.16;letter-spacing:-1.6px;margin:8px 0 13px}.subtitle{color:var(--muted);margin:0}.button{display:inline-flex;gap:20px;align-items:center;white-space:nowrap;background:var(--ink);color:white;padding:12px 19px;border-radius:7px;text-decoration:none;font-size:13px;font-weight:650}.run-line{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:27px;font-size:12px;color:var(--muted)}.pill{display:inline-block;white-space:nowrap;font-size:11px;font-weight:650;border-radius:5px;padding:2px 7px}.good{color:var(--green);background:var(--mint)}.bad{color:var(--red);background:#fbeceb}.warn{color:var(--amber);background:#fff0d7}.muted{color:var(--muted);background:#e9edee}nav{display:flex;flex-wrap:wrap;gap:24px;padding:16px 0 23px;font-size:13px}a{color:var(--green);text-underline-offset:4px}nav a{text-decoration:none;color:var(--muted)}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px}.metrics article{background:var(--paper);border:1px solid var(--line);border-radius:9px;padding:17px 19px}.metrics p{font-size:12px;color:var(--muted);margin:0 0 8px}.metrics strong{font-size:22px;line-height:1.3;display:block;letter-spacing:-.5px;overflow-wrap:anywhere}.metrics small{display:block;font-size:11px;color:var(--muted);margin-top:9px}section{background:var(--paper);border:1px solid var(--line);border-radius:9px;margin-top:20px;padding:25px 27px;scroll-margin-top:15px}h2{font-size:18px;letter-spacing:-.4px;margin:0 0 20px}h3{font-size:13px;margin:18px 0 10px}h4{font-size:11px;text-transform:uppercase;color:var(--muted);letter-spacing:1px;margin:18px 0 7px}p{margin:12px 0;color:var(--muted)}p:last-child{margin-bottom:0}.facts{margin:0}.facts>div{display:grid;grid-template-columns:210px minmax(0,1fr);gap:18px;padding:8px 0;border-bottom:1px solid #eef1f1;font-size:12px}.facts>div:last-child{border-bottom:0}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.finding,.qualification{border-left:3px solid #d3a342;padding:10px 14px;background:#fff9ed;color:#654c26;font-size:13px}.code-pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.code-pair h3{margin-top:0}pre{font:12px/1.75 ui-monospace,SFMono-Regular,Consolas,monospace;background:#f4f6f6;border:1px solid #e4e9e9;border-radius:6px;padding:15px 17px;margin:0;overflow:auto;tab-size:4}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}pre code{font:inherit;white-space:pre}.diff{padding:12px 0}.diff span{display:block;white-space:pre;padding:0 17px;min-height:1.75em}.diff .added{background:#e9f6ed;color:#205f3c}.diff .removed{background:#fcefee;color:#9b3c38}.diff .context{color:#63757b}details{margin-top:12px;border:1px solid var(--line);border-radius:6px;overflow:hidden}summary{padding:12px 15px;cursor:pointer;font-size:12px;font-weight:600}details>.facts,details>p{margin:10px 16px}summary small{font-weight:400;color:var(--muted);margin-left:8px;overflow-wrap:anywhere}.operation summary{display:flex;justify-content:space-between;align-items:center;gap:12px}.operation summary:before{content:'+';font-size:17px;color:var(--muted)}.operation[open] summary:before{content:'−'}.operation summary>span:first-of-type{flex:1;overflow-wrap:anywhere}.check-label{font-size:10px;font-weight:400;color:var(--muted)}.operation-body{padding:0 18px 18px;border-top:1px solid var(--line)}.errors{font-size:12px;color:var(--red);padding-left:20px}.operation-body p{font-size:12px}.file-links{display:flex;flex-wrap:wrap;gap:10px 24px;margin-top:20px;font-size:12px}.empty,.archive-unavailable{font-size:13px;color:var(--muted)}footer{font-size:11px;text-align:center;color:var(--muted);padding:24px}a:focus-visible,summary:focus-visible{outline:3px solid #429a79;outline-offset:3px}
@media(max-width:850px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.code-pair{grid-template-columns:1fr}.operation summary{flex-wrap:wrap}.check-label{width:100%}.hero{align-items:flex-start;flex-direction:column}.facts>div{grid-template-columns:160px minmax(0,1fr)}}
@media(max-width:520px){.shell{padding:20px 14px}section{padding:19px 16px}.metrics{gap:9px}.metrics article{padding:14px}.metrics strong{font-size:18px}.facts>div{grid-template-columns:1fr;gap:2px}.brand>span:last-child{font-size:11px}nav{gap:18px}.operation summary small{display:block;margin-left:0}}
@media print{body{background:white}.shell{max-width:none;padding:0}nav,.button{display:none}section,.metrics article{break-inside:avoid}details{break-inside:avoid}pre{white-space:pre-wrap}a{color:inherit}footer{padding:12px}}
'''
