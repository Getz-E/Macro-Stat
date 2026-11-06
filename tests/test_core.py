# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Ayarlar, i18n ve paket yapısı için birim testleri."""

import json
import os
import stat
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from macrostat import common, i18n, settings, transfer
from macrostat.logpanel import classify_log_line, filter_lines


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
        text = i18n.T("Algılandı: {}").format("KEY_A")
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


class MousePathSanitizeTests(unittest.TestCase):
    def setUp(self):
        from macrostat.recorder import RecorderMixin
        self.sanitize = RecorderMixin._sanitize_mouse_path

    def test_keeps_only_valid_three_element_points(self):
        data = {"points": [[4, 5, -1], [4, "x", 0], [2, 1], ["9", "2", "3"]]}
        self.assertEqual(self.sanitize(data), [[4, 5, -1], [9, 2, 3]])

    def test_clamps_negative_delay_and_limits_points(self):
        self.assertEqual(self.sanitize({"points": [[-5, 1, 2]]}), [[0, 1, 2]])
        many = {"points": [[0, 1, 1] for _ in range(200_005)]}
        self.assertEqual(len(self.sanitize(many)), 200_000)

    def test_rejects_malformed_payloads(self):
        self.assertEqual(self.sanitize(None), [])
        self.assertEqual(self.sanitize([]), [])
        self.assertEqual(self.sanitize({"points": "nope"}), [])
        self.assertEqual(self.sanitize({"points": [[1, 2, 3], None]}), [[1, 2, 3]])

    def test_sanitizes_optional_start_position(self):
        from macrostat.recorder import RecorderMixin
        sanitize = RecorderMixin._sanitize_mouse_start
        self.assertEqual(sanitize({"start": [120, 40]}), [120, 40])
        self.assertEqual(sanitize({"start": ["-5", "7"]}), [-5, 7])
        self.assertEqual(sanitize({"start": [10**9, -10**9]}),
                         [1_000_000, -1_000_000])
        for bad in (None, {}, {"start": [1]}, {"start": [1, "x"]}, {"start": "1,2"}):
            self.assertIsNone(sanitize(bad), bad)


class MouseButtonRecordingTests(unittest.TestCase):
    def test_sanitize_buttons_filters_invalid_entries(self):
        from macrostat.recorder import sanitize_mouse_buttons
        data = {"buttons": [
            [10, "BTN_LEFT", 1],
            [5, "BTN_WEIRD", 1],
            [-2, "BTN_RIGHT", 0],
            [600_001, "BTN_MIDDLE", 1],
            [7, "BTN_SIDE", 1],
            [8, "BTN_EXTRA", 1],
            [9, "BTN_RIGHT", 2],
            "bad",
        ]}
        self.assertEqual(sanitize_mouse_buttons(data), [
            [10, "BTN_LEFT", 1],
            [0, "BTN_RIGHT", 0],
            [600_000, "BTN_MIDDLE", 1],
            [7, "BTN_SIDE", 1],
            [8, "BTN_EXTRA", 1],
        ])

    def test_sanitize_buttons_rejects_malformed_payloads(self):
        from macrostat.recorder import sanitize_mouse_buttons
        for bad in (None, [], {"buttons": "nope"}, {}):
            self.assertEqual(sanitize_mouse_buttons(bad), [], bad)

    def test_merge_splits_path_at_button_time(self):
        from macrostat.recorder import merge_mouse_path_buttons
        events = merge_mouse_path_buttons(
            [[10, 1, 0], [20, 2, 0], [30, 0, 1]],
            [[30, "BTN_LEFT", 1]],
        )
        self.assertEqual(events, [
            {"type": "MOUSE_PATH", "points": [[10, 1, 0], [20, 2, 0]]},
            {"type": "MOUSE_DOWN", "mouseButton": "BTN_LEFT"},
            {"type": "MOUSE_PATH", "points": [[30, 0, 1]]},
        ])

    def test_merge_inserts_delay_for_idle_gap(self):
        from macrostat.recorder import merge_mouse_path_buttons
        events = merge_mouse_path_buttons([[10, 1, 0]], [[50, "BTN_RIGHT", 0]])
        self.assertEqual(events, [
            {"type": "MOUSE_PATH", "points": [[10, 1, 0]]},
            {"type": "DELAY", "delayMs": 40, "jitterMs": 2},
            {"type": "MOUSE_UP", "mouseButton": "BTN_RIGHT"},
        ])

    def test_merge_without_buttons_keeps_single_path(self):
        from macrostat.recorder import merge_mouse_path_buttons
        points = [[4, 1, 1], [6, -1, 0]]
        self.assertEqual(merge_mouse_path_buttons(points, []),
                         [{"type": "MOUSE_PATH", "points": points}])

    def test_merge_keeps_points_between_buttons_in_time_order(self):
        """Düğmeler arasındaki hareket, düğmelerden sonra değil aralarında yer almalı."""
        from macrostat.recorder import merge_mouse_path_buttons
        events = merge_mouse_path_buttons(
            [[1386, 30, 0], [200, 0, -10]],
            [[935, "BTN_LEFT", 1], [1185, "BTN_LEFT", 0],
             [1887, "BTN_RIGHT", 1], [2087, "BTN_RIGHT", 0]],
        )
        self.assertEqual([e["type"] for e in events], [
            "DELAY", "MOUSE_DOWN", "DELAY", "MOUSE_UP", "MOUSE_PATH",
            "DELAY", "MOUSE_DOWN", "DELAY", "MOUSE_UP",
        ])
        self.assertEqual(events[4]["points"], [[201, 30, 0], [200, 0, -10]])
        self.assertEqual(events[5]["delayMs"], 301)

    def test_widget_within_detects_control_ancestry(self):
        from macrostat.recorder import widget_is_within

        class FakeWidget:
            def __init__(self, parent=None):
                self._parent = parent

            def parentWidget(self):
                return self._parent

        control = FakeWidget()
        child = FakeWidget(FakeWidget(control))
        other = FakeWidget(FakeWidget())
        self.assertTrue(widget_is_within(control, control))
        self.assertTrue(widget_is_within(child, control))
        self.assertFalse(widget_is_within(other, control))

    def test_widget_within_accepts_non_widget_qobjects(self):
        """Uygulama olay filtresi QWidget olmayan nesneler de alır; çökmemeli."""
        from macrostat.recorder import widget_is_within

        class BareQObject:
            pass

        control = BareQObject()
        self.assertFalse(widget_is_within(BareQObject(), control))
        self.assertFalse(widget_is_within(None, control))


class RestartKeyTests(unittest.TestCase):
    def test_normalizes_restart_key(self):
        self.assertEqual(common.DEFAULT_RESTART_KEY, "KEY_F12")
        self.assertEqual(common.normalize_restart_key("key_f12"), "KEY_F12")
        for bad in (None, "", "BTN_LEFT", "F12", "KEY_A+KEY_B"):
            self.assertEqual(common.normalize_restart_key(bad),
                             common.DEFAULT_RESTART_KEY, bad)

    def test_watch_exit_code_is_distinct(self):
        self.assertEqual(common.RESTART_WATCH_EXIT_CODE, 42)
        self.assertNotIn(common.RESTART_WATCH_EXIT_CODE, (0, 1, 2, 4, 5))

    def test_watch_command_uses_daemon_binary(self):
        self.assertEqual(
            common.restart_watch_command(Path("/opt/macrostat-daemon"), "KEY_F12"),
            ["/opt/macrostat-daemon", "--watch-restart", "KEY_F12"],
        )


class RestartWatcherTests(unittest.TestCase):
    def test_stale_watcher_exit_does_not_warn(self):
        """Elle Yeniden Başlat sonrası eski izleyicinin çıkışı hata uyarısı üretmemeli."""
        from macrostat.system import SystemMixin

        class Stub:
            restart_watch_proc = None
            restart_after_stop_called = False

            def show_autosave_banner(self, message):
                self.banner = message

        stub = Stub()
        SystemMixin._restart_watch_finished(stub, 15, None)
        self.assertFalse(hasattr(stub, "banner"), "Eski izleyici çıkışı banner üretmemeli")

    def test_changed_key_replaces_running_watcher(self):
        """STOP sırasında tuş değiştirilirse eski izleyici durdurulup yenisi kurulmalı."""
        from macrostat.system import SystemMixin

        class Stub:
            restart_watch_proc = object()
            _restart_watch_key = "KEY_F12"
            restart_key = "KEY_F9"
            stopped = False

            def stop_restart_watch(self):
                self.stopped = True

        stub = Stub()
        with mock.patch.object(common, "locate_paths", return_value=(None, None)):
            SystemMixin.start_restart_watch(stub)
        self.assertTrue(stub.stopped)

    def test_same_key_keeps_running_watcher(self):
        from macrostat.system import SystemMixin

        class Stub:
            restart_watch_proc = object()
            _restart_watch_key = "KEY_F12"
            restart_key = "KEY_F12"
            stopped = False

            def stop_restart_watch(self):
                self.stopped = True

        stub = Stub()
        SystemMixin.start_restart_watch(stub)
        self.assertFalse(stub.stopped)


class KwinDetectionTests(unittest.TestCase):
    def setUp(self):
        from macrostat import kwin
        self.kwin = kwin

    def test_detects_kde_wayland(self):
        with mock.patch.dict(os.environ, {
                "WAYLAND_DISPLAY": "wayland-0",
                "XDG_CURRENT_DESKTOP": "KDE"}, clear=True):
            self.assertTrue(self.kwin.is_kde_wayland())

    def test_rejects_other_sessions(self):
        cases = [
            {},
            {"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "KDE"},
            {"WAYLAND_DISPLAY": "wayland-0", "XDG_CURRENT_DESKTOP": "GNOME"},
        ]
        for env in cases:
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertFalse(self.kwin.is_kde_wayland(), env)

    def test_cursor_position_is_none_without_qt_dbus(self):
        with mock.patch.object(self.kwin, "QDBusConnection", None):
            self.assertIsNone(self.kwin.cursor_position())


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


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_is_atomic_and_has_metadata(self):
        target = self.dir / "exports" / "backup.json"
        profiles = [{"id": "p1", "name": "Profil", "macros": []}]
        transfer.export_profiles(profiles, target, "p1")
        data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(data["exportedBy"], "MacroStat")
        self.assertEqual(data["activeProfileId"], "p1")
        self.assertEqual(data["profiles"][0]["id"], "p1")
        leftovers = [p for p in target.parent.iterdir() if p.name != "backup.json"]
        self.assertEqual(leftovers, [], "geçici dosya kalmamalı")

    def test_import_regenerates_conflicting_ids(self):
        payload = {
            "profiles": [{
                "id": "p1",
                "name": "Yeni",
                "panicKey": "KEY_PAUSE",
                "macros": [{
                    "id": "m1",
                    "name": "Makro",
                    "triggerKey": "KEY_A",
                    "actions": [{"type": "KEY_TAP", "key": "KEY_B", "id": "a1"}],
                }],
            }]
        }
        result = transfer.import_payload(
            payload, existing_macro_ids={"m1"}, existing_profile_ids={"p1"})
        profile = result["profiles"][0]
        macro = profile["macros"][0]
        self.assertNotEqual(profile["id"], "p1")
        self.assertNotEqual(macro["id"], "m1")
        self.assertFalse(macro["enabled"], "içe aktarılan makro kapalı olmalı")
        self.assertEqual(macro["actions"][0]["key"], "KEY_B")
        self.assertTrue(macro["actions"][0]["id"])

    def test_import_regenerates_unsafe_ids(self):
        unsafe_id = "m" + chr(0x202E) + "1"
        payload = {
            "profiles": [{
                "id": "p<script>1",
                "name": "Yeni",
                "panicKey": "KEY_PAUSE",
                "macros": [
                    {
                        "id": unsafe_id,
                        "name": "Makro",
                        "triggerKey": "KEY_A",
                        "actions": [],
                    },
                    {
                        "id": "safe-id_01",
                        "name": "Güvenli",
                        "triggerKey": "KEY_B",
                        "actions": [],
                    },
                ],
            }]
        }
        result = transfer.import_payload(payload)
        profile = result["profiles"][0]
        unsafe_macro, safe_macro = profile["macros"]
        self.assertNotEqual(profile["id"], "p<script>1")
        self.assertNotEqual(unsafe_macro["id"], unsafe_id)
        for value in (profile["id"], unsafe_macro["id"], safe_macro["id"]):
            self.assertRegex(value, r"^[A-Za-z0-9_-]{1,64}$")
        self.assertEqual(safe_macro["id"], "safe-id_01",
                         "güvenli kimlikler korunmalı")

    def test_import_drops_invalid_actions_with_warning(self):
        result = transfer.import_payload([{
            "name": "M",
            "triggerKey": "KEY_A",
            "actions": [
                {"type": "KEY_TAP", "key": "NOT_A_KEY"},
                {"type": "NOPE"},
                {"type": "DELAY", "delayMs": 10},
            ],
        }])
        macro = result["macros"][0]
        self.assertEqual([a["type"] for a in macro["actions"]], ["DELAY"])
        self.assertEqual(len(result["warnings"]), 2)

    def test_import_rejects_empty_and_broken_files(self):
        with self.assertRaises(transfer.TransferError):
            transfer.import_payload({"foo": "bar"})
        broken = self.dir / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        with self.assertRaises(transfer.TransferError) as ctx:
            transfer.load_payload(broken)
        self.assertNotIn("\n", str(ctx.exception))

    def test_load_payload_enforces_size_limit(self):
        big = self.dir / "big.json"
        big.write_bytes(b" " * (transfer.MAX_FILE_BYTES + 1))
        with self.assertRaises(transfer.TransferError):
            transfer.load_payload(big)

    def test_unique_name_suffixes(self):
        used = {"Profil", "Profil (2)"}
        self.assertEqual(transfer.unique_name("Profil", used), "Profil (3)")
        self.assertEqual(transfer.unique_name("Başka", used), "Başka")


class UdevRuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rule = Path(self.tmp.name) / "rules.d" / "99-macrostat.rules"
        self.patch = mock.patch.object(common, "UDEV_RULE_PATH", self.rule)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_detects_installed_rule(self):
        self.assertFalse(common.udev_rule_installed())
        self.rule.parent.mkdir(parents=True)
        self.rule.write_text(common.UDEV_RULE_CONTENT, encoding="utf-8")
        self.assertTrue(common.udev_rule_installed())

    def test_install_uses_narrow_rule_and_no_chmod_666(self):
        import types

        self.rule.parent.mkdir(parents=True)

        def fake_run(cmd, **_kwargs):
            assert cmd[:3] == ["pkexec", "sh", "-c"]
            script = cmd[3]
            self.assertIn('MODE="0660"', script)
            self.assertIn('TAG+="uaccess"', script)
            # Geniş `input` grubu üyeliği istenmez: uaccess yeterlidir.
            self.assertNotIn('GROUP="input"', script)
            self.assertNotIn("usermod", script)
            self.assertNotIn("chmod 666", script)
            self.rule.write_text(common.UDEV_RULE_CONTENT, encoding="utf-8")
            return types.SimpleNamespace(returncode=0)

        with mock.patch.object(common.shutil, "which", return_value="/usr/bin/pkexec"), \
                mock.patch.object(common.subprocess, "run", side_effect=fake_run):
            ok, detail = common.install_udev_rule()
        self.assertTrue(ok, detail)
        self.assertTrue(common.udev_rule_installed())

    def test_install_does_not_embed_username_in_script(self):
        import types

        self.rule.parent.mkdir(parents=True)

        def fake_run(cmd, **_kwargs):
            script = cmd[3]
            # Betiğe kullanıcı adı gömülmez; kabuk enjeksiyonu yüzeyi yoktur.
            self.assertNotIn("testuser", script)
            self.assertNotIn("bad name", script)
            self.assertNotIn("usermod", script)
            self.rule.write_text(common.UDEV_RULE_CONTENT, encoding="utf-8")
            return types.SimpleNamespace(returncode=0)

        with mock.patch.object(common.shutil, "which", return_value="/usr/bin/pkexec"), \
                mock.patch.object(common.subprocess, "run", side_effect=fake_run):
            ok, detail = common.install_udev_rule()
        self.assertTrue(ok, detail)


class OnboardingChecksTests(unittest.TestCase):
    def test_collect_checks_shape(self):
        from macrostat import onboarding

        checks = onboarding.collect_checks()
        self.assertEqual([c[0] for c in checks],
                         ["uinput", "uaccess", "udev", "daemon"])
        for _key, ok, title, description in checks:
            self.assertIsInstance(ok, bool)
            self.assertTrue(title)
            self.assertTrue(description)
        self.assertIsInstance(onboarding.uinput_writable(), bool)
        self.assertFalse(hasattr(onboarding, "in_input_group"),
                         "'input' grubu kontrolü kaldırılmalı")


class LogPanelHelpersTests(unittest.TestCase):
    def test_classifies_error_before_warning(self):
        self.assertEqual(classify_log_line("[HATA] aygıt açılamadı"), "error")
        self.assertEqual(classify_log_line("[UYARI] tuş atlandı"), "warning")
        self.assertEqual(classify_log_line("[HAZIR] motor çalışıyor"), "ok")
        self.assertEqual(classify_log_line("[TEST] KEY_F8"), "ok")
        self.assertEqual(classify_log_line("sıradan satır"), "normal")

    def test_filter_is_case_insensitive_and_keeps_order(self):
        lines = ["KEY_A basıldı", "hata: KEY_B", "başka"]
        self.assertEqual(filter_lines(lines, "key_"), ["KEY_A basıldı", "hata: KEY_B"])
        self.assertEqual(filter_lines(lines, ""), lines)
        self.assertEqual(filter_lines(lines, "yok"), [])


class SecurityHardeningTests(unittest.TestCase):
    """Açık kaynak yayını öncesi sertleştirme: özel dosyalar ve güvenli metin."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_runtime_dir_rejects_world_writable_base(self):
        unsafe = self.dir / "unsafe"
        unsafe.mkdir()
        os.chmod(unsafe, 0o777)
        home = self.dir / "home"
        home.mkdir()
        with mock.patch.object(common.Path, "home", return_value=home):
            result = common._runtime_dir(str(unsafe))
        self.assertNotEqual(result, unsafe)
        self.assertEqual(stat.S_IMODE(os.stat(result).st_mode), 0o700)

    def test_runtime_dir_accepts_private_xdg_dir(self):
        safe = self.dir / "safe"
        safe.mkdir()
        os.chmod(safe, 0o700)
        self.assertEqual(common._runtime_dir(str(safe)), safe)

    def test_log_lives_in_private_runtime_dir(self):
        self.assertEqual(Path(common.LOG_FILE).parent, Path(common.RUNTIME_DIR))
        self.assertNotEqual(Path(common.LOG_FILE), Path("/tmp/macrostat.log"))

    def test_log_open_refuses_symlink_and_sets_private_mode(self):
        target = self.dir / "victim"
        target.write_text("dokunma", encoding="utf-8")
        link = self.dir / "link.log"
        link.symlink_to(target)
        with mock.patch.object(common, "LOG_FILE", link):
            with self.assertRaises(OSError):
                common.open_rotated_log()
        self.assertEqual(target.read_text(encoding="utf-8"), "dokunma")

        log = self.dir / "real.log"
        with mock.patch.object(common, "LOG_FILE", log):
            handle = common.open_rotated_log()
            handle.write("merhaba\n")
            handle.close()
        self.assertEqual(stat.S_IMODE(os.stat(log).st_mode), 0o600)


    def test_sanitize_display_text_strips_controls_and_markup(self):
        cleaned = common.sanitize_display_text(
            "Kötü\x00 <b>ad</b>\x1b[31m", single_line=True)
        for forbidden in ("\x00", "\x1b", "<", ">"):
            self.assertNotIn(forbidden, cleaned)
        self.assertIn("Kötü", cleaned)
        self.assertIn("ad", cleaned)
        self.assertNotIn("\n", cleaned)
        self.assertEqual(common.sanitize_display_text("a\nb\tc", multiline=True),
                         "a\nbc")
        self.assertEqual(
            common.sanitize_display_text("x" * 500, single_line=True), "x" * 500)
        self.assertEqual(
            common.sanitize_display_text("x" * 500, single_line=True, max_len=20),
            "x" * 20)

    def test_sanitize_display_text_strips_bidi_and_zero_width(self):
        bidi = chr(0x202E)
        zero_width = chr(0x200B)
        bom = chr(0xFEFF)
        cleaned = common.sanitize_display_text(
            "ma" + bidi + "exe" + zero_width + ".txt" + bom, single_line=True)
        for forbidden in (bidi, zero_width, bom):
            self.assertNotIn(forbidden, cleaned)
        self.assertEqual(cleaned, "maexe.txt")

    def test_coerce_int_falls_back_and_clamps(self):
        self.assertEqual(common.coerce_int("12", 1, 1, 99), 12)
        self.assertEqual(common.coerce_int("bad", 1, 1, 99), 1)
        self.assertEqual(common.coerce_int(None, 5, 1, 99), 5)
        self.assertEqual(common.coerce_int(True, 5, 1, 99), 5)
        self.assertEqual(common.coerce_int(1000, 5, 1, 99), 99)
        self.assertEqual(common.coerce_int(-3, 5, 1, 99), 1)

    def test_daemon_lookup_never_uses_path(self):
        with mock.patch.object(common.shutil, "which",
                               side_effect=AssertionError("PATH lookup")):
            candidates = common._daemon_candidates()
        self.assertTrue(candidates)
        self.assertTrue(all(isinstance(p, Path) for p in candidates))

    def test_udev_rule_does_not_require_input_group(self):
        self.assertNotIn('GROUP="input"', common.UDEV_RULE_CONTENT)
        self.assertIn('TAG+="uaccess"', common.UDEV_RULE_CONTENT)
        self.assertIn('MODE="0660"', common.UDEV_RULE_CONTENT)

    def test_udev_rule_installed_requires_uaccess(self):
        rule = self.dir / "rules.d" / "99-macrostat.rules"
        rule.parent.mkdir(parents=True)
        rule.write_text('KERNEL=="uinput", MODE="0660"\n', encoding="utf-8")
        with mock.patch.object(common, "UDEV_RULE_PATH", rule):
            self.assertFalse(common.udev_rule_installed(),
                             "uaccess etiketi olmayan kural yetersiz")
            rule.write_text(common.UDEV_RULE_CONTENT, encoding="utf-8")
            self.assertTrue(common.udev_rule_installed())

    def test_udev_rule_installed_rejects_legacy_input_group_rule(self):
        rule = self.dir / "rules.d" / "99-macrostat.rules"
        rule.parent.mkdir(parents=True)
        rule.write_text(
            'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", '
            'GROUP="input", MODE="0660"\n'
            'SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess", '
            'GROUP="input", MODE="0660"\n',
            encoding="utf-8")
        with mock.patch.object(common, "UDEV_RULE_PATH", rule):
            self.assertFalse(common.udev_rule_installed(),
                             "geniş 'input' grubu içeren eski kural güncel sayılmamalı")

    def test_profile_files_are_private(self):
        from macrostat.core import CoreMixin

        path = self.dir / "profile.json"
        target = type("Target", (), {})()
        target.profile_data = {"id": "p1", "name": "One", "macros": []}
        target.all_profiles = [target.profile_data]
        target.active_profile_id = "p1"
        with mock.patch.object(common, "PROFILE_PATH", path):
            self.assertTrue(CoreMixin.save_profile_to_disk(
                target, restart_daemon=False))
            self.assertTrue(CoreMixin.save_profile_to_disk(
                target, restart_daemon=False))
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        backup = path.with_name(path.name + ".bak")
        self.assertEqual(stat.S_IMODE(os.stat(backup).st_mode), 0o600)

    def test_load_profile_sanitizes_names_and_numeric_fields(self):
        from macrostat.core import CoreMixin

        path = self.dir / "profile.json"
        path.write_text(json.dumps({
            "profiles": [{
                "id": "p1",
                "name": "Kötü\x00<b>",
                "macros": [{
                    "id": "m1",
                    "name": "m\x1b<script>",
                    "repeatCount": "çok",
                    "doubleTapTimeoutMs": None,
                    "holdDurationMs": [1],
                    "actions": [],
                }],
            }],
            "activeProfileId": "p1",
        }), encoding="utf-8")
        target = type("Target", (), {"all_profiles": [], "active_profile_id": ""})()
        with mock.patch.object(common, "PROFILE_PATH", path):
            CoreMixin.load_profile(target)
        profile = target.all_profiles[0]
        for text in (profile["name"], profile["macros"][0]["name"]):
            for forbidden in ("\x00", "\x1b", "<", ">"):
                self.assertNotIn(forbidden, text)
        self.assertIsInstance(profile["macros"][0]["repeatCount"], int)

    def test_load_profile_clamps_numbers_to_editor_ranges(self):
        """Yükleyici, düzenleyicinin gösteremediği değerleri sessizce değiştirmesin."""
        from macrostat.core import CoreMixin

        path = self.dir / "profile.json"
        path.write_text(json.dumps({
            "profiles": [{
                "id": "p1",
                "name": "Sınır",
                "macros": [{
                    "id": "m1",
                    "name": "m",
                    "repeatCount": 10_000,
                    "doubleTapTimeoutMs": 10,
                    "holdDurationMs": 5,
                    "actions": [],
                }],
            }],
            "activeProfileId": "p1",
        }), encoding="utf-8")
        target = type("Target", (), {"all_profiles": [], "active_profile_id": ""})()
        with mock.patch.object(common, "PROFILE_PATH", path):
            CoreMixin.load_profile(target)
        macro = target.all_profiles[0]["macros"][0]
        self.assertEqual(macro["repeatCount"], 9999)
        self.assertEqual(macro["doubleTapTimeoutMs"], 50)
        self.assertEqual(macro["holdDurationMs"], 50)


class TransferSanitizeTests(unittest.TestCase):
    def test_import_sanitizes_control_and_markup_in_names(self):
        result = transfer.import_payload({
            "name": "A\x00<b>",
            "panicKey": "KEY_PAUSE",
            "macros": [],
        })
        name = result["profiles"][0]["name"]
        for forbidden in ("\x00", "<", ">"):
            self.assertNotIn(forbidden, name)
        self.assertIn("A", name)

    def test_text_action_limit_helper(self):
        self.assertTrue(transfer.is_text_within_limits("a" * 100))
        self.assertFalse(transfer.is_text_within_limits(
            "a" * (transfer.MAX_TEXT_BYTES + 1)))
        self.assertFalse(transfer.is_text_within_limits(None))


class PackageTests(unittest.TestCase):
    def test_mixin_app_class_importable(self):
        from macrostat.app import MacroStatApp

        names = {c.__name__ for c in MacroStatApp.__mro__}
        for expected in ("CoreMixin", "MacrosMixin", "EditorMixin",
                         "RecorderMixin", "SystemMixin", "QMainWindow"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
