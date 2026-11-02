import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from vocab_app.settings import RESOURCE_ROOT, ROOT, user_data_dir
from vocab_app.prompts import default_prompts


class ReleaseLayoutTests(unittest.TestCase):
    def test_cli_works_with_legacy_windows_stream_encoding(self):
        (ROOT / "output").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            result = subprocess.run([sys.executable, "-m", "vocab_app.cli", "--language", "ja", "--word", "猫", "--output-dir", directory],
                                    cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertIn("预览", result.stdout.decode("utf-8"))

    def test_resources_and_every_prompt_are_packaged_and_readable(self):
        self.assertTrue((RESOURCE_ROOT / "data/pronunciation/kanjium/LICENSE.txt").is_file())
        self.assertTrue((RESOURCE_ROOT / "examples/notes.json").is_file())
        self.assertEqual(len(default_prompts()), 11)
        self.assertTrue(all(text.strip() for text in default_prompts().values()))

    def test_writable_directory_can_be_overridden_without_source_tree_dependency(self):
        with patch.dict(os.environ, {"ANKICARD_DATA_DIR": str(ROOT / "output/test-state")}, clear=True):
            self.assertEqual(user_data_dir(), (ROOT / "output/test-state").resolve())

    def test_default_state_is_not_installation_directory(self):
        with patch.dict(os.environ, {}, clear=True), patch("vocab_app.settings.Path.home", return_value=ROOT / "output/fake-home"):
            self.assertNotEqual(user_data_dir(), ROOT)
            self.assertNotEqual(user_data_dir(), RESOURCE_ROOT)

    def test_release_auditor_detects_secrets_without_returning_values(self):
        import importlib.util
        path = ROOT / "tools/audit_release.py"
        spec = importlib.util.spec_from_file_location("release_audit", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        value = "sk-" + "z" * 40
        findings = module.inspect("sample.py", ("value = " + value).encode())
        self.assertEqual(findings, [("sample.py", 1, "API credential")])
        self.assertNotIn(value, repr(findings))


if __name__ == "__main__":
    unittest.main()
