# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Ayarlar, i18n ve paket yapısı için birim testleri."""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from macrostat import common, i18n, settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "nested" / "settings.json"
        self.patch = mock.patch.object(settings, "SETTINGS_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_defaults_when_file_missing(self):
        with mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8"}, clear=False):
            self.assertEqual(settings.load_settings()["language"], "en")
        with mock.patch.dict(os.environ, {"LC_ALL": "tr_TR.UTF-8"}, clear=False):
            self.assertEqual(settings.load_settings()["language"], "tr")

    def test_roundtrip_is_atomic(self):
        settings.save_settings({"language": "en"})
        self.assertEqual(settings.load_settings()["language"], "en")
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name != "settings.json"]
        self.assertEqual(leftovers, [], "geçici dosya kalmamalı")

    def test_invalid_language_falls_back(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"language": "de"}), encoding="utf-8")
        with mock.patch.dict(os.environ, {"LANG": "tr_TR.UTF-8"}, clear=False):
            self.assertEqual(settings.load_settings()["language"], "tr")

    def test_corrupt_file_falls_back(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{bozuk", encoding="utf-8")
        with mock.patch.dict(os.environ, {"LANG": "en_US.UTF-8"}, clear=False):
            self.assertEqual(settings.load_settings()["language"], "en")


class I18nTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_known_key_translated(self):
        i18n.set_language("en")
        self.assertEqual(i18n.T("İptal"), "Cancel")

    def test_unknown_key_returned_as_is(self):
        i18n.set_language("en")
        self.assertEqual(i18n.T("bilinmeyen anahtar"), "bilinmeyen anahtar")

    def test_dynamic_template_keeps_placeholder(self):
        i18n.set_language("en")
        text = i18n.T("✔ Algılandı: {}").format("KEY_A")
        self.assertIn("KEY_A", text)
        self.assertNotIn("Algılandı", text)

    def test_turkish_returns_source(self):
        i18n.set_language("tr")
        self.assertEqual(i18n.T("İptal"), "İptal")

    def test_languages_table(self):
        self.assertEqual(set(dict(i18n.available_languages())), {"tr", "en"})


class DaemonProcessTests(unittest.TestCase):
    def test_zombie_counts_as_dead(self):
        proc = subprocess.Popen(["sleep", "30"])
        try:
            self.assertTrue(common._process_alive(proc.pid))
            common._terminate_daemon_pid(proc.pid)
            # Zombi süreç (henüz reap edilmedi) ölü sayılmalı; aksi halde
            # arayüz her motor durdurmasında timeout kadar donar.
            self.assertFalse(common._process_alive(proc.pid))
        finally:
            proc.wait()

    def test_terminate_does_not_block_on_timeout(self):
        proc = subprocess.Popen(["sleep", "30"])
        try:
            started = time.monotonic()
            common._terminate_daemon_pid(proc.pid)
            self.assertLess(time.monotonic() - started, 0.5)
        finally:
            proc.wait()


class PackageTests(unittest.TestCase):
    def test_mixin_app_class_importable(self):
        from macrostat.app import MacroStatApp

        names = {c.__name__ for c in MacroStatApp.__mro__}
        for expected in ("CoreMixin", "MacrosMixin", "EditorMixin",
                         "RecorderMixin", "SystemMixin", "QMainWindow"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
