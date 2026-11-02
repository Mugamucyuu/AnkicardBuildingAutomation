"""Shutdown saves progress; resuming never regenerates completed model stages."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock

from vocab_app.desktop import CloseController, prompt_is_dirty
from vocab_app.examples import OfflineClient
from vocab_app.pipeline import ImportPipeline
from vocab_app.settings import ROOT
from vocab_app.taxonomy import TagCatalog
from vocab_app.ui_service import UIService, GenerationPaused


class CloseTests(unittest.TestCase):
    def test_unresponsive_renderer_has_bounded_exit_check(self):
        release = threading.Event()
        window = Mock()
        window.evaluate_js.side_effect = lambda *args: release.wait(5)
        try:
            self.assertFalse(prompt_is_dirty(window, timeout=.01))
        finally:
            release.set()

    def test_native_callback_returns_without_waiting_and_coalesces_clicks(self):
        entered, release, destroyed = threading.Event(), threading.Event(), threading.Event()
        def prepare():
            entered.set()
            release.wait(5)
            return True
        window = Mock()
        window.destroy.side_effect = destroyed.set
        controller = CloseController(window, prepare, Mock())
        self.assertFalse(controller.closing())
        self.assertTrue(entered.wait(2))
        self.assertFalse(controller.closing())
        release.set()
        self.assertTrue(destroyed.wait(2))
        self.assertTrue(controller.closing())
        self.assertEqual(window.destroy.call_count, 1)

    def test_cancel_or_save_failure_leaves_window_open_and_allows_retry(self):
        window = Mock()
        prepare = Mock(side_effect=[False, OSError('disk full'), True])
        error = Mock()
        controller = CloseController(window, prepare, error)
        for index in range(3):
            controller.lock.acquire()
            controller._prepare()
            if index < 2:
                self.assertFalse(controller.approved)
                window.destroy.assert_not_called()
        self.assertTrue(controller.approved)
        error.assert_called_once()


class ResumeTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'output').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'output')
        self.service = UIService(self.temp.name)

    def tearDown(self):
        self.service.pool.shutdown(wait=True)
        self.temp.cleanup()

    def test_shutdown_restart_and_resume_skip_ready_cards_keep_snapshots(self):
        entered, release = threading.Event(), threading.Event()
        original = ImportPipeline.generate
        calls = []
        def slow(pipeline, word, *args):
            calls.append(word)
            if word == 'pear':
                entered.set()
                release.wait(5)
            return original(pipeline, 'apple', *args)
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test'}), patch('vocab_app.ui_service.ModelClient', side_effect=lambda *a: OfflineClient()), patch.object(ImportPipeline, 'generate', slow):
            job = self.service.create_job({'language':'en', 'text':'apple,pear,plum', 'provider':'deepseek', 'model':'test',
                'mode':'independent', 'tag_source':'seed', 'audio':'none', 'image':'none', 'concurrency':1})
            self.assertTrue(entered.wait(5))
            root = Path(self.temp.name) / 'jobs' / job['id']
            before = (root / '0.json').read_bytes()
            prompt = (root / 'prompts.json').read_bytes()
            self.service.prepare_shutdown()
            release.set()
            self.service.pool.shutdown(wait=True)
            saved = json.loads((root / 'job.json').read_text(encoding='utf-8'))
            self.assertEqual([i['status'] for i in saved['items']], ['ready','paused','paused'])
            self.assertEqual(calls, ['apple','pear'])
        resumed = UIService(self.temp.name)
        try:
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'API key'):
                resumed.retry(job['id'])
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test'}), patch('vocab_app.ui_service.ModelClient', side_effect=lambda *a: OfflineClient()), patch.object(ImportPipeline, 'generate', slow):
                resumed.retry(job['id'])
                resumed.pool.submit(lambda: None).result(10)
            self.assertEqual([i['status'] for i in resumed.jobs[job['id']]['items']], ['ready']*3)
            self.assertEqual(calls, ['apple','pear','pear','plum'])
            self.assertEqual((root / '0.json').read_bytes(), before)
            self.assertEqual((root / 'prompts.json').read_bytes(), prompt)
        finally:
            resumed.pool.shutdown(wait=True)

    def test_resume_reuses_content_after_formatting_interrupt(self):
        client = OfflineClient()
        client.enforce_readability = True
        # Use a real validated offline response, with quality functions instrumented.
        note = ImportPipeline(OfflineClient()).generate('apple','en')
        content = {k:copy.deepcopy(note[k]) for k in ('senses','analysis','reading','alternative_forms','proposed_tags')}
        state = {}
        def checkpoint(value):
            state.clear(); state.update(copy.deepcopy(value))
            if 'content' in value and 'formatting' not in value:
                raise GenerationPaused()
        pipeline = ImportPipeline(client, tag_catalog=TagCatalog.load())
        pipeline.checkpoint = checkpoint
        with patch('vocab_app.pipeline.generate_content', return_value=(content, {'ok':True})) as generate:
            with self.assertRaises(GenerationPaused):
                pipeline.generate('apple','en')
            self.assertEqual(generate.call_count, 1)
        resumed = ImportPipeline(client, tag_catalog=TagCatalog.load())
        resumed.resume_state = state
        resumed.checkpoint = lambda value: None
        with patch('vocab_app.pipeline.generate_content', side_effect=AssertionError('repeated paid content call')), patch('vocab_app.pipeline.format_content', return_value=(content, {'ok':True})), patch('vocab_app.pipeline.audit_tags', return_value={'ok':True}):
            result = resumed.generate('apple','en')
        self.assertEqual(result['senses'], note['senses'])
        self.assertEqual(result['analysis'], note['analysis'])


if __name__ == '__main__':
    unittest.main()
