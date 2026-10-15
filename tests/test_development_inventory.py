"""Keep the supplemental development contract separate from the original split."""

import hashlib
import json
from pathlib import Path

from docdrift.evaluation import load_cases


ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = ROOT / 'fixtures' / 'development'


def test_supplemental_index_adds_only_development_cases_outside_original_inventory():
    original = json.loads((ROOT / 'fixtures/evaluation/index.json').read_text())
    supplemental = json.loads((DEVELOPMENT / 'index.json').read_text())
    cases = load_cases(DEVELOPMENT / 'index.json')
    assert original['case_count'] == 14
    assert supplemental['case_count'] == len(cases) == 2
    assert supplemental['held_out_broken'] == []
    assert {case['kind'] for case in cases} == {'broken', 'healthy'}
    assert all(case['split'] == 'development' for case in cases)
    assert not {case['id'] for case in cases} & {case['id'] for case in original['cases']}
    assert load_cases(DEVELOPMENT / 'index.json', include_held_out=True) == cases
    assert all(case['reproduction_status'] == 'not_run' and case['behavior_verified'] is False for case in cases)
    assert all((ROOT / case['repository']).is_relative_to(DEVELOPMENT) for case in cases)
    fixture_digest = hashlib.sha256((DEVELOPMENT / 'source_only/manifest.json').read_bytes()).hexdigest()
    assert all(case['fixture_manifest_sha256'] == fixture_digest for case in cases)


def test_supplemental_freeze_covers_index_provenance_and_nested_fixture_manifest():
    manifest = json.loads((DEVELOPMENT / 'manifest.json').read_text())
    files = {path.relative_to(DEVELOPMENT).as_posix() for path in DEVELOPMENT.rglob('*') if path.is_file() and path != DEVELOPMENT / 'manifest.json' and '__pycache__' not in path.parts}
    assert set(manifest['files']) == files
    assert {'index.json', 'README.md', 'source_only/manifest.json', 'source_only/provenance.json'} <= files
    assert all(hashlib.sha256((DEVELOPMENT / name).read_bytes()).hexdigest() == digest for name, digest in manifest['files'].items())
