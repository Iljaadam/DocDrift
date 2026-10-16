import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from docdrift.review import render_review


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags = []
        self.links = []
        self.words = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        for key, value in attrs:
            if key in {'src', 'href'}:
                self.links.append(value)

    def handle_data(self, data):
        self.words.append(data)

    @property
    def text(self):
        return ''.join(self.words)


def save_json(root: Path, name: str, value):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value))


def saved_report():
    return {
        'run_id': 'a' * 32,
        'status': 'completed',
        'repair_verdict': 'behavior_verified',
        'diagnosis': 'documentation_drift',
        'repair_source': 'model_agent',
        'adapter': 'local_docker',
        'provider_qualification': 'unconfirmed',
        'protected_hashes_preserved': True,
        'evidence_exported': True,
        'environment': {'image': 'python:3.12-slim', 'image_id': 'sha256:abc123', 'network': 'none'},
        'provenance': {'kind': 'local_git', 'origin': '/tmp/fixture', 'commit': 'b' * 40, 'archive_sha256': 'c' * 64},
        'usage': {'inference_calls': 2, 'paid_calls': 2, 'compute_operations': 3},
        'original_failure_kind': 'process_exit',
        'healthy_preservation': {'required_examples': 1, 'required_cases': 1, 'all_passed': True},
        'coverage_note': 'Only the declared inputs are checked.',
        'results': [
            {
                'phase': 'baseline_target', 'case_id': 'empty', 'example_id': 'target',
                'result': {'operation_id': 'op-baseline', 'image_id': 'sha256:abc123', 'state': 'completed', 'exit_code': 1, 'stderr': 'AttributeError: old method'},
                'checks': {'execution_passed': False, 'observable_passed': False, 'behavior_passed': False, 'errors': ['Exit nonzero']},
            },
            {
                'phase': 'final_repaired', 'case_id': 'empty',
                'result': {'operation_id': 'op-repaired', 'image_id': 'sha256:abc123', 'state': 'completed', 'exit_code': 0, 'stdout': '{"red": 2}\n'},
                'checks': {'execution_passed': True, 'observable_passed': True, 'behavior_passed': True, 'coverage': ['exact_json_output', 'api_result_reaches_output'], 'known_repair_ast_match': False},
            },
            {
                'phase': 'healthy_regression', 'case_id': 'empty',
                'result': {'operation_id': 'op-healthy', 'image_id': 'sha256:abc123', 'state': 'completed', 'exit_code': 0, 'stdout': '{}\n'},
                'checks': {'execution_passed': True, 'observable_passed': True, 'behavior_passed': True},
            },
        ],
    }


def test_review_explains_real_run_evidence_and_preserves_saved_usage(tmp_path):
    report = saved_report()
    save_json(tmp_path, 'profile/profile.json', {'name': 'owned-renamed-method'})
    save_json(tmp_path, 'repair.json', {'strategy': 'agent', 'model': 'nvidia/nemotron', 'live_inference': True, 'usage': {'model_calls': 2, 'prompt_tokens': 1234, 'completion_tokens': 321, 'snippet_runs': 1}})
    (tmp_path / 'original.py').write_text('result = api.old()\nprint(result)\n')
    (tmp_path / 'repaired.py').write_text('result = api.current()\nprint(result)\n')
    (tmp_path / 'repair.patch').write_text('--- a/README.md\n+++ b/README.md\n-result = api.old()\n+result = api.current()\n')
    source = render_review(report, tmp_path)
    page = Page(source)
    assert '<h1>Behavior verified</h1>' in source
    for expected in ['Owned fixture', 'Local Docker', 'Live model repair', 'AttributeError: old method', 'b' * 40, 'sha256:abc123', 'op-baseline', 'op-repaired', 'op-healthy', 'Healthy example preservation', '1234', '321', '1555', 'Known repair AST match (informational): False', 'Nebius Sandbox access', 'deliberately obfuscated']:
        assert expected in page.text
    assert '2 / 2' in page.text
    assert 'evidence.zip' in page.links
    assert 'repair.patch' not in page.links  # Diff is embedded and reviewable offline.
    assert '<span class="removed">-result = api.old()' in source
    assert '<span class="added">+result = api.current()' in source
    assert report == saved_report()  # Rendering is read-only.


def test_saved_live_proposal_separates_historical_generation_from_current_usage(tmp_path):
    historical_usage = {'model_calls': 5, 'prompt_tokens': 7100, 'completion_tokens': 741, 'snippet_runs': 1}
    repair = {'strategy': 'agent', 'model': 'nvidia/nemotron', 'live_inference': True, 'usage': historical_usage}
    save_json(tmp_path, 'repair.json', repair)
    original_transcript = (tmp_path / 'repair.json').read_bytes()
    save_json(tmp_path, 'ledger.json', {'metadata': {
        'inference_usage': {'model_calls': 0, 'prompt_tokens': 0, 'completion_tokens': 0, 'snippet_runs': 0},
        'historical_generation': {
            'source_run_id': 'prior-generation-run', 'proposal_sha256': 'd' * 64,
            **repair, 'note': 'Saved model generation; no new inference in this verification.',
        },
    }})
    report = {
        'run_id': 'prepared-verification', 'status': 'incomplete', 'repair_verdict': 'unattempted',
        'repair_source': 'saved_model_agent', 'adapter': 'sandbox',
        # Even a copied historical report count cannot override this run's metadata.
        'usage': {'inference_calls': 5, 'paid_calls': 0, 'compute_operations': 0},
    }
    source = render_review(report, tmp_path)
    page = Page(source)
    assert 'Saved live model proposal' in page.text
    assert 'Live model repair' not in page.text
    assert 'Current model calls0' in page.text
    assert '<h1>Verification incomplete</h1>' in source
    assert '<h1>Behavior verified</h1>' not in source
    current, historical = source.split('<section id="usage">', 1)[1].split('<h3>Historical generation · prior run</h3>', 1)
    current_text = Page(current).text
    for expected in ['Current inference usage', 'Live inference in this runFalse', 'Inference calls0', 'Prompt tokens0', 'Completion tokens0', 'Total recorded tokens0', 'Model exploration snippet runs0']:
        assert expected in current_text
    assert all(str(value) not in current_text for value in [7100, 741, 7841])
    historical_text = Page(historical.split('</section>', 1)[0]).text
    for expected in ['prior-generation-run', 'd' * 64, 'Historical inference calls5', 'Historical prompt tokens7100', 'Historical completion tokens741', 'Historical total tokens7841', 'Historical snippet runs1', 'not counted as current inference', 'No new model call is recorded']:
        assert expected in historical_text
    assert (tmp_path / 'repair.json').read_bytes() == original_transcript
    assert json.loads(original_transcript)['usage'] == historical_usage


def test_saved_proposal_without_current_usage_does_not_reuse_historical_tokens(tmp_path):
    save_json(tmp_path, 'repair.json', {'live_inference': True, 'usage': {'model_calls': 5, 'prompt_tokens': 7100, 'completion_tokens': 741}})
    source = render_review({'repair_source': 'saved_model_agent'}, tmp_path)
    assert 'Current model callsNot recorded' in Page(source).text
    current = source.split('<section id="usage">', 1)[1].split('<h3>Historical generation · prior run</h3>', 1)[0]
    current_text = Page(current).text
    assert 'Inference callsNot recorded' in current_text
    assert 'Total recorded tokensNot recorded' in current_text
    assert all(str(value) not in current_text for value in [7100, 741, 7841])
    assert 'No new model call is recorded' not in Page(source).text


def test_all_untrusted_evidence_is_escaped_and_page_has_no_active_content(tmp_path):
    hostile = '</code></pre><script>alert("oops")</script><img src="https://bad.invalid">&'
    report = saved_report()
    report.update(run_id=hostile, finding=hostile, coverage_note=hostile)
    report['provenance']['origin'] = hostile
    report['results'][0]['result']['stderr'] = hostile
    report['results'][0]['case_id'] = hostile
    for name in ['original.py', 'repaired.py', 'repair.patch']:
        (tmp_path / name).write_text(hostile)
    save_json(tmp_path, 'repair.json', {'model': hostile})
    source = render_review(report, tmp_path)
    page = Page(source)
    assert 'script' not in page.tags
    assert 'img' not in page.tags
    assert 'iframe' not in page.tags
    assert hostile in page.text
    assert all(not link.startswith(('https:', 'http:', '//', 'javascript:', 'data:')) for link in page.links)
    assert 'Content-Security-Policy' in source
    assert '&lt;script&gt;' in source


@pytest.mark.parametrize(('status', 'verdict', 'headline'), [
    ('incomplete', 'behavior_verified', 'Verification incomplete'),
    ('rejected', 'rejected', 'Repair rejected'),
    ('completed', 'execution_passed', 'Execution passed; behavior unverified'),
    ('completed', 'unattempted', 'No verified repair'),
])
def test_unfinished_and_rejected_reports_never_get_a_success_headline(tmp_path, status, verdict, headline):
    report = {'run_id': 'saved', 'status': status, 'repair_verdict': verdict, 'finding': 'Required checks did not finish'}
    source = render_review(report, tmp_path)
    page = Page(source)
    assert f'<h1>{headline}</h1>' in source
    assert '<h1>Behavior verified</h1>' not in source
    assert 'Required checks did not finish' in page.text
    assert 'No completed check records were saved' in page.text
    assert 'No candidate snippet was saved' in page.text
    assert 'No patch was saved' in page.text
    assert 'evidence.zip' not in page.links
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(('source', 'repair', 'label'), [
    ('model_one_shot', {'live_inference': True}, 'Live model repair'),
    ('synthetic_agent', {'live_inference': False}, 'Synthetic model replay'),
    ('supplied_manual_patch', {}, 'Supplied manual patch'),
])
def test_repair_provenance_distinguishes_live_replay_and_manual(tmp_path, source, repair, label):
    save_json(tmp_path, 'repair.json', repair)
    report = saved_report()
    report['repair_source'] = source
    page = Page(render_review(report, tmp_path))
    assert label in page.text
    assert source in page.text
    assert 'Total recorded tokensNot recorded' in page.text
    assert '$' not in page.text


def test_arbitrary_repository_is_not_called_an_owned_fixture(tmp_path):
    save_json(tmp_path, 'profile/profile.json', {'name': 'my-public-library'})
    page = Page(render_review(saved_report(), tmp_path))
    assert 'Owned fixture' not in page.text
    assert 'Repository snapshot; ownership not recorded' in page.text


def test_saved_coverage_note_is_not_replaced_with_current_verifier_claims(tmp_path):
    report = saved_report()
    report['coverage_note'] = 'Historical exact-AST-only acceptance.'
    page = Page(render_review(report, tmp_path))
    assert 'Saved coverage noteHistorical exact-AST-only acceptance.' in page.text
    assert 'Inspect each operation’s recorded coverage when reviewing historical runs' in page.text


def test_execution_success_does_not_hide_behavior_rejection(tmp_path):
    report = saved_report()
    report['repair_verdict'] = 'execution_passed'
    report['results'][1]['checks'].update(behavior_passed=False, errors=['Required API result does not reach output'])
    page = Page(render_review(report, tmp_path))
    assert 'Execution passed; behavior unverified' in page.text
    assert 'Execution checks2 / 2' in page.text
    assert 'Behavior checks1 / 2' in page.text
    assert 'Required API result does not reach output' in page.text


def test_pending_operation_and_corrupt_optional_artifact_are_visible(tmp_path):
    save_json(tmp_path, 'ledger.json', {'metadata': {'inference_usage': {'prompt_tokens': 11, 'completion_tokens': 9}}, 'operations': [{'phase': 'final_repaired/target/empty', 'operation_id': 'op-pending', 'state': 'accepted', 'result': None}]})
    (tmp_path / 'repair.json').write_text('{broken json')
    page = Page(render_review({'status': 'incomplete'}, tmp_path))
    assert 'Other accepted operations' in page.text
    assert 'op-pending' in page.text
    assert 'repair.json: saved JSON is unreadable' in page.text
    assert 'Total recorded tokens20' in page.text
    assert 'Execution Not recorded' in page.text


def test_false_evidence_flag_overrides_leftover_archive(tmp_path):
    (tmp_path / 'evidence.zip').write_bytes(b'old')
    report = saved_report()
    report['evidence_exported'] = False
    source = render_review(report, tmp_path)
    assert 'evidence.zip' not in Page(source).links
    assert '<h1>Behavior verified</h1>' not in source


def test_optional_artifact_cannot_follow_a_symlink_outside_run(tmp_path):
    root = tmp_path / 'run'
    root.mkdir()
    secret = tmp_path / 'outside.py'
    secret.write_text('PRIVATE OUTSIDE CONTENT')
    (root / 'replacement.py').symlink_to(secret)
    page = Page(render_review({'status': 'rejected'}, root))
    assert 'PRIVATE OUTSIDE CONTENT' not in page.text
    assert 'replacement.py: artifact points outside this run; omitted' in page.text
