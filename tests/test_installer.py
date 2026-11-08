# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Dağıtıma özel kurulum betikleri ve masaüstü kısayolu."""

import os
import shutil
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
                "apt-cache": '#!/bin/bash\nexit {}\n'.format(apt_cache_rc),
                "apt-get": '#!/bin/bash\necho "apt-get $*" >> "{}"\n'.format(log),
                "add-apt-repository":
                    '#!/bin/bash\necho "add-apt-repository $*" >> "{}"\n'.format(log),
            }
            for name, body in scripts.items():
                path = bindir / name
                path.write_text(body, encoding="utf-8")
                path.chmod(0o755)
            # Yol çözümlemesi kendi testlerinde doğrulanır; burada depo
            # mantığını denemek için yalnızca araç çözümü stub'lanır.
            script = (
                'set -euo pipefail; source "{}"; '
                'trusted_executable() {{ '
                'if [ "$1" = "apt-cache" ]; then '
                'printf "%s\\n" "$STUB_BIN/apt-cache"; return 0; fi; '
                'return 1; }}; '
                'run_root_tool() {{ local name="$1"; shift; '
                '"$STUB_BIN/$name" "$@"; }}; ensure_pyqt6_repo'
            ).format(COMMON)
            result = run_bash(script, {"STUB_BIN": str(bindir)})
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
    def test_actions_are_pinned_to_immutable_shas(self):
        import re
        for name in ("ci.yml", "release.yml"):
            text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                if "uses:" not in line:
                    continue
                self.assertRegex(
                    line.strip(), r"^-?\s*uses: [^@\s]+@[0-9a-f]{40}(\s+#.*)?$",
                    "{}: eylem sabit SHA'ya sabitlenmeli: {}".format(name, line))

    def test_release_runs_tests_and_audit_before_publishing(self):
        text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("cargo fmt --check", text)
        self.assertIn("cargo clippy --all-targets", text)
        self.assertIn("cargo test --release --locked", text)
        self.assertIn("unittest discover -s tests", text)
        self.assertIn("cargo audit", text)
        # Yayın işi doğrulama işlerine bağlı olmalı.
        self.assertRegex(text, r"(?m)^\s+needs:\s*\n?\s*\[?.*verify")
        self.assertRegex(text, r"(?m)^\s+needs:\s*\n?\s*\[?.*python")
        self.assertRegex(text, r"(?m)^\s+needs:\s*\n?\s*\[?.*audit")

    def test_release_permissions_are_minimal_and_attested(self):
        text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("attest-build-provenance", text)
        self.assertIn("subject-path", text)
        self.assertIn("attestations: write", text)
        self.assertIn("id-token: write", text)
        top = text.split("jobs:", 1)[0]
        self.assertIn("permissions:\n  contents: read", top)
        self.assertNotIn("contents: write", top)
        self.assertNotIn("pull_request_target", text)

    def test_workflows_never_expose_repository_secrets_to_fork_builds(self):
        for name in ("ci.yml", "release.yml"):
            text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertNotIn("secrets.", text, name)
            self.assertNotIn("pull_request_target", text, name)

    def test_release_checksum_is_relative_and_verifiable(self):
        text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn(
            '(cd dist && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")',
            text)

        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            dist.mkdir()
            name = "macrostat-v1.0.0-linux-x86_64"
            archive = dist / (name + ".tar.gz")
            archive.write_bytes(b"simulated release archive")
            result = subprocess.run(
                ["bash", "-c",
                 '(cd "{}" && sha256sum "$NAME.tar.gz" > '
                 '"$NAME.tar.gz.sha256")'.format(dist)],
                env={**os.environ, "NAME": name},
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

            checksum = (dist / (name + ".tar.gz.sha256")).read_text(
                encoding="utf-8").strip()
            self.assertEqual(checksum.split()[-1], name + ".tar.gz")

            download = Path(tmp) / "download"
            download.mkdir()
            shutil.copy2(archive, download / archive.name)
            shutil.copy2(dist / (archive.name + ".sha256"),
                         download / (archive.name + ".sha256"))
            verified = subprocess.run(
                ["sha256sum", "-c", archive.name + ".sha256"],
                cwd=str(download), capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_release_documents_artifact_verification(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("gh attestation verify", readme)
        self.assertIn("sha256sum -c", readme)
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("Release integrity", security)
        self.assertIn("Sürüm bütünlüğü", security)

    def test_audit_tool_is_version_pinned(self):
        for name in ("ci.yml", "release.yml"):
            text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn("cargo-audit --version", text, name)
            self.assertNotIn("cargo install --locked cargo-audit\n", text, name)

    def test_pyqt6_major_version_is_bounded(self):
        text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("PyQt6>=6.5,<7", text)

    def test_appimage_support_is_removed(self):
        self.assertFalse((ROOT / "build_appimage.sh").exists())
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("build_appimage", ci)

    def test_ci_checks_msrv_and_every_distro(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("1.79", ci)
        self.assertNotIn("1.75", ci)
        for image in ("ubuntu:24.04", "debian:trixie", "fedora:41", "archlinux"):
            self.assertIn(image, ci)

    def test_ci_test_jobs_build_with_lockfile(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(ci.count("cargo test --release --locked"), 2)

    def test_installer_requires_secure_msrv_with_ubuntu_fallback(self):
        text = (ROOT / "packaging/install-common.sh").read_text(encoding="utf-8")
        self.assertIn('RUST_MIN_VERSION="1.79"', text)
        # Ubuntu 24.04 depo rustc'si 1.75; sürümlü paketlerle yükseltilmeli.
        self.assertIn("rustc-1.79", text)
        self.assertIn("cargo-1.79", text)

    def test_lockfile_is_readable_by_msrv_cargo(self):
        first_lines = (ROOT / "Cargo.lock").read_text(encoding="utf-8").splitlines()[:4]
        versions = [line for line in first_lines if line.startswith("version = ")]
        self.assertTrue(versions, "Cargo.lock sürüm satırı yok")
        self.assertNotEqual(versions[0].strip(), "version = 4")


class UdevScopeTests(unittest.TestCase):
    """udev kuralı dar kalır ve kullanıcı geneli etkisi açıkça bildirilir."""

    def test_rule_uses_narrow_uaccess_permission(self):
        text = (ROOT / "packaging/99-macrostat.rules").read_text(encoding="utf-8")
        self.assertIn('TAG+="uaccess"', text)
        self.assertIn('MODE="0660"', text)
        self.assertNotIn("0666", text)
        self.assertNotIn('GROUP="input"', text)

    def test_installer_warns_that_uaccess_is_user_wide(self):
        text = COMMON.read_text(encoding="utf-8")
        self.assertIn("logged-in user, not to MacroStat alone", text)
        self.assertIn("privileged broker", text)

    def test_gui_permissions_page_warns_that_uaccess_is_user_wide(self):
        text = (ROOT / "macrostat/onboarding.py").read_text(encoding="utf-8")
        self.assertIn("kullanıcı genelinde", text)
        self.assertIn("ayrıcalıklı bir aracı", text)

    def test_documents_state_the_limitation_in_both_languages(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("user-wide, not per application", readme)
        self.assertIn("kullanıcı genelindedir, uygulama başına değildir", readme)
        self.assertIn("user-wide, not application-wide", security)
        self.assertIn("kullanıcı genelindedir, uygulama genelinde değildir", security)


class TrustedToolTests(unittest.TestCase):
    """Kurulum betiği ayrıcalıklı araçları PATH'ten çözmemeli."""

    def _run(self, body, env=None):
        # PATH kasıtlı olarak saldırgan dizine ayarlandığında bash'i de
        # PATH'ten çözmemek için mutlak kabuk yolu kullanılır.
        full_env = os.environ.copy()
        full_env.update(env or {})
        return subprocess.run(
            ["/bin/bash", "-c",
             'set -euo pipefail; source "{}"; {}'.format(COMMON, body)],
            capture_output=True, text=True, env=full_env)

    def test_tool_is_found_in_trusted_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "sh"
            fake.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            fake.chmod(0o755)
            result = self._run("trusted_executable sh", {"PATH": tmp})
        self.assertEqual(result.returncode, 0, result.stderr)
        found = Path(result.stdout.strip())
        self.assertTrue(found.is_absolute())
        self.assertNotEqual(found.parent, Path(tmp))
        self.assertEqual(found.name, "sh")

    def test_path_only_tool_is_never_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "macrostat-untrusted-tool"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            result = self._run(
                "declare -F trusted_executable >/dev/null; "
                "if trusted_executable macrostat-untrusted-tool; "
                "then exit 9; fi; echo rejected", {"PATH": tmp})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rejected")

    def test_user_writable_trusted_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "tool"
            fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake.chmod(0o755)
            result = self._run(
                "declare -F trusted_executable >/dev/null; "
                'TRUSTED_BIN_DIRS=("{}"); '
                "if trusted_executable tool; then exit 9; fi; echo rejected"
                .format(tmp))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rejected")

    def test_names_with_path_separators_are_rejected(self):
        result = self._run(
            "declare -F trusted_executable >/dev/null; "
            "if trusted_executable ../bin/sh; then exit 9; fi; echo rejected")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rejected")

    def test_cargo_is_resolved_without_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cargo = home / ".cargo" / "bin" / "cargo"
            cargo.parent.mkdir(parents=True)
            cargo.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            cargo.chmod(0o755)
            attacker = Path(tmp) / "attacker"
            attacker.mkdir()
            evil = attacker / "cargo"
            evil.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
            evil.chmod(0o755)
            result = self._run("resolve_cargo", {
                "HOME": str(home), "PATH": str(attacker),
                "CARGO_HOME": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        found = Path(result.stdout.strip())
        self.assertTrue(found.is_absolute())
        self.assertNotEqual(found, evil)

    def test_privileged_commands_are_never_bare(self):
        text = COMMON.read_text(encoding="utf-8")
        self.assertIn("trusted_executable", text)
        self.assertIn("run_root_tool", text)
        self.assertIn("CARGO_BIN", text)
        for pattern in ("command -v sudo", "command -v cargo",
                        "run_privileged apt-get", "run_privileged pacman",
                        "run_privileged dnf", "run_privileged modprobe",
                        "run_privileged tee", "run_privileged udevadm"):
            self.assertNotIn(pattern, text)


class DispatcherTests(unittest.TestCase):
    def test_install_all_delegates_to_distro_script(self):
        text = (ROOT / "install_all.sh").read_text(encoding="utf-8")
        self.assertIn("detect_family", text)
        for script in DISTRO_SCRIPTS:
            self.assertIn(script, text)


class RootExecutionGuardTests(unittest.TestCase):
    """Kurulum/kaldırma betikleri kök olarak çalıştırılmamalı.

    Betikler depo tarafından denetlenen yardımcı kütüphaneyi ``source`` eder;
    kök kabuğa ait ``PATH``/ortam değişkenleriyle bu kod yüklenmeden önce
    yükseltilmiş çalıştırma reddedilmelidir.
    """

    ENTRY_POINTS = ("install_all.sh", "install_arch.sh", "install_ubuntu.sh",
                    "install_debian.sh", "install_fedora.sh", "uninstall.sh")

    def test_each_entry_point_refuses_root_before_sourcing(self):
        for name in self.ENTRY_POINTS:
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("Do not run", text, name)
            self.assertIn('"$(id -u)"', text, name)
            guard = text.index('"$(id -u)"')
            source = text.index("source \"$DIR/packaging/install-common.sh\"")
            self.assertLess(guard, source,
                            "{}: kök denetimi source'tan önce olmalı".format(name))

    def test_common_library_refuses_direct_execution(self):
        text = COMMON.read_text(encoding="utf-8")
        self.assertIn("This file is a library", text)
        self.assertIn("install_all.sh or install_<distro>.sh", text)

    def test_root_execution_is_refused_before_source(self):
        for name in self.ENTRY_POINTS:
            with tempfile.TemporaryDirectory() as tmp:
                bindir = Path(tmp) / "bin"
                bindir.mkdir()
                # kök kullanıcı kimliğini taklit et: denetim source'tan önce
                # çalışmazsa betik gerçek kurulum adımlarına geçerdi.
                fake_id = bindir / "id"
                fake_id.write_text("#!/bin/sh\necho 0\n", encoding="utf-8")
                fake_id.chmod(0o755)
                result = subprocess.run(
                    ["/bin/bash", str(ROOT / name)],
                    capture_output=True, text=True,
                    env={"PATH": str(bindir), "HOME": tmp, "LANG": "C"})
            self.assertNotEqual(result.returncode, 0, name)
            self.assertIn("regular user", result.stderr.lower(), name)

    def test_common_library_direct_execution_is_refused(self):
        result = subprocess.run(
            ["/bin/bash", str(COMMON)], capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("library", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
