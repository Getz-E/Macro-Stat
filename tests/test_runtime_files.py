# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Çalışma zamanı dosyaları: GUI kilidi ve KWin geçici betiği."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from macrostat import common, kwin


class GuiLockFileTests(unittest.TestCase):
    def test_lock_file_content_has_no_stale_bytes(self):
        from macrostat import app as app_mod

        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "macrostat-gui-{}.lock".format(os.getuid())
            lock_path.write_text("9" * 200, encoding="utf-8")
            with mock.patch.object(common, "RUNTIME_DIR", Path(tmp)), \
                    mock.patch.object(app_mod, "_GUI_LOCK", None):
                self.assertTrue(app_mod.acquire_gui_single_instance())
                content = lock_path.read_text(encoding="utf-8")
                app_mod.release_gui_single_instance()
        self.assertEqual(content, str(os.getpid()))


class EditorTestGuardTests(unittest.TestCase):
    def test_missing_engine_binary_warns_instead_of_running(self):
        from macrostat import editor

        stub = type("Stub", (), {})()
        stub.profile_data = {"macros": [{"id": "m1"}]}
        stub.selected_macro_idx = 0
        stub._editor_macro_copy = lambda: {"id": "m1", "actions": [{"type": "key"}]}
        with mock.patch.object(common, "DAEMON_BIN", None), \
                mock.patch.object(editor, "QMessageBox") as box, \
                mock.patch.object(editor, "QProcess") as proc:
            editor.EditorMixin.test_current_macro(stub)
        box.warning.assert_called_once()
        self.assertIn("cargo build --release", box.warning.call_args.args[2])
        proc.assert_not_called()


class PackagingManifestTests(unittest.TestCase):
    """Kurulum betiği ve yayın arşivi listeleri gerçek ağacı kapsamalı."""

    ROOT = Path(__file__).resolve().parent.parent

    def test_installer_requires_every_interface_module(self):
        text = (self.ROOT / "packaging" / "install-common.sh").read_text(
            encoding="utf-8")
        missing = [
            p.name for p in sorted((self.ROOT / "macrostat").glob("*.py"))
            if "macrostat/" + p.name not in text
        ]
        self.assertEqual(missing, [], "kurulum listesinde eksik modüller")

    def test_installer_requires_kwin_build_inputs(self):
        text = (self.ROOT / "packaging" / "install-common.sh").read_text(
            encoding="utf-8")
        self.assertIn("src/kwin_input.rs", text)
        self.assertIn("protocols/fake-input.xml", text)

    def test_release_archive_ships_wayland_protocol(self):
        text = (self.ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8")
        self.assertIn("cp -r protocols", text)


class PidFileTests(unittest.TestCase):
    def test_pid_file_is_private_and_contains_daemon_pid(self):
        from macrostat import system

        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "macrostat.pid"
            with mock.patch.object(system, "PID_FILE", pid_path):
                system.write_pid_file(4242)
            self.assertEqual(pid_path.read_text(encoding="utf-8").strip(), "4242")
            self.assertEqual(os.stat(pid_path).st_mode & 0o777, 0o600)


class GuiBuildFallbackTests(unittest.TestCase):
    def test_gui_build_fallback_uses_lockfile(self):
        text = (Path(__file__).resolve().parent.parent / "macrostat"
                / "system.py").read_text(encoding="utf-8")
        self.assertIn('["cargo", "build", "--release", "--locked"]', text)


class ConfigMigrationTests(unittest.TestCase):
    """0.x geliştirme sürümlerinin eski yapılandırma adından taşıma."""

    def _migrate(self, settings, legacy, new):
        with mock.patch.object(settings, "CONFIG_DIR", new), \
                mock.patch.object(settings, "_LEGACY_CONFIG_DIR", legacy):
            settings._migrate_legacy_config()

    def test_legacy_dir_is_moved_when_new_dir_absent(self):
        from macrostat import settings

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            legacy = base / "cachymacro"
            new = base / "macrostat"
            legacy.mkdir()
            (legacy / "profile.json").write_text("{}", encoding="utf-8")

            self._migrate(settings, legacy, new)

            self.assertTrue((new / "profile.json").exists())
            self.assertFalse(legacy.exists())

    def test_existing_new_dir_is_not_overwritten(self):
        from macrostat import settings

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            legacy = base / "cachymacro"
            new = base / "macrostat"
            legacy.mkdir()
            new.mkdir()
            (new / "settings.json").write_text("yeni", encoding="utf-8")

            self._migrate(settings, legacy, new)

            self.assertEqual((new / "settings.json").read_text(encoding="utf-8"),
                             "yeni")
            self.assertTrue(legacy.exists())


class KwinScriptFileTests(unittest.TestCase):
    def test_script_file_lives_in_runtime_dir_with_owner_only_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(common, "RUNTIME_DIR", Path(tmp)):
                path = kwin.write_script_file("var p = workspace.cursorPos;")
                try:
                    self.assertEqual(Path(path).parent, Path(tmp))
                    self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
                    self.assertIn("cursorPos", Path(path).read_text(encoding="utf-8"))
                finally:
                    os.unlink(path)


if __name__ == "__main__":
    unittest.main()
