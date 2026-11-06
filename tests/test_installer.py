# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Dağıtıma özel kurulum betikleri ve masaüstü kısayolu."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMON = ROOT / "packaging" / "install-common.sh"

DISTRO_SCRIPTS = {
    "install_arch.sh": 'DISTRO_FAMILY="arch"',
    "install_ubuntu.sh": 'DISTRO_FAMILY="debian"',
    "install_debian.sh": 'DISTRO_FAMILY="debian"',
    "install_fedora.sh": 'DISTRO_FAMILY="fedora"',
}


def run_bash(script, env=None):
    full_env = os.environ.copy()
    full_env.update(env or {})
    return subprocess.run(["bash", "-c", script], capture_output=True,
                          text=True, env=full_env)


class InstallerLayoutTests(unittest.TestCase):
    def test_per_distro_scripts_are_executable_wrappers(self):
        for name, family_line in DISTRO_SCRIPTS.items():
            path = ROOT / name
            self.assertTrue(path.is_file(), name)
            text = path.read_text(encoding="utf-8")
            self.assertIn("set -euo pipefail", text)
            self.assertIn("install-common.sh", text)
            self.assertIn(family_line, text)
            self.assertTrue(os.access(path, os.X_OK), name)

    def test_common_library_supports_every_package_manager(self):
        text = COMMON.read_text(encoding="utf-8")
        for manager in ("pacman", "apt-get", "dnf"):
            self.assertIn(manager, text)

    def test_expected_runtime_packages_per_family(self):
        text = COMMON.read_text(encoding="utf-8")
        self.assertIn("python3-pyqt6", text)
        self.assertIn("python-pyqt6", text)
        # evdev crate saf Rust; libevdev sistem paketi gerekmez.
        self.assertNotIn("libevdev", text)

    def test_pkgbuild_does_not_require_libevdev(self):
        text = (ROOT / "PKGBUILD").read_text(encoding="utf-8")
        self.assertNotIn("libevdev", text)


class DistroDetectionTests(unittest.TestCase):
    def _detect(self, content):
        with tempfile.TemporaryDirectory() as tmp:
            os_release = Path(tmp) / "os-release"
            os_release.write_text(content, encoding="utf-8")
            result = run_bash(
                'set -euo pipefail; source "{}"; detect_family'.format(COMMON),
                {"MACROSTAT_OS_RELEASE": str(os_release)})
        return result

    def test_detects_ubuntu(self):
        result = self._detect('ID=ubuntu\nID_LIKE=debian\nVERSION_ID="24.04"\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ubuntu")

    def test_detects_plain_debian(self):
        result = self._detect('ID=debian\nVERSION_ID="13"\n')
        self.assertEqual(result.stdout.strip(), "debian")

    def test_detects_fedora(self):
        result = self._detect('ID=fedora\nVERSION_ID=43\n')
        self.assertEqual(result.stdout.strip(), "fedora")

    def test_detects_arch_and_cachyos(self):
        self.assertEqual(self._detect('ID=arch\n').stdout.strip(), "arch")
        self.assertEqual(
            self._detect('ID=cachyos\nID_LIKE=arch\n').stdout.strip(), "arch")

    def test_unknown_distro_fails_with_message(self):
        result = self._detect('ID=gentoo\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not supported", result.stderr.lower())


class VersionGateTests(unittest.TestCase):
    def _check(self, current, minimum):
        return run_bash(
            'set -euo pipefail; source "{}"; version_ge "$1" "$2"'.format(COMMON),
            {}, ) if False else subprocess.run(
            ["bash", "-c",
             'set -euo pipefail; source "{}"; version_ge "$1" "$2"'.format(COMMON),
             "version_ge", current, minimum],
            capture_output=True, text=True)

    def test_equal_version_passes(self):
        self.assertEqual(self._check("24.04", "24.04").returncode, 0)

    def test_newer_version_passes(self):
        self.assertEqual(self._check("13", "12").returncode, 0)
        self.assertEqual(self._check("24.10", "24.04").returncode, 0)

    def test_older_version_fails(self):
        self.assertNotEqual(self._check("6.4.2", "6.5").returncode, 0)
        self.assertNotEqual(self._check("22.04", "24.04").returncode, 0)


class DesktopEntryTests(unittest.TestCase):
    def test_exec_path_with_spaces_and_dollar_is_quoted(self):
        result = run_bash(
            'set -euo pipefail; source "{}"; desktop_quote "$1"'.format(COMMON)
            + ' ', {"X": "1"}) if False else subprocess.run(
            ["bash", "-c",
             'set -euo pipefail; source "{}"; desktop_quote "$1"'.format(COMMON),
             "desktop_quote", "/home/a b/Macro$Stat/gui.py"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '"/home/a b/Macro\\$Stat/gui.py"')

    def test_entry_content_has_marker_and_no_terminal(self):
        result = subprocess.run(
            ["bash", "-c",
             'set -euo pipefail; source "{}"; '
             'render_desktop_entry "/opt/Macro Stat/gui.py" macrostat'.format(COMMON)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = result.stdout
        self.assertIn('Exec="/opt/Macro Stat/gui.py"', text)
        self.assertIn("Icon=macrostat", text)
        self.assertIn("Terminal=false", text)
        self.assertIn("X-MacroStat-Autogenerated=true", text)

    def test_user_dirs_config_is_parsed_for_localized_desktop(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "user-dirs.dirs"
            config.write_text('XDG_DESKTOP_DIR="$HOME/Masaüstü"\n',
                              encoding="utf-8")
            result = subprocess.run(
                ["bash", "-c",
                 'set -euo pipefail; source "{}"; '
                 'desktop_dir_from_config "$1"'.format(COMMON), "x", str(config)],
                capture_output=True, text=True,
                env={**os.environ, "HOME": "/home/tester"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/home/tester/Masaüstü")

    def test_shortcut_installed_to_menu_and_desktop(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            desktop = Path(tmp) / "Masaüstü"
            home.mkdir()
            result = subprocess.run(
                ["bash", "-c",
                 'set -euo pipefail; source "{}"; '
                 'install_desktop_shortcut "$1" macrostat'.format(COMMON),
                 "x", str(home / "start-macrostat.sh")],
                capture_output=True, text=True,
                env={**os.environ, "HOME": str(home),
                     "MACROSTAT_DESKTOP_DIR": str(desktop),
                     "MACROSTAT_APPS_DIR": str(home / ".local/share/applications")})
            self.assertEqual(result.returncode, 0, result.stderr)
            menu_entry = home / ".local/share/applications/macrostat.desktop"
            desk_entry = desktop / "MacroStat.desktop"
            self.assertTrue(menu_entry.is_file())
            self.assertTrue(desk_entry.is_file())
            self.assertTrue(desk_entry.stat().st_mode & stat.S_IXUSR)
            self.assertIn("X-MacroStat-Autogenerated=true",
                          desk_entry.read_text(encoding="utf-8"))

    def test_shortcut_embeds_absolute_icon_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            desktop = Path(tmp) / "Desktop"
            icon = home / ".local/share/icons/hicolor/scalable/apps/macrostat.svg"
            home.mkdir()
            icon.parent.mkdir(parents=True)
            icon.write_text("<svg/>", encoding="utf-8")
            result = subprocess.run(
                ["bash", "-c",
                 'set -euo pipefail; source "{}"; '
                 'install_desktop_shortcut "$1" macrostat'.format(COMMON),
                 "x", str(home / "start-macrostat.sh")],
                capture_output=True, text=True,
                env={**os.environ, "HOME": str(home),
                     "MACROSTAT_DESKTOP_DIR": str(desktop),
                     "MACROSTAT_APPS_DIR": str(home / ".local/share/applications"),
                     "MACROSTAT_ICON_PATH": str(icon)})
            self.assertEqual(result.returncode, 0, result.stderr)
            for entry in (home / ".local/share/applications/macrostat.desktop",
                          desktop / "MacroStat.desktop"):
                text = entry.read_text(encoding="utf-8")
                self.assertIn("Icon={}".format(icon), text)

    def test_existing_user_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            desktop = Path(tmp) / "Desktop"
            home.mkdir()
            desktop.mkdir()
            target = desktop / "MacroStat.desktop"
            target.write_text("[Desktop Entry]\nName=Benim\n", encoding="utf-8")
            result = subprocess.run(
                ["bash", "-c",
                 'set -euo pipefail; source "{}"; '
                 'install_desktop_shortcut "$1" macrostat'.format(COMMON),
                 "x", str(home / "start-macrostat.sh")],
                capture_output=True, text=True,
                env={**os.environ, "HOME": str(home),
                     "MACROSTAT_DESKTOP_DIR": str(desktop),
                     "MACROSTAT_APPS_DIR": str(home / ".local/share/applications")})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"),
                             "[Desktop Entry]\nName=Benim\n")


class UbuntuRepositoryTests(unittest.TestCase):
    """Ubuntu'da python3-pyqt6 yalnızca 'universe' deposundadır."""

    def _run_with_stubs(self, apt_cache_rc):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            log = Path(tmp) / "calls.log"
            scripts = {
                "id": '#!/bin/bash\n[ "${1:-}" = "-u" ] && { echo 0; exit 0; }\n'
                      'exec /usr/bin/id "$@"\n',
                "apt-cache": '#!/bin/bash\nexit {}\n'.format(apt_cache_rc),
                "apt-get": '#!/bin/bash\necho "apt-get $*" >> "{}"\n'.format(log),
                "add-apt-repository":
                    '#!/bin/bash\necho "add-apt-repository $*" >> "{}"\n'.format(log),
            }
            for name, body in scripts.items():
                path = bindir / name
                path.write_text(body, encoding="utf-8")
                path.chmod(0o755)
            result = run_bash(
                'set -euo pipefail; source "{}"; ensure_pyqt6_repo'.format(COMMON),
                {"PATH": "{}:{}".format(bindir, os.environ["PATH"])})
            calls = log.read_text(encoding="utf-8") if log.exists() else ""
        return result, calls

    def test_missing_python3_pyqt6_enables_universe(self):
        result, calls = self._run_with_stubs(apt_cache_rc=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("add-apt-repository -y universe", calls)
        self.assertIn("apt-get update", calls)

    def test_available_python3_pyqt6_leaves_repos_untouched(self):
        result, calls = self._run_with_stubs(apt_cache_rc=0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, "")


class ReleasePipelineTests(unittest.TestCase):
    def test_appimage_support_is_removed(self):
        self.assertFalse((ROOT / "build_appimage.sh").exists())
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("build_appimage", ci)

    def test_ci_checks_msrv_and_every_distro(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("1.75", ci)
        for image in ("ubuntu:24.04", "debian:trixie", "fedora:41", "archlinux"):
            self.assertIn(image, ci)

    def test_lockfile_is_readable_by_msrv_cargo(self):
        first_lines = (ROOT / "Cargo.lock").read_text(encoding="utf-8").splitlines()[:4]
        versions = [line for line in first_lines if line.startswith("version = ")]
        self.assertTrue(versions, "Cargo.lock sürüm satırı yok")
        self.assertNotEqual(versions[0].strip(), "version = 4")


class DispatcherTests(unittest.TestCase):
    def test_install_all_delegates_to_distro_script(self):
        text = (ROOT / "install_all.sh").read_text(encoding="utf-8")
        self.assertIn("detect_family", text)
        for script in DISTRO_SCRIPTS:
            self.assertIn(script, text)


if __name__ == "__main__":
    unittest.main()
