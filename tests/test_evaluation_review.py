import copy
from html.parser import HTMLParser

import pytest

from docdrift.review import render_evaluation_review


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.links = []
        self.words = []
        self.tables = {}
        self.current_table = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append(tag)
        if tag == 'a':
            self.links.append(attributes.get('href'))
        if tag == 'table':
            self.current_table = attributes.get('id')
            self.tables[self.current_table] = []

    def handle_endtag(self, tag):
        if tag == 'table':
            self.current_table = None

    def handle_data(self, data):
        self.words.append(data)
        if self.current_table is not None:
            self.tables[self.current_table].append(data)

    @property
    def text(self):
        return ''.join(self.words)

    def table_text(self, identifier):
        return ''.join(self.tables[identifier])


def saved_report():
    return {
        'kind': 'docdrift_evaluation',
        'evidence': 'live_inference',
        'model': 'nvidia/nemotron-3-super-120b-a12b',
        'execution_backend': 'LocalDockerAdapter',
        'include_held_out': False,
        'strategies': ['execution_only', 'one_shot', 'agent'],
        'compute_operations': 54,
        'summary': {
            name: {
                'broken_cases': 2, 'drift_detected': 2,
                'behavior_verified_repairs': 0 if name == 'execution_only' else 2,
                'healthy_cases': 2, 'false_drift_reports': 0,
                'unsupported_or_setup_cases': 4, 'correct_abstentions': 4,
                'model_calls': 0 if name == 'execution_only' else 2,
                'prompt_tokens': 0 if name == 'execution_only' else 100,
                'completion_tokens': 0 if name == 'execution_only' else 50,
                'agent_snippet_runs': 1 if name == 'agent' else 0,
            }
            for name in ['execution_only', 'one_shot', 'agent']
        },
        'rows': [
            {'case': 'renamed_method_broken', 'kind': 'broken', 'split': 'development', 'label': 'Owned fixture',
             'strategy': 'agent', 'scored': True, 'detected': True, 'outcome': 'behavior_verified',
             'run_id': 'abc123', 'run_status': 'completed', 'verified': True},
            {'case': 'healthy_neighbor', 'kind': 'healthy', 'split': 'development', 'label': 'Owned fixture',
             'strategy': 'agent', 'scored': True, 'detected': False, 'outcome': 'no_failure_found'},
            {'case': 'upstream_candidate', 'kind': 'public_reference', 'split': 'reference', 'label': 'Public candidate',
             'strategy': 'agent', 'scored': False, 'outcome': 'pending_reproduction'},
        ],
    }


def test_comparison_preserves_recorded_counts_usage_and_historical_scope():
    report = saved_report()
    before = copy.deepcopy(report)
    page = Page(render_evaluation_review(report))
    for expected in ['Live inference recorded', 'LocalDockerAdapter', 'local Docker', 'nvidia/nemotron',
                     'Excluded from this saved report', 'Historical inventory unspecified',
                     'Nebius Sandbox execution', 'Execution-only, healthy, unsupported and setup rows may use no model calls']:
        assert expected in page.text
    summary = page.table_text('strategy-results')
    for expected in ['execution_only', 'one_shot', 'agent', '2 / 2', '0 / 2', '4 / 4', '150 (100 + 50)', 'Not attempted']:
        assert expected in summary
    assert 'Scored cases2' in page.text
    assert 'Model calls4' in page.text
    assert 'renamed_method_broken' in page.table_text('scored-cases')
    assert 'Status: completed' in page.table_text('scored-cases')
    assert all(link.startswith('#') for link in page.links)
    assert report == before


def test_synthetic_verdicts_remain_explicitly_non_model_evidence():
    report = saved_report()
    report.update(evidence='synthetic_not_evidence', execution_backend='ContractAdapter')
    page = Page(render_evaluation_review(report))
    assert 'Synthetic rehearsal; not model evidence' in page.text
    assert 'Recorded repair verdicts are not evidence of live model performance' in page.text
    assert 'ContractAdapter' in page.text
    assert 'does not probe provider access or establish that a contract double executed code' in page.text
    assert 'behavior_verified' in page.table_text('scored-cases')
    assert 'Live inference recorded' not in page.text


def test_no_model_and_held_out_scope_do_not_imply_model_repairs():
    report = saved_report()
    report.update(evidence='no_model', model=None, include_held_out=True, strategies=['execution_only'])
    report['summary'] = {'execution_only': report['summary']['execution_only']}
    report['rows'] = []
    page = Page(render_evaluation_review(report))
    assert 'No model used' in page.text
    assert 'Included in this saved report' in page.text
    assert 'detection and abstention rather than model-generated repairs' in page.text
    assert 'Not attempted' in page.table_text('strategy-results')
    assert 'ModelNot recorded' in page.text


def test_pending_and_reference_rows_never_enter_the_scored_case_table():
    report = saved_report()
    # Even a contradictory flag must not promote pending public references.
    report['rows'][2]['scored'] = True
    report['rows'] += [
        {'case': 'unreproduced_owned', 'kind': 'broken', 'split': 'development', 'scored': True,
         'strategy': 'agent', 'outcome': 'pending_reproduction'},
        {'case': 'unscored_other', 'kind': 'broken', 'split': 'development', 'scored': False,
         'strategy': 'agent', 'outcome': 'no_accepted_proposal'},
    ]
    page = Page(render_evaluation_review(report))
    scored, unscored = page.table_text('scored-cases'), page.table_text('unscored-cases')
    for case in ['upstream_candidate', 'unreproduced_owned', 'unscored_other']:
        assert case not in scored
        assert case in unscored
    assert 'Scored cases2' in page.text
    assert 'Public references awaiting reproduction are unscored' in page.text


def test_inventory_identity_and_selected_cases_are_shown_only_as_recorded():
    report = saved_report()
    report.update(inventory_sha256='f' * 64, inventory_name='development', inventory_case_count=15,
                  selected_case_ids=['renamed_method_broken', 'healthy_neighbor', 'upstream_candidate'])
    page = Page(render_evaluation_review(report))
    assert 'f' * 64 in page.text
    assert 'Inventory namedevelopment' in page.text
    assert 'Inventory case count15' in page.text
    assert 'Recorded selected case IDs' in page.text
    assert 'Historical inventory unspecified' not in page.text


def test_every_evidence_field_is_escaped_without_active_html():
    hostile = '</td><script>alert("x")</script><img src="https://evil.invalid">&'
    report = saved_report()
    report.update(evidence=hostile, model=hostile, execution_backend=hostile,
                  inventory_sha256=hostile, inventory_name=hostile, selected_case_ids=[hostile])
    report['rows'][0].update(case=hostile, label=hostile, split=hostile, kind=hostile,
                             strategy=hostile, outcome=hostile, reason=hostile, run_id=hostile, run_status=hostile)
    report['strategies'].append(hostile)
    report['summary'][hostile] = {}
    report['budget'] = {hostile: hostile}
    source = render_evaluation_review(report, run_links={hostile: hostile})
    page = Page(source)
    assert hostile in page.text
    assert not {'script', 'img', 'iframe', 'object', 'form'} & set(page.tags)
    assert all(link.startswith('#') for link in page.links)
    assert '&lt;script&gt;' in source
    assert 'Content-Security-Policy' in source


@pytest.mark.parametrize('target', ['../runs/abc123/review.html', 'runs/abc123/review.html', './saved-review.html'])
def test_saved_run_links_require_explicit_safe_relative_html_paths(target):
    page = Page(render_evaluation_review(saved_report(), run_links={'abc123': target}))
    assert target in page.links


@pytest.mark.parametrize('target', [
    'https://example.com/review.html', 'http://example.com/review.html', '//example.com/review.html',
    '/private/review.html', 'javascript:alert(1).html', 'data:text/html,evil.html',
    '../runs/review.html?auth=secret', '../runs/review.html#fragment', '../runs/%2freview.html',
    '../runs\\evil.html', '../runs/\nreview.html', 'x.html" onclick="evil()', '', None,
])
def test_unsafe_supplied_run_links_are_omitted(target):
    page = Page(render_evaluation_review(saved_report(), run_links={'abc123': target}))
    assert all(link.startswith('#') for link in page.links)
    assert 'abc123' in page.text


def test_missing_summary_values_are_unavailable_instead_of_fabricated_zeros():
    page = Page(render_evaluation_review({'strategies': ['agent'], 'rows': []}))
    summary = page.table_text('strategy-results')
    assert 'Not recorded' in summary
    assert '0 / 0' not in summary
    assert 'Evidence source not established' in page.text
    assert 'Historical inventory unspecified' in page.text
