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


class TranslationCompletenessTests(unittest.TestCase):
    def test_all_translated_literals_have_english(self):
        """T("...") ile kullanılan her sabit metin _EN sözlüğünde olmalı."""
        import ast

        from macrostat.i18n import _EN

        root = Path(__file__).resolve().parent.parent
        sources = list((root / "macrostat").glob("*.py")) + [root / "gui.py"]
        missing = set()
        for path in sources:
            if path.name == "i18n.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "T" and node.args):
                    arg = node.args[0]
                    if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                            and arg.value not in _EN):
                        missing.add(arg.value)
        self.assertEqual(missing, set(), f"Çevirisi eksik: {sorted(missing)}")


class ProfileMigrationTests(unittest.TestCase):
    def setUp(self):
        from macrostat.core import CoreMixin

        self.core_mixin = CoreMixin
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "profile.json"
        self.patch = mock.patch.object(common, "PROFILE_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _target(self):
        return type("Target", (), {})()

    def test_wrapper_schema_uses_active_profile(self):
        profiles = [{"id": "p1", "name": "One", "macros": []},
                    {"id": "p2", "name": "Two", "macros": []}]
        self.path.write_text(json.dumps({
            "schemaVersion": 1, "activeProfileId": "p2", "profiles": profiles,
        }), encoding="utf-8")
        target = self._target()
        active = self.core_mixin.load_profile(target)
        self.assertEqual(active["id"], "p2")
        self.assertEqual(target.active_profile_id, "p2")
        self.assertEqual(len(target.all_profiles), 2)

    def test_unknown_active_profile_falls_back_to_first(self):
        profiles = [{"id": "p1", "name": "One", "macros": []},
                    {"id": "p2", "name": "Two", "macros": []}]
        self.path.write_text(json.dumps({
            "schemaVersion": 1, "activeProfileId": "yok", "profiles": profiles,
        }), encoding="utf-8")
        target = self._target()
        self.assertEqual(self.core_mixin.load_profile(target)["id"], "p1")

    def test_legacy_single_profile_is_accepted(self):
        legacy = {"id": "legacy", "name": "Eski",
                  "macros": [{"id": "m1", "name": "M", "actions": []}]}
        self.path.write_text(json.dumps(legacy), encoding="utf-8")
        target = self._target()
        active = self.core_mixin.load_profile(target)
        self.assertEqual(active["id"], "legacy")
        self.assertEqual(target.active_profile_id, "legacy")
        self.assertEqual(target.all_profiles, [legacy])


class TriggerValidationTests(unittest.TestCase):
    def test_accepts_keys_buttons_and_combos(self):
        for value in ("KEY_A", "BTN_LEFT", "KEY_LEFTSHIFT+KEY_LEFTCTRL",
                      "KEY_CODE_59", " key_f8 "):
            self.assertTrue(common.is_valid_trigger(value), value)

    def test_rejects_invalid_values(self):
        for value in ("", None, "S", "KEY_", "KEY_A+", "KEY_A+rm -rf /"):
            self.assertFalse(common.is_valid_trigger(value), value)


class DefaultSeedTests(unittest.TestCase):
    def test_english_seed_translates_visible_fields(self):
        i18n.set_language("en")
        try:
            data = json.loads(common._seed_profile_bytes().decode("utf-8"))
            profile = data["profiles"][0]
            self.assertEqual(profile["name"], "MacroStat Default Profile")
            names = [m["name"] for m in profile["macros"]]
            self.assertIn("Rapid Click (Demo)", names)
            self.assertTrue(all(m["enabled"] is False for m in profile["macros"]))
        finally:
            i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_turkish_seed_is_unchanged(self):
        i18n.set_language("tr")
        data = json.loads(common._seed_profile_bytes().decode("utf-8"))
        self.assertEqual(data["profiles"][0]["name"], "MacroStat Varsayılan Profil")


class ProfileSaveTests(unittest.TestCase):
    def setUp(self):
        from macrostat.core import CoreMixin

        self.core_mixin = CoreMixin
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "profile.json"
        self.patch = mock.patch.object(common, "PROFILE_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _target(self):
        profile = {"id": "p1", "name": "One",
                   "macros": [{"id": "", "actions": [{"type": "KEY_TAP", "key": "KEY_A"}]}]}
        target = type("Target", (), {})()
        target.profile_data = profile
        target.all_profiles = [profile]
        target.active_profile_id = "p1"
        return target

    def test_save_creates_wrapper_and_no_temp_files(self):
        target = self._target()
        self.assertTrue(self.core_mixin.save_profile_to_disk(target, restart_daemon=False))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["activeProfileId"], "p1")
        self.assertEqual(data["schemaVersion"], 1)
        self.assertTrue(data["profiles"][0]["macros"][0]["id"].startswith("macro-"))
        leftovers = [p.name for p in self.path.parent.iterdir()
                     if p.name not in ("profile.json", "profile.json.bak")]
        self.assertEqual(leftovers, [])

    def test_second_save_keeps_backup(self):
        target = self._target()
        self.core_mixin.save_profile_to_disk(target, restart_daemon=False)
        self.core_mixin.save_profile_to_disk(target, restart_daemon=False)
        self.assertTrue((self.path.parent / "profile.json.bak").exists())


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
