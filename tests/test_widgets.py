# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Tuş yakalama iletişim kutusunun birim testleri (offscreen Qt)."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QGroupBox, QLineEdit, QListWidget, QMenu,
    QMessageBox, QSpinBox, QTableWidget, QWidget,
)

from macrostat import common, core, onboarding
from macrostat.core import CoreMixin
from macrostat.editor import EditorMixin
from macrostat.recorder import RecorderMixin
from macrostat.widgets import KeyCaptureDialog

_APP = None
_CENTER = QPointF(10.0, 10.0)


def setUpModule():
    global _APP
    _APP = QApplication.instance() or QApplication([])


def _key_event(event_type, key, text=""):
    return QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier, text)


def _mouse_event(event_type, button):
    return QMouseEvent(event_type, _CENTER, button, button,
                       Qt.KeyboardModifier.NoModifier)


class KeyCaptureReleaseTest(unittest.TestCase):
    def setUp(self):
        self.dialog = KeyCaptureDialog()

    def tearDown(self):
        self.dialog.deleteLater()

    def test_released_modifier_is_not_added_to_next_key(self):
        self.dialog.keyPressEvent(
            _key_event(QEvent.Type.KeyPress, Qt.Key.Key_Control))
        self.dialog.keyReleaseEvent(
            _key_event(QEvent.Type.KeyRelease, Qt.Key.Key_Control))

        self.dialog.keyPressEvent(
            _key_event(QEvent.Type.KeyPress, Qt.Key.Key_A, "a"))

        self.assertEqual(self.dialog.captured_key, "KEY_A")

    def test_still_held_modifier_stays_in_combo(self):
        self.dialog.keyPressEvent(
            _key_event(QEvent.Type.KeyPress, Qt.Key.Key_Control))
        self.dialog.keyPressEvent(
            _key_event(QEvent.Type.KeyPress, Qt.Key.Key_A, "a"))

        self.assertEqual(self.dialog.captured_key, "KEY_LEFTCTRL+KEY_A")

    def test_released_mouse_button_is_not_added_to_next_button(self):
        self.dialog.mousePressEvent(
            _mouse_event(QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton))
        self.dialog.mouseReleaseEvent(
            _mouse_event(QEvent.Type.MouseButtonRelease, Qt.MouseButton.LeftButton))

        self.dialog.mousePressEvent(
            _mouse_event(QEvent.Type.MouseButtonPress, Qt.MouseButton.RightButton))

        self.assertEqual(self.dialog.captured_key, "BTN_RIGHT")

    def test_non_ascii_text_does_not_produce_bogus_key_name(self):
        # Türkçe karakterlerde isalnum() True döner; eskiden motorun
        # tanımadığı "KEY_Ş" üretiliyordu.
        self.dialog.keyPressEvent(
            _key_event(QEvent.Type.KeyPress, Qt.Key(0x1000200), "ş"))

        self.assertFalse(getattr(self.dialog, "captured_key", None))

    def test_ascii_fallback_still_works(self):
        self.dialog.keyPressEvent(
            _key_event(QEvent.Type.KeyPress, Qt.Key(0x1000200), "q"))

        self.assertEqual(self.dialog.captured_key, "KEY_Q")


class _EditorHarness(EditorMixin):
    """Düzenleyici yükleme yolları için asgari widget seti."""

    def __init__(self):
        self.edit_name = QLineEdit()
        self.combo_trigger_key = QComboBox()
        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["ONCE"] * 7)
        self.spin_repeat = QSpinBox()
        self.spin_double_tap = QSpinBox()
        self.spin_hold = QSpinBox()
        self.action_table = QTableWidget(0, 3)
        self.release_list = QListWidget()
        self.release_group = QGroupBox()
        self.release_group.setCheckable(True)
        self.release_body = QWidget()
        self.profile_data = {"macros": []}
        self._MODE_REVERSE = ["ONCE", "WHILE_HELD", "TOGGLE_LOOP", "REPEAT_COUNT",
                              "DOUBLE_TAP", "HOLD_LONG_PRESS", "PRESS_AND_RELEASE"]


class EditorReleaseActionsTest(unittest.TestCase):
    def setUp(self):
        self.harness = _EditorHarness()

    def test_saved_release_actions_are_loaded_back_into_editor(self):
        self.harness.profile_data["macros"] = [{
            "name": "M", "triggerKey": "KEY_F1", "triggerMode": "PRESS_AND_RELEASE",
            "actions": [{"type": "KEY_TAP", "key": "KEY_A", "delayMs": 20}],
            "releaseActions": [{"type": "KEY_TAP", "key": "KEY_B", "delayMs": 20}],
        }]
        self.harness.load_macro_into_editor(0)
        self.assertEqual(self.harness.current_release_actions,
                         [{"type": "KEY_TAP", "key": "KEY_B", "delayMs": 20}])
        self.assertTrue(self.harness.release_group.isChecked())


class _RecorderHarness(RecorderMixin):
    def __init__(self):
        self.recording_active = True
        self.recorded_events = []
        self.last_key_time = 0.0
        self.tabs = None

    def refresh_rec_table(self):
        pass

    def trigger_panic(self):
        pass


def _recorder_key_event(event_type, key, text="", autorep=False):
    return QKeyEvent(event_type, key, Qt.KeyboardModifier.NoModifier, text,
                     autorep, 1)


class RecorderKeySymmetryTest(unittest.TestCase):
    def setUp(self):
        self.harness = _RecorderHarness()

    def _keys(self):
        return [e["key"] for e in self.harness.recorded_events
                if e["type"] in ("KEY_DOWN", "KEY_UP")]

    def test_key_up_uses_same_name_as_key_down(self):
        key = Qt.Key(0x1000100)
        self.harness.keyPressEvent(
            _recorder_key_event(QEvent.Type.KeyPress, key, "1"))
        self.harness.keyReleaseEvent(
            _recorder_key_event(QEvent.Type.KeyRelease, key, ""))
        self.assertEqual(self._keys(), ["KEY_1", "KEY_1"])

    def test_auto_repeat_is_recorded_once(self):
        self.harness.keyPressEvent(
            _recorder_key_event(QEvent.Type.KeyPress, Qt.Key.Key_A, "a"))
        self.harness.keyPressEvent(
            _recorder_key_event(QEvent.Type.KeyPress, Qt.Key.Key_A, "a",
                                autorep=True))
        self.harness.keyReleaseEvent(
            _recorder_key_event(QEvent.Type.KeyRelease, Qt.Key.Key_A, ""))
        self.assertEqual(self._keys(), ["KEY_A", "KEY_A"])


class _FakeTabs:
    def __init__(self):
        self._index = 1

    def blockSignals(self, _flag):
        pass

    def setCurrentIndex(self, index):
        self._index = index

    def currentIndex(self):
        return self._index


class _ProfileChangeHarness(_EditorHarness, CoreMixin):
    """Profil değiştirme koruması için düzenleyici + çekirdek karışımı."""

    def __init__(self):
        super().__init__()
        self.tabs = _FakeTabs()
        self._editor_active = True
        self.selected_macro_idx = 0
        self.current_editing_actions = []
        self.current_release_actions = []
        self.profile_data = {"macros": [{
            "name": "M", "triggerKey": "KEY_F1", "triggerMode": "ONCE",
            "repeatCount": 1, "actions": [],
        }]}
        self.load_macro_into_editor(0)


class ProfileChangeGuardTest(unittest.TestCase):
    def setUp(self):
        self.harness = _ProfileChangeHarness()

    def test_change_without_edits_proceeds_and_closes_editor(self):
        self.assertTrue(self.harness.prepare_profile_change())
        self.assertFalse(self.harness._editor_active)
        self.assertEqual(self.harness.tabs.currentIndex(), 0)

    def test_cancel_keeps_editor_open_with_unsaved_edits(self):
        self.harness.edit_name.setText("Değişti")
        with mock.patch.object(
                core.QMessageBox, "question",
                return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.harness.prepare_profile_change())
        self.assertTrue(self.harness._editor_active)
        self.assertEqual(self.harness.tabs.currentIndex(), 1)


class ExclusiveMenuTest(unittest.TestCase):
    def test_switching_option_unchecks_previous(self):
        menu = QMenu()
        picked = []
        core.build_exclusive_menu(
            menu, [("a", "A"), ("b", "B"), ("c", "C")], "a", picked.append)
        actions = menu.actions()
        self.assertTrue(actions[0].isChecked())

        actions[1].trigger()

        self.assertEqual(picked, ["b"])
        self.assertFalse(actions[0].isChecked())
        self.assertTrue(actions[1].isChecked())

    def test_triggering_current_option_keeps_it_checked(self):
        menu = QMenu()
        core.build_exclusive_menu(
            menu, [("a", "A"), ("b", "B")], "a", lambda _value: None)
        actions = menu.actions()

        actions[0].trigger()

        self.assertTrue(actions[0].isChecked())


class OnboardingSkipTest(unittest.TestCase):
    def test_skip_checkbox_allows_leaving_permissions_page(self):
        with mock.patch.object(common, "udev_rule_installed",
                               return_value=False):
            page = onboarding.PermissionsPage()
            try:
                self.assertFalse(page.isComplete())
                page.chk_skip.setChecked(True)
                self.assertTrue(page.isComplete())
            finally:
                page.deleteLater()


if __name__ == "__main__":
    unittest.main()
