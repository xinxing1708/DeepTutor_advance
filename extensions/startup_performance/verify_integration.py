"""Regress installed plugin discovery against the reviewed upstream snapshot."""
from __future__ import annotations

import argparse
import csv
import io
from importlib.metadata import PathDistribution
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

GROUP = Path(__file__).resolve().parent
ROOT = GROUP.parents[1]
DIAG = ROOT / 'data/user/diagnostics/startup-investigation-20261014'
import importlib.util
from importlib.metadata import version
import deeptutor.plugins.registry as registry
import deeptutor.plugins.runtime as runtime

# Load the preserved upstream as the reference, and exercise installed code.
# No startup_candidate/sitecustomize injection is used in this regression.
snapshot = GROUP / f'upstream-{version("deeptutor")}/plugins/registry.py'
spec = importlib.util.spec_from_file_location('deeptutor.plugins._startup_upstream', snapshot)
upstream = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = upstream
spec.loader.exec_module(upstream)
ORIGINAL = upstream._manifest_files
INSTALLED = registry._manifest_files


def manifest():
    return {'schema_version': 'deeptutor.plugin/v1', 'id': 'local.startup-fixture', 'name': 'Startup fixture',
            'version': '1.0.0', 'description_i18n': {'en': 'Isolated startup test'}, 'author': 'Local test',
            'license': 'MIT', 'homepage': 'https://example.invalid/local-fixture', 'source_url': 'https://example.invalid/local-fixture',
            'compatibility': {'deeptutor': '>=1.6.14', 'api': {'capability': '1'}},
            'permissions': {}, 'dependencies': [],
            'extensions': [{'type': 'capability', 'id': 'startup_fixture', 'entry_point': 'fixture.extension:Capability'}]}


class InstalledRegistryBehavior(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fixture-', dir=DIAG)
        self.root = Path(self.temp.name)
        self.metadata = self.root / 'fixture-1.0.0.dist-info'
        self.metadata.mkdir()
        (self.metadata / 'METADATA').write_text('Name: fixture\nVersion: 1.0.0\n', encoding='utf-8')
        self.dist = PathDistribution(self.metadata)
        self.catalog = self.root / 'catalog.json'
        self.catalog.write_text(registry.CATALOG_PATH.read_text(encoding='utf-8'), encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def record(self, paths):
        text = io.StringIO()
        writer = csv.writer(text, lineterminator='\n')
        writer.writerows([[p, '', ''] for p in paths])
        (self.metadata / 'RECORD').write_text(text.getvalue(), encoding='utf-8')

    def plugin_file(self, name='deeptutor.plugin.json', raw=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw or manifest()), encoding='utf-8')
        return path

    def assert_equivalent(self):
        self.assertEqual(ORIGINAL(self.dist), INSTALLED(self.dist))

    def test_plain_wheel_scan_avoids_per_file_existence_checks(self):
        self.record([f'ordinary/file_{i}.py' for i in range(3000)])
        count = 0
        original_exists = Path.exists
        def counted_exists(path):
            nonlocal count
            count += 1
            return original_exists(path)
        with patch.object(Path, 'exists', counted_exists):
            self.assertEqual(INSTALLED(self.dist), [])
        self.assertEqual(count, 0)

    def test_ordinary_dependency_and_later_plugin_install(self):
        (self.root / 'ordinary.py').write_text('', encoding='utf-8')
        self.record(['ordinary.py', self.metadata.name + '/METADATA'])
        self.assert_equivalent()
        self.assertEqual(INSTALLED(self.dist), [])
        self.plugin_file()
        self.record(['ordinary.py', 'deeptutor.plugin.json'])
        self.assert_equivalent()
        self.assertEqual(len(INSTALLED(self.dist)), 1)

    def test_uppercase_and_csv_quoted_manifest_path(self):
        self.plugin_file('folder,comma/DEEPTUTOR.PLUGIN.JSON')
        self.record(['folder,comma/DEEPTUTOR.PLUGIN.JSON'])
        self.assert_equivalent()
        self.assertEqual(len(INSTALLED(self.dist)), 1)

    def test_missing_manifest_and_unrelated_missing_files(self):
        self.record(['missing.py', 'missing/deeptutor.plugin.json'])
        self.assert_equivalent()
        self.assertEqual(INSTALLED(self.dist), [])

    def test_corrupt_json_and_immediate_replacement(self):
        path = self.plugin_file()
        self.record(['deeptutor.plugin.json'])
        path.write_text('{bad json', encoding='utf-8')
        self.assert_equivalent()
        self.assertTrue(INSTALLED(self.dist)[0][2])
        path.write_text(json.dumps(manifest()), encoding='utf-8')
        self.assert_equivalent()
        self.assertEqual(INSTALLED(self.dist)[0][2], '')

    def test_missing_and_empty_record_retain_egg_info_fallback(self):
        self.plugin_file()
        (self.metadata / 'SOURCES.txt').write_text('deeptutor.plugin.json\n', encoding='utf-8')
        self.assert_equivalent()
        self.assertEqual(len(INSTALLED(self.dist)), 1)
        (self.metadata / 'RECORD').write_text('', encoding='utf-8')
        self.assert_equivalent()
        self.assertEqual(len(INSTALLED(self.dist)), 1)

    def test_custom_distribution_file_provider_is_preserved(self):
        self.plugin_file()
        self.record(['deeptutor.plugin.json'])
        class Custom(PathDistribution):
            def read_text(inner, name):
                if name == 'RECORD':
                    return 'custom-provider.py,,\n'
                return super().read_text(name)
            @property
            def files(inner):
                return self.dist.files
        custom = Custom(self.metadata)
        self.assertEqual(ORIGINAL(custom), INSTALLED(custom))
        self.assertEqual(len(INSTALLED(custom)), 1)

    def test_approval_disable_reenable_and_generation_change_remain_live(self):
        path = self.plugin_file()
        self.record(['deeptutor.plugin.json'])
        reg = registry.PluginRegistry(state_path=self.root / 'plugins.json', catalog_path=self.catalog,
                                      installed_distributions=[self.dist])
        ep = SimpleNamespace(name='startup_fixture', value='fixture.extension:Capability', dist=self.dist)
        class Capability:
            def is_active(self, context=None):
                return True
        with patch.object(registry, '_manifest_files', INSTALLED), patch.object(runtime, 'get_plugin_registry', return_value=reg):
            self.assertFalse(runtime.entry_point_can_load(ep, 'deeptutor.extensions'))
            reg.approve('local.startup-fixture')
            self.assertTrue(runtime.entry_point_can_load(ep, 'deeptutor.extensions'))
            guarded = runtime.guard_entry_point_loaded(ep, 'deeptutor.extensions', Capability)
            instance = guarded()
            self.assertTrue(instance.is_active())
            reg.set_enabled('local.startup-fixture', False)
            self.assertFalse(runtime.entry_point_can_load(ep, 'deeptutor.extensions'))
            with self.assertRaises(runtime.PluginRuntimeError):
                instance.is_active()
            reg.set_enabled('local.startup-fixture', True)
            self.assertTrue(instance.is_active())
            changed = manifest()
            changed['permissions'] = {'storage': ['user-output']}
            path.write_text(json.dumps(changed), encoding='utf-8')
            self.assertFalse(runtime.entry_point_can_load(ep, 'deeptutor.extensions'))
            with self.assertRaises(runtime.PluginRuntimeError):
                instance.is_active()
        with patch.object(registry, '_manifest_files', ORIGINAL):
            original_records = [r.to_dict() for r in reg.list_plugins(include_catalog=False)]
        with patch.object(registry, '_manifest_files', INSTALLED):
            self.assertEqual(original_records, [r.to_dict() for r in reg.list_plugins(include_catalog=False)])


def benchmark():
    records = []
    scans = {}
    for name, function in [('original', ORIGINAL), ('installed', INSTALLED)]:
        count = 0
        original_exists = Path.exists
        def counted_exists(path):
            nonlocal count
            count += 1
            return original_exists(path)
        started = time.perf_counter()
        with patch.object(registry, '_manifest_files', function), patch.object(Path, 'exists', counted_exists):
            value = registry.PluginRegistry().list_plugins(include_catalog=False)
        elapsed = time.perf_counter() - started
        rows = [r.to_dict() for r in value]
        scans[name] = rows
        row = {'implementation': name, 'elapsed_seconds': elapsed, 'path_exists_calls': count, 'plugin_records': len(rows)}
        records.append(row)
        print(json.dumps(row), flush=True)
    if scans['original'] != scans['installed']:
        raise AssertionError('Installed plugin records changed')
    output = {'scans': records, 'equal_records': True, 'speedup': records[0]['elapsed_seconds'] / records[1]['elapsed_seconds']}
    (OUTPUT / 'scan-comparison.json').write_text(json.dumps(output, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    OUTPUT = args.output_dir.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InstalledRegistryBehavior)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    (OUTPUT / 'test-result.json').write_text(json.dumps({'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors)}), encoding='utf-8')
    if not result.wasSuccessful():
        sys.exit(1)
    if args.benchmark:
        benchmark()
