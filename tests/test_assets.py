# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Uygulama logosu ve masaüstü/menü entegrasyonu."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "assets" / "macrostat.svg"


class LogoAssetTests(unittest.TestCase):
    def test_logo_is_flat_scalable_vector(self):
        text = SVG.read_text(encoding="utf-8")
        root = ET.fromstring(text)
        self.assertEqual(root.get("viewBox"), "0 0 128 128")
        # Gradyan/gölge küçük boyutta kaybolur; logo düz renkli olmalı.
        self.assertNotIn("Gradient", text)
        self.assertNotIn("filter", text)
        self.assertIn("#F2F4F7", text)
        self.assertIn("#0B0D10", text)

    def test_desktop_entry_uses_installed_icon_name(self):
        text = (ROOT / "packaging" / "macrostat.desktop").read_text(
            encoding="utf-8")
        self.assertIn("Icon=macrostat", text)
        self.assertIn("Terminal=false", text)

    def test_gui_window_icon_loads_the_logo(self):
        core = (ROOT / "macrostat" / "core.py").read_text(encoding="utf-8")
        self.assertIn('"macrostat.svg"', core)
        self.assertIn("setWindowIcon", core)

    def test_installers_ship_the_logo(self):
        common = (ROOT / "packaging" / "install-common.sh").read_text(
            encoding="utf-8")
        self.assertIn("assets/macrostat.svg", common)
        self.assertIn("hicolor/scalable/apps", common)


if __name__ == "__main__":
    unittest.main()
