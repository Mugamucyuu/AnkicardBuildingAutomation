import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError
from zipfile import ZipFile

from vocab_app import __version__
from vocab_app.data_migrations import backup_data, prepare_data
from vocab_app.settings import ROOT
from vocab_app.ui_service import UIService
from vocab_app.updates import UpdateManager, official_release, version_tuple, RELEASES_URL, LATEST_API


def release(version="0.3.0", content=b"test installer"):
    name = f"Ankicard-{version}-windows-x64-Setup.exe"
    digest = hashlib.sha256(content).hexdigest()
    base = RELEASES_URL + "/download/v" + version + "/"
    return {"tag_name": "v" + version, "html_url": RELEASES_URL + "/tag/v" + version,
            "draft": False, "prerelease": False, "assets": [
                {"name": name, "state": "uploaded", "size": len(content), "digest": "sha256:" + digest,
                 "browser_download_url": base + name},
                {"name": "SHA256SUMS.txt", "state": "uploaded", "browser_download_url": base + "SHA256SUMS.txt"}]}


class UpdateTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "output").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "output")
        self.directory = Path(self.temp.name)
        self.content = b"test installer"
        self.metadata = release(content=self.content)
        def open_url(request, **kwargs):
            url = request.full_url
            if url == LATEST_API:
                return io.BytesIO(json.dumps(self.metadata).encode())
            if url.endswith("SHA256SUMS.txt"):
                name = self.metadata["assets"][0]["name"]
                return io.BytesIO((hashlib.sha256(self.content).hexdigest() + "  " + name + "\n").encode())
            return io.BytesIO(self.content)
        self.opener = Mock()
        self.opener.open.side_effect = open_url
        self.manager = UpdateManager(self.directory, can_install=True, current_version="0.2.0", opener=self.opener)

    def tearDown(self):
        if self.manager.thread: self.manager.thread.join(5)
        self.temp.cleanup()

    def finish(self):
        self.manager.thread.join(5)
        self.assertFalse(self.manager.thread.is_alive())
        return self.manager.status()

    def download(self):
        self.manager.check();self.finish()
        self.manager.download()
        self.assertEqual(self.finish()["state"], "ready")

    def test_version_comparison_and_official_assets_only(self):
        self.assertGreater(version_tuple("0.10.0"), version_tuple("0.9.9"))
        for value in ("../0.3.0", "0.3.0-beta", "0.03.0", None):
            with self.assertRaises(ValueError): version_tuple(value)
        for change in ({"prerelease": True}, {"draft": True}, {"html_url": "https://example.com"}, {"assets": []}):
            with self.assertRaises(ValueError): official_release({**self.metadata, **change})
        self.metadata["assets"][0]["browser_download_url"] = "https://evil.test/setup.exe"
        with self.assertRaises(ValueError): official_release(self.metadata)

    def test_download_verifies_and_prepare_creates_backup_before_install(self):
        (self.directory / "settings.json").write_text('{"theme":"dark"}')
        self.download()
        self.assertEqual(self.manager.installer.read_bytes(), self.content)
        self.manager.request_install()
        plan = self.manager.prepare_install()
        self.assertEqual(self.manager.status()["state"], "installing")
        with ZipFile(plan["backup"]) as archive:
            self.assertEqual(json.loads(archive.read("settings.json"))["theme"], "dark")

    def test_cancel_requested_install_does_not_start_installer(self):
        self.download()
        self.manager.request_install()
        self.manager.cancel()
        self.assertEqual(self.manager.status()["state"], "ready")
        with self.assertRaises(ValueError): self.manager.prepare_install()

    def test_latest_older_or_same_never_downgrades(self):
        self.manager.current_version = "0.4.0"
        self.manager.check()
        self.assertEqual(self.finish()["state"], "up_to_date")
        with self.assertRaises(ValueError): self.manager.download()

    def test_tampered_download_and_tampered_staging_never_install(self):
        self.manager.check();self.finish()
        self.content = b"tampered file"
        self.manager.download()
        self.assertEqual(self.finish()["error"], "verification")
        self.assertIsNone(self.manager.installer)
        self.assertFalse(list(self.directory.rglob("*.exe")))
        self.content = b"test installer"
        self.download()
        self.manager.installer.write_bytes(b"changed locally")
        self.manager.request_install()
        with self.assertRaises(ValueError): self.manager.prepare_install()
        self.assertEqual(self.manager.status()["state"], "error")

    def test_interrupted_download_cleans_partial_and_can_retry(self):
        self.manager.check();self.finish()
        original = self.opener.open.side_effect
        def cancelled(request, **kwargs):
            result = original(request, **kwargs)
            if request.full_url.endswith(".exe"):
                self.manager.cancel_event.set()
            return result
        self.opener.open.side_effect = cancelled
        self.manager.download()
        self.assertEqual(self.finish()["state"], "available")
        self.assertFalse(list(self.directory.rglob("*.partial")))
        self.opener.open.side_effect = original
        self.manager.download()
        self.assertEqual(self.finish()["state"], "ready")

    def test_offline_check_preserves_existing_user_data(self):
        state = self.directory / "settings.json"
        state.write_text('{"theme":"dark"}')
        self.opener.open.side_effect = URLError("offline")
        self.manager.check()
        self.assertEqual(self.finish()["error"], "network")
        self.assertEqual(state.read_text(), '{"theme":"dark"}')

    def test_disk_full_and_backup_failure_leave_app_usable(self):
        self.manager.check();self.finish()
        with patch("vocab_app.updates.shutil.disk_usage", return_value=Mock(free=0)):
            self.manager.download()
            self.assertEqual(self.finish()["error"], "storage")
        self.download()
        self.manager.request_install()
        with patch("vocab_app.updates.backup_data", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): self.manager.prepare_install()
        self.assertEqual(self.manager.status()["state"], "error")

    def test_source_edition_cannot_install_and_active_jobs_block_install(self):
        source = UpdateManager(self.directory)
        with self.assertRaises(ValueError): source.download()
        with self.assertRaises(ValueError): source.request_install()
        service = UIService(self.directory)
        try:
            service.updates = self.manager
            self.download()
            for job in (
                {"status": "running", "items": []},
                {"status": "complete", "items": [], "bulk_import": {"status": "running"}},
                {"status": "complete", "items": [{"status": "importing"}]},
            ):
                service.jobs["busy"] = job
                with self.assertRaises(ValueError): service.request_update_install()
            service.jobs.clear()
            self.assertEqual(service.request_update_install()["state"], "install_requested")
        finally:
            service.pool.shutdown()

    def test_migration_preserves_legacy_files_and_is_idempotent(self):
        files = {"settings.json": b'{"locale":"ja","theme":"dark"}',
                 "prompts/old.md": "用户提示词".encode(), "prompts/bindings.json": b'{"style_ja":"custom/old.md"}',
                 "vocabulary/words.txt": b"apple\n", "jobs/one/job.json": b'{"id":"one"}',
                 "jobs/one/media/test.mp3": b"fixture media"}
        for name, content in files.items():
            path = self.directory / name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        metadata = prepare_data(self.directory, __version__)
        self.assertEqual(metadata["schema_version"], 1)
        with ZipFile(self.directory / "backups" / metadata["backup"]) as archive:
            for name, content in files.items():
                self.assertEqual(archive.read(name), content)
                self.assertEqual((self.directory / name).read_bytes(), content)
        prepare_data(self.directory, __version__)
        self.assertEqual(len(list((self.directory / "backups").glob("*.zip"))), 1)

    def test_future_schema_is_rejected_without_mutation(self):
        path = self.directory / "data-version.json"
        path.write_text('{"schema_version":99,"app_version":"9.0.0"}')
        before = path.read_bytes()
        with self.assertRaises(ValueError): prepare_data(self.directory, __version__)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.directory / "backups").exists())
