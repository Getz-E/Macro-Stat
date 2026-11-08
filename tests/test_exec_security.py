# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Ayrıcalıklı yardımcıların ve araçların güvenilir yol çözümlemesi."""

import errno
import os
import stat
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from macrostat import common


def _write_executable(path, mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(mode)
    return path


def _stat_result(mode, uid):
    return os.stat_result((mode, 0, 0, 1, uid, 0, 0, 0, 0, 0))


def _fake_stat(entries):
    """Belirtilen yollar için sahte stat sonucu döndürür."""
    entries = {str(path): info for path, info in entries.items()}

    def fake_stat(self):
        try:
            return entries[str(self)]
        except KeyError:
            raise FileNotFoundError(str(self))
    return fake_stat


def _owned_entries(path, uid, unsafe=None):
    """Dosya ve tüm üst dizinleri için sahte stat sonuçları üretir."""
    path = Path(path).resolve()
    entries = {}
    for component in (path, *path.parents):
        mode = stat.S_IFREG if component == path else stat.S_IFDIR
        entries[component] = _stat_result(mode | 0o755, uid)
    if unsafe is not None:
        entries[Path(unsafe).resolve()] = _stat_result(
            stat.S_IFDIR | 0o777, uid)
    return entries


class TrustedSystemExecutableTests(unittest.TestCase):
    def test_path_environment_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = _write_executable(Path(tmp) / "sh")
            with mock.patch.dict(os.environ, {"PATH": tmp}):
                found = common.trusted_system_executable("sh")
        self.assertIsNotNone(found)
        self.assertTrue(found.is_absolute())
        self.assertNotEqual(found.parent, Path(tmp))
        self.assertNotEqual(found, fake)
        self.assertEqual(found.name, "sh")

    def test_names_with_path_separators_are_rejected(self):
        for name in ("", "../bin/sh", "/bin/sh", "bin/sh"):
            self.assertIsNone(common.trusted_system_executable(name),
                              name)

    def test_user_owned_binary_is_not_a_trusted_system_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_bin = _write_executable(Path(tmp) / "tool")
            self.assertFalse(common._is_trusted_root_binary(user_bin))

    def test_group_writable_binary_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            user_bin = _write_executable(Path(tmp) / "tool", 0o775)
            self.assertFalse(common._is_trusted_root_binary(user_bin))
            self.assertFalse(common._is_trusted_user_binary(user_bin))


class CargoResolutionTests(unittest.TestCase):
    def _resolve(self, home, path_dir):
        env = {"HOME": str(home), "PATH": str(path_dir)}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(common, "SYSTEM_BIN_DIRS", ()), \
                mock.patch.object(common, "VERSIONED_CARGO_PATHS", ()):
            return common.find_cargo()

    def test_user_cargo_is_found_without_using_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cargo = _write_executable(home / ".cargo" / "bin" / "cargo")
            attacker = Path(tmp) / "attacker"
            evil = _write_executable(attacker / "cargo")
            found = self._resolve(home, attacker)
        self.assertEqual(found, cargo)
        self.assertNotEqual(found, evil)

    def test_group_writable_user_cargo_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            _write_executable(home / ".cargo" / "bin" / "cargo", 0o775)
            attacker = Path(tmp) / "attacker"
            attacker.mkdir()
            self.assertIsNone(self._resolve(home, attacker))

    def test_cargo_home_bin_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            cargo_home = Path(tmp) / "cargo-home"
            cargo = _write_executable(cargo_home / "bin" / "cargo")
            attacker = Path(tmp) / "attacker"
            attacker.mkdir()
            env = {"HOME": str(home), "PATH": str(attacker),
                   "CARGO_HOME": str(cargo_home)}
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(common, "SYSTEM_BIN_DIRS", ()), \
                    mock.patch.object(common, "VERSIONED_CARGO_PATHS", ()):
                found = common.find_cargo()
        self.assertEqual(found, cargo)


class UdevPrivilegeTests(unittest.TestCase):
    def test_command_uses_only_trusted_absolute_tools(self):
        mapping = {
            "pkexec": Path("/usr/bin/pkexec"),
            "sudo": Path("/usr/bin/sudo"),
            "sh": Path("/bin/sh"),
            "modprobe": Path("/usr/bin/modprobe"),
            "cat": Path("/usr/bin/cat"),
            "udevadm": Path("/usr/bin/udevadm"),
        }
        with mock.patch.object(common, "trusted_system_executable",
                               side_effect=mapping.get):
            command = common.build_udev_install_command()
        self.assertIsNotNone(command)
        self.assertEqual(command[0], "/usr/bin/pkexec")
        self.assertEqual(command[1], "/bin/sh")
        self.assertEqual(command[2], "-c")
        script = command[3]
        for tool in ("/usr/bin/modprobe", "/usr/bin/cat", "/usr/bin/udevadm",):
            self.assertIn(tool, script)
        self.assertIn(str(common.UDEV_RULE_PATH), script)

    def test_missing_privileged_helper_fails_without_execution(self):
        with mock.patch.object(common, "trusted_system_executable",
                               return_value=None), \
                mock.patch.object(common.subprocess, "run") as run:
            ok, detail = common.install_udev_rule()
        self.assertFalse(ok)
        self.assertIn("privileged", detail)
        run.assert_not_called()


class TrustedParentChainTests(unittest.TestCase):
    """Güvenilir araç, üst dizin zinciri güvenli değilse çalıştırılmamalı."""

    def test_root_binary_rejects_writable_grandparent(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            tool = _write_executable(bindir / "tool")
            entries = _owned_entries(tool, 0, unsafe=Path(tmp))
            with mock.patch.object(Path, "stat", _fake_stat(entries)):
                self.assertFalse(common._is_trusted_root_binary(tool))

    def test_trusted_system_executable_rejects_writable_grandparent(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            _write_executable(bindir / "tool")
            entries = _owned_entries(bindir / "tool", 0, unsafe=Path(tmp))
            with mock.patch.object(Path, "stat", _fake_stat(entries)), \
                    mock.patch.object(common, "SYSTEM_BIN_DIRS", (bindir,)):
                self.assertIsNone(common.trusted_system_executable("tool"))

    def test_trusted_system_executable_returns_resolved_symlink_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real" / "bin"
            tool = _write_executable(real / "tool")
            link = Path(tmp) / "link"
            link.symlink_to(real, target_is_directory=True)
            entries = _owned_entries(tool, 0)
            entries[link] = _stat_result(stat.S_IFDIR | 0o755, 0)
            entries[link / "tool"] = _stat_result(stat.S_IFREG | 0o755, 0)
            with mock.patch.object(Path, "stat", _fake_stat(entries)), \
                    mock.patch.object(common, "SYSTEM_BIN_DIRS", (link,)):
                found = common.trusted_system_executable("tool")
        self.assertEqual(found, tool.resolve())

    def test_root_controlled_rejects_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tool = _write_executable(Path(tmp) / "tool")
            entries = _owned_entries(tool, 0)
            with mock.patch.object(Path, "stat", _fake_stat(entries)):
                self.assertFalse(common._is_root_controlled(tool))

    def test_user_cargo_rejects_writable_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cargo = _write_executable(home / ".cargo" / "bin" / "cargo")
            entries = _owned_entries(
                cargo, os.getuid(), unsafe=home / ".cargo")
            env = {"HOME": str(home), "PATH": str(tmp)}
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(common, "SYSTEM_BIN_DIRS", ()), \
                    mock.patch.object(common, "VERSIONED_CARGO_PATHS", ()), \
                    mock.patch.object(Path, "stat", _fake_stat(entries)):
                found = common.find_cargo()
        self.assertIsNone(found)


class IntermediateSymlinkTests(unittest.TestCase):
    """Son symlink'in hedef zincirindeki ara symlink'ler de doğrulanmalı."""

    def test_writable_intermediate_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "safe"
            bindir = safe / "bin"
            writable = root / "writable"
            bindir.mkdir(parents=True)
            writable.mkdir()
            real = _write_executable(bindir / "real")
            link = writable / "link"
            link.symlink_to(real)
            (bindir / "tool").symlink_to(link)
            entries = _owned_entries(real, 0, unsafe=writable)
            with mock.patch.object(Path, "stat", _fake_stat(entries)), \
                    mock.patch.object(common, "SYSTEM_BIN_DIRS", (bindir,)):
                found = common.trusted_system_executable("tool")
        self.assertIsNone(found)

    def test_writable_directory_symlink_component_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "safe"
            bindir = safe / "bin"
            writable = root / "writable"
            realdir = safe / "real"
            for directory in (bindir, writable, realdir):
                directory.mkdir(parents=True)
            real = _write_executable(realdir / "tool")
            (writable / "dirlink").symlink_to(realdir)
            (bindir / "tool").symlink_to(writable / "dirlink" / "tool")
            entries = _owned_entries(real, 0, unsafe=writable)
            with mock.patch.object(Path, "stat", _fake_stat(entries)), \
                    mock.patch.object(common, "SYSTEM_BIN_DIRS", (bindir,)):
                found = common.trusted_system_executable("tool")
        self.assertIsNone(found)

    def test_safe_intermediate_symlinks_are_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            safe = Path(tmp) / "safe"
            bindir = safe / "bin"
            libdir = safe / "lib"
            realdir = safe / "real"
            for directory in (bindir, libdir, realdir):
                directory.mkdir(parents=True)
            real = _write_executable(realdir / "tool")
            (libdir / "tool").symlink_to(real)
            (bindir / "tool").symlink_to(libdir / "tool")
            entries = _owned_entries(real, 0)
            for directory in (bindir, libdir, safe):
                entries[directory] = _stat_result(stat.S_IFDIR | 0o755, 0)
            with mock.patch.object(Path, "stat", _fake_stat(entries)), \
                    mock.patch.object(common, "SYSTEM_BIN_DIRS", (bindir,)):
                found = common.trusted_system_executable("tool")
                # Resolution must not depend on the original link afterwards.
                (bindir / "tool").unlink()
                evil = _write_executable(Path(tmp) / "evil")
                (bindir / "tool").symlink_to(evil)
        self.assertEqual(found, real.resolve())

    def test_symlink_target_with_different_name_preserves_requested_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            bindir.mkdir()
            actual = _write_executable(bindir / "actual")
            (bindir / "tool").symlink_to(actual)
            entries = _owned_entries(actual, 0)
            with mock.patch.object(Path, "stat", _fake_stat(entries)), \
                    mock.patch.object(common, "SYSTEM_BIN_DIRS", (bindir,)):
                found = common.trusted_system_executable("tool")
                resolved_found = found.resolve() if found else None
                resolved_actual = actual.resolve()
        self.assertEqual(found, bindir / "tool")
        self.assertEqual(resolved_found, resolved_actual)


class AclTrustTests(unittest.TestCase):
    """ACL ile verilen ek yazma izinleri mod bitlerinde görünmez."""

    @staticmethod
    def _acl(entries, version=2):
        data = struct.pack("<I", version)
        for tag, perm, eid in entries:
            data += struct.pack("<HHI", tag, perm, eid)
        return data

    def _write_acl(self, eid=4242):
        return self._acl([
            (0x01, 0x06, 0xFFFFFFFF),  # owner rw
            (0x02, 0x06, eid),         # named user rw
            (0x04, 0x04, 0xFFFFFFFF),  # group r
            (0x10, 0x06, 0xFFFFFFFF),  # mask rw
            (0x20, 0x04, 0xFFFFFFFF),  # other r
        ])

    def test_named_user_write_acl_is_rejected(self):
        self.assertTrue(common._acl_grants_untrusted_write(
            self._write_acl(), trusted_uids={0, os.getuid()}))

    def test_named_group_write_acl_is_rejected(self):
        acl = self._acl([
            (0x01, 0x06, 0xFFFFFFFF),
            (0x04, 0x04, 0xFFFFFFFF),
            (0x08, 0x06, 4242),         # named group rw
            (0x10, 0x06, 0xFFFFFFFF),
            (0x20, 0x04, 0xFFFFFFFF),
        ])
        self.assertTrue(common._acl_grants_untrusted_write(
            acl, trusted_uids={0, os.getuid()}))

    def test_masked_named_user_write_is_not_effective(self):
        acl = self._acl([
            (0x01, 0x06, 0xFFFFFFFF),
            (0x02, 0x06, 4242),
            (0x04, 0x04, 0xFFFFFFFF),
            (0x10, 0x04, 0xFFFFFFFF),  # mask r only
            (0x20, 0x04, 0xFFFFFFFF),
        ])
        self.assertFalse(common._acl_grants_untrusted_write(
            acl, trusted_uids={0, os.getuid()}))

    def test_trusted_named_user_write_is_allowed(self):
        self.assertFalse(common._acl_grants_untrusted_write(
            self._write_acl(eid=0), trusted_uids={0, os.getuid()}))

    def test_malformed_acl_fails_closed(self):
        self.assertTrue(common._acl_grants_untrusted_write(
            b"\x02\x00\x00\x00\x01", trusted_uids={0}))
        self.assertTrue(common._acl_grants_untrusted_write(
            self._acl([(0x01, 0x06, 0xFFFFFFFF)], version=3),
            trusted_uids={0}))
        self.assertTrue(common._acl_grants_untrusted_write(
            b"", trusted_uids={0}))

    def test_missing_acl_is_not_write(self):
        with mock.patch.object(common.os, "getxattr",
                               side_effect=OSError(errno.ENODATA, "yok")):
            self.assertFalse(common._path_acl_grants_untrusted_write(
                Path("/"), {0}))

    def test_unreadable_acl_fails_closed(self):
        with mock.patch.object(common.os, "getxattr",
                               side_effect=OSError(errno.EPERM, "yasak")):
            self.assertTrue(common._path_acl_grants_untrusted_write(
                Path("/"), {0}))

    def test_resolver_rejects_acl_write_on_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            tool = _write_executable(bindir / "tool")
            entries = _owned_entries(tool, 0)
            acl = self._write_acl()

            def fake_getxattr(path, name, *args, **kwargs):
                if Path(path) == Path(tmp):
                    return acl
                raise OSError(errno.ENODATA, "yok")

            with mock.patch.object(Path, "stat", _fake_stat(entries)), \
                    mock.patch.object(common.os, "getxattr",
                                      side_effect=fake_getxattr):
                self.assertFalse(common._is_trusted_root_binary(tool))

    def test_resolver_rejects_acl_write_on_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            bindir = Path(tmp) / "bin"
            tool = _write_executable(bindir / "tool")
            entries = _owned_entries(tool, 0)
            acl = self._write_acl()

            def fake_getxattr(path, name, *args, **kwargs):
                if Path(path) == tool:
                    return acl
                raise OSError(errno.ENODATA, "yok")

            with mock.patch.object(Path, "stat", _fake_stat(entries)), \
                    mock.patch.object(common.os, "getxattr",
                                      side_effect=fake_getxattr):
                self.assertFalse(common._is_trusted_root_binary(tool))


class DaemonResolutionTests(unittest.TestCase):
    """``locate_paths`` ilk bulunan dosyayı değil, doğrulanmış adayı seçmeli."""

    def _locate(self, candidates, tmp):
        with mock.patch.object(common, "_daemon_candidates",
                               return_value=list(candidates)), \
                mock.patch.object(common, "CONFIG_DIR",
                                  Path(tmp) / "config"), \
                mock.patch.object(common, "DEFAULT_PROFILE_PATH",
                                  Path(tmp) / "missing-default.json"):
            return common.locate_paths()[0]

    def test_trusted_user_daemon_is_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            daemon = _write_executable(
                home / ".cargo" / "bin" / "macrostat-daemon")
            found = self._locate([daemon], tmp)
        self.assertEqual(found, daemon)

    def test_world_writable_daemon_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            evil = Path(tmp) / "evil"
            evil.mkdir()
            evil.chmod(0o777)
            daemon = _write_executable(evil / "macrostat-daemon")
            found = self._locate([daemon], tmp)
        self.assertIsNone(found)

    def test_untrusted_candidate_does_not_block_later_trusted(self):
        with tempfile.TemporaryDirectory() as tmp:
            evil = Path(tmp) / "evil"
            evil.mkdir()
            evil.chmod(0o777)
            bad = _write_executable(evil / "macrostat-daemon")
            good = _write_executable(
                Path(tmp) / "home" / ".cargo" / "bin" / "macrostat-daemon")
            found = self._locate([bad, good], tmp)
        self.assertEqual(found, good)

    def test_root_owned_system_daemon_is_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            daemon = _write_executable(
                Path(tmp) / "system" / "macrostat-daemon")
            entries = _owned_entries(daemon, 0)
            with mock.patch.object(Path, "stat", _fake_stat(entries)):
                found = self._locate([daemon], tmp)
        self.assertEqual(found, daemon.resolve())

    def test_repo_candidate_is_made_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            daemon = repo / "macrostat-daemon"
            daemon.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            daemon.chmod(0o644)
            with mock.patch.object(common, "SCRIPT_DIR", repo):
                found = self._locate([daemon], tmp)
            executable = os.access(daemon, os.X_OK)
        self.assertEqual(found, daemon)
        self.assertTrue(executable)


if __name__ == "__main__":
    unittest.main()
