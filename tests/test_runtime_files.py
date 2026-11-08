# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Çalışma zamanı dosyaları: GUI kilidi ve KWin geçici betiği."""

import json
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


def _identity(pid=4242, starttime=111, uid=None,
              exe="/opt/macrostat/macrostat-daemon", ppid=None):
    return {
        "pid": pid,
        "starttime": starttime,
        "uid": os.geteuid() if uid is None else uid,
        "exe": exe,
        "ppid": os.getpid() if ppid is None else ppid,
    }


class PidFileTests(unittest.TestCase):
    def test_pid_file_is_private_and_contains_daemon_identity(self):
        from macrostat import system

        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "macrostat.pid"
            with mock.patch.object(system, "PID_FILE", pid_path), \
                    mock.patch.object(common, "_proc_identity",
                                      return_value=_identity()):
                system.write_pid_file(4242)
            stored = json.loads(pid_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["pid"], 4242)
            self.assertEqual(stored["starttime"], 111)
            self.assertEqual(stored["uid"], os.geteuid())
            self.assertEqual(os.stat(pid_path).st_mode & 0o777, 0o600)


class PidIdentityValidationTests(unittest.TestCase):
    """PID yeniden kullanımı ve yabancı süreçlere sinyal gönderilmemeli."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pid_path = Path(self.tmp.name) / "macrostat.pid"
        self.patch = mock.patch.object(common, "PID_FILE", self.pid_path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _store(self, identity):
        self.pid_path.write_text(json.dumps(identity), encoding="utf-8")

    def test_matching_identity_is_returned(self):
        identity = _identity()
        self._store(identity)
        with mock.patch.object(common, "_proc_identity",
                               return_value=dict(identity)):
            self.assertEqual(common._pid_file_pid(), 4242)

    def test_reused_pid_with_different_start_time_is_rejected(self):
        self._store(_identity(starttime=111))
        with mock.patch.object(common, "_proc_identity",
                               return_value=_identity(starttime=222)):
            self.assertIsNone(common._pid_file_pid())

    def test_process_with_wrong_executable_is_rejected(self):
        identity = _identity(exe="/usr/bin/python3")
        self._store(identity)
        with mock.patch.object(common, "_proc_identity",
                               return_value=dict(identity)):
            self.assertIsNone(common._pid_file_pid())

    def test_process_owned_by_another_user_is_rejected(self):
        identity = _identity(uid=os.geteuid() + 1)
        self._store(identity)
        with mock.patch.object(common, "_proc_identity",
                               return_value=dict(identity)):
            self.assertIsNone(common._pid_file_pid())

    def test_legacy_bare_pid_file_is_not_trusted(self):
        self.pid_path.write_text("4242\n", encoding="utf-8")
        with mock.patch.object(common, "_proc_identity",
                               return_value=_identity()):
            self.assertIsNone(common._pid_file_pid())

    def test_unterminated_identity_record_is_rejected(self):
        self._store({"pid": 4242, "starttime": 111})
        with mock.patch.object(common, "_proc_identity",
                               return_value=_identity()):
            self.assertIsNone(common._pid_file_pid())

    def test_termination_skips_kill_when_identity_does_not_match(self):
        self._store(_identity(starttime=111))
        with mock.patch.object(common, "_proc_identity",
                               return_value=_identity(starttime=222)), \
                mock.patch.object(common.os, "kill") as kill:
            common._terminate_daemon_pid(4242)
        kill.assert_not_called()

    def test_sigkill_is_not_sent_after_pid_is_reused(self):
        identity = _identity()
        self._store(identity)
        identities = [dict(identity), _identity(starttime=999)]
        with mock.patch.object(common, "_proc_identity",
                               side_effect=identities), \
                mock.patch.object(common.os, "kill") as kill:
            common._terminate_daemon_pid(4242, timeout=0)
        kill.assert_called_once()
        self.assertEqual(kill.call_args.args[1], common.signal.SIGTERM)

    def test_stored_identity_for_a_different_pid_is_rejected(self):
        self._store(_identity(pid=4242))
        with mock.patch.object(
                common, "_proc_identity",
                return_value=_identity(pid=9999)):
            self.assertIsNone(common._validated_daemon_identity(9999))

    def test_same_executable_with_different_start_time_is_rejected(self):
        self._store(_identity(starttime=111))
        with mock.patch.object(
                common, "_proc_identity",
                return_value=_identity(starttime=222)), \
                mock.patch.object(common.os, "kill") as kill:
            common._terminate_daemon_pid(4242)
        kill.assert_not_called()

    def test_expected_child_must_be_a_direct_child(self):
        # Kayıt yokken yalnızca doğrudan alt süreç sonlandırılabilir.
        with mock.patch.object(
                common, "_proc_identity",
                return_value=_identity(ppid=os.getpid() + 1)), \
                mock.patch.object(common.os, "kill") as kill:
            common._terminate_daemon_pid(4242, expected_child=True)
        kill.assert_not_called()


class DaemonLifecycleTests(unittest.TestCase):
    """Ölmüş daemon_proc referansı eski PID'ye sinyal göndermemeli."""

    def test_stale_daemon_proc_is_cleared_without_termination(self):
        from macrostat import system

        class ExitedProc:
            pid = 4242

            def poll(self):
                return 0

            def wait(self, timeout=None):
                raise AssertionError("ölü süreç için wait çağrılmamalı")

        stub = type("Stub", (), {})()
        stub.daemon_proc = ExitedProc()
        stub.update_daemon_status = lambda: None
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "macrostat.pid"
            with mock.patch.object(system, "PID_FILE", pid_path), \
                    mock.patch.object(
                        system, "_terminate_daemon_pid") as terminate:
                system.SystemMixin.stop_daemon(stub)
        terminate.assert_not_called()
        self.assertIsNone(stub.daemon_proc)

    def test_live_child_is_terminated_as_verified_direct_child(self):
        from macrostat import system

        class LiveProc:
            pid = 4242

            def poll(self):
                return None

            def wait(self, timeout=None):
                return 0

        stub = type("Stub", (), {})()
        stub.daemon_proc = LiveProc()
        stub.update_daemon_status = lambda: None
        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "macrostat.pid"
            with mock.patch.object(system, "PID_FILE", pid_path), \
                    mock.patch.object(
                        system, "_terminate_daemon_pid") as terminate:
                system.SystemMixin.stop_daemon(stub)
        terminate.assert_called_once_with(4242, expected_child=True)
        self.assertIsNone(stub.daemon_proc)

    def test_cleanup_ignores_exited_daemon_proc(self):
        class ExitedProc:
            pid = 4242

            def poll(self):
                return 0

            def wait(self, timeout=None):
                raise AssertionError("ölü süreç için wait çağrılmamalı")

        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "macrostat.pid"
            with mock.patch.object(common, "PID_FILE", pid_path), \
                    mock.patch.object(
                        common, "DAEMON_PROC", ExitedProc()), \
                    mock.patch.object(
                        common, "_terminate_daemon_pid") as terminate:
                common.cleanup_daemon()
        terminate.assert_not_called()

class GuiBuildFallbackTests(unittest.TestCase):
    def test_gui_build_fallback_uses_trusted_cargo_and_lockfile(self):
        text = (Path(__file__).resolve().parent.parent / "macrostat"
                / "system.py").read_text(encoding="utf-8")
        self.assertIn("common.find_cargo()", text)
        self.assertNotIn('["cargo", "build"', text)
        self.assertIn('"build", "--release", "--locked"', text)


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
