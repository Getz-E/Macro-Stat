# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Sistem sekmesi, motor süreç denetimi, izinler ve yedekleme."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from . import common, theme, transfer
from .common import *  # noqa: F401,F403
from .common import _pid_file_pid, _terminate_daemon_pid
from .widgets import SlidingSwitch, KeyCaptureDialog  # noqa: F401

class SystemMixin:
    """Sistem sekmesi, motor süreç denetimi, izinler ve yedekleme."""

    def setup_system_tab(self):
        layout = QVBoxLayout(self.tab_system)
        self.sys_info = QTextEdit()
        self.sys_info.setReadOnly(True)
        layout.addWidget(self.sys_info)

        p_box = QHBoxLayout()
        btn_fix = QPushButton(T("Donanım İzinlerini Otomatik Düzelt (udev)"))
        theme.set_variant(btn_fix, "primary")
        btn_fix.clicked.connect(self.fix_permissions)
        p_box.addWidget(btn_fix)

        btn_ref = QPushButton(T("Durumu Yenile"))
        btn_ref.clicked.connect(self.refresh_system_status)
        p_box.addWidget(btn_ref)
        p_box.addStretch()
        layout.addLayout(p_box)

        b_box = QHBoxLayout()
        btn_backup = QPushButton(T("Yedekle…"))
        btn_backup.clicked.connect(self.backup_all_profiles)
        b_box.addWidget(btn_backup)

        btn_restore = QPushButton(T("Geri Yükle…"))
        btn_restore.clicked.connect(self.restore_profiles_from_file)
        b_box.addWidget(btn_restore)

        btn_onboarding = QPushButton(T("Kurulumu yeniden çalıştır"))
        btn_onboarding.clicked.connect(self.run_onboarding_wizard)
        b_box.addWidget(btn_onboarding)
        b_box.addStretch()
        layout.addLayout(b_box)
        self.refresh_system_status()

    def backup_all_profiles(self):
        if not self.all_profiles:
            QMessageBox.warning(self, T("Yedekleme"),
                                T("Yedeklenecek profil bulunamadı."))
            return
        default_name = "macrostat-yedek-{}.json".format(time.strftime("%Y%m%d-%H%M"))
        path, _ = QFileDialog.getSaveFileName(
            self, T("Profilleri Yedekle"),
            str(Path.home() / default_name), "JSON (*.json)")
        if not path:
            return
        try:
            transfer.export_profiles(self.all_profiles, path, self.active_profile_id)
            self.show_autosave_banner(
                T("{} profil yedeklendi: {}").format(len(self.all_profiles), path))
        except transfer.TransferError as exc:
            QMessageBox.critical(self, T("Yedekleme Hatası"), str(exc))

    def restore_profiles_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, T("Yedeği Geri Yükle"), str(Path.home()), "JSON (*.json)")
        if not path:
            return
        try:
            data = transfer.load_payload(path)
            existing_macros = {
                m.get("id") for p in self.all_profiles
                for m in p.get("macros", []) if isinstance(m, dict) and m.get("id")
            }
            existing_profiles = {p.get("id") for p in self.all_profiles if p.get("id")}
            result = transfer.import_payload(data, existing_macros, existing_profiles)
        except transfer.TransferError as exc:
            QMessageBox.critical(self, T("Yedek Geri Yükleme"), str(exc))
            return

        if not result["profiles"]:
            QMessageBox.warning(
                self, T("Yedek Geri Yükleme"),
                T("Bu dosyada geri yüklenecek profil yok. Makroları "
                  "Makrolar sekmesindeki 'İçe Aktar…' ile ekleyin."))
            return

        answer = QMessageBox.question(
            self, T("Yedek Geri Yükleme"),
            T("{} profil geri yüklenecek. Aynı adlı profiller '(2)', '(3)' "
              "ekleriyle eklenir; mevcut profiller silinmez. Devam edilsin mi?").format(
                len(result["profiles"])),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            used_names = {p.get("name") for p in self.all_profiles if p.get("name")}
            for profile in result["profiles"]:
                profile["name"] = transfer.unique_name(profile.get("name"), used_names)
                used_names.add(profile["name"])
                self.all_profiles.append(profile)
            self.populate_profile_combo()
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self.show_autosave_banner(
                T("{} profil geri yüklendi.").format(len(result["profiles"])))
        except Exception as exc:
            QMessageBox.critical(self, T("Yedek Geri Yükleme"), str(exc))

    def refresh_system_status(self):
        uinput_ok = os.access("/dev/uinput", os.W_OK)
        guide_text = T(
            "=== MacroStat Donanım ve Sistem Tanılama ===\n"
            "Kernel /dev/uinput: {}\n"
            "Motor İkili Dosyası: {}\n"
            "Profil Dosyası: {}\n"
            "Acil Durdurma Tuşu (STOP): {}\n"
            "Log Dosyası: {}\n"
        ).format(
            T("Erişilebilir (Yazma İzni Var)") if uinput_ok
            else T("Erişim Yok (İzin Gerekli)"),
            common.DAEMON_BIN or T("İkili Dosya Bulunamadı (cargo build --release çalıştırın)"),
            common.PROFILE_PATH.resolve() if common.PROFILE_PATH else T("Bulunamadı"),
            common.PANIC_KEY,
            LOG_FILE,
        )
        self.sys_info.setPlainText(guide_text)

    def fix_permissions(self):
        try:
            ok, detail = common.install_udev_rule()
            if not ok:
                raise RuntimeError(T("İzinler kurulamadı: {}").format(detail))
            time.sleep(0.3)
            self.restart_daemon(show_message=False)
            self.refresh_system_status()
            QMessageBox.information(
                self, T("İzinler Düzeltildi"),
                T("udev kuralı kuruldu ve motor başlatıldı.\n"
                  "Kural yeni oturumda etkinleşir; sorun sürerse oturumu kapatıp açın."),
            )
        except Exception as e:
            QMessageBox.critical(self, T("Hata"), str(e))

    def _daemon_stopped_by_panic(self):
        """Bu motor çalışması sırasında yazılmış STOP kaydı var mı?"""
        try:
            offset = getattr(self, "_daemon_log_offset", 0)
            if not LOG_FILE.exists() or LOG_FILE.stat().st_size <= offset:
                return False
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(offset)
                return "[STOP] Acil durdurma" in f.read()
        except Exception:
            return False

    def is_daemon_running(self):
        if self.daemon_proc is not None and self.daemon_proc.poll() is None:
            return True
        return _pid_file_pid() is not None

    def check_and_auto_start_daemon(self):
        if getattr(self, "is_manually_stopped", False) or getattr(self, "was_editor_daemon_running", False):
            return
        if not self.is_daemon_running():
            self.restart_daemon(show_message=False)

    def update_daemon_status(self):
        if getattr(self, "is_manually_stopped", False):
            self.lbl_stopped.show()
            self.status_badge.setText(T("Motor Durduruldu (STOP)"))
            theme.set_state(self.status_badge, "error")
            self.btn_restart_after_stop.setEnabled(True)
            self.start_restart_watch()
            return
        self.btn_restart_after_stop.setEnabled(False)
        if getattr(self, "was_editor_daemon_running", False):
            self.status_badge.setText(T("Düzenleme Modu (Beklemede)"))
            theme.set_state(self.status_badge, "info")
            return
        if self.is_daemon_running():
            self.failed_status_checks = 0
            self.status_badge.setText(T("Aktif"))
            theme.set_state(self.status_badge, "ok")
            if hasattr(self, 'act_view_log'):
                self.act_view_log.setText(T("Günlüğü İncele"))
                self.act_view_log.setIcon(theme.icon("document-preview"))
            if hasattr(self, 'btn_quick_fix'):
                self.btn_quick_fix.hide()
        else:
            # Fiziksel STOP tuşu motoru kapatır; bu durum oturum boyunca korunur.
            if self._daemon_stopped_by_panic():
                self.is_manually_stopped = True
                self.lbl_stopped.show()
                self.status_badge.setText(T("Motor Durduruldu (STOP)"))
                theme.set_state(self.status_badge, "error")
                self.btn_restart_after_stop.setEnabled(True)
                self.start_restart_watch()
                return
            self.failed_status_checks += 1
            if self.failed_status_checks >= 2:
                exit_code = self.daemon_proc.poll() if self.daemon_proc is not None else None
                if exit_code not in (None, 0):
                    self.status_badge.setText(T("Motor Çöktü (kod {})").format(exit_code))
                else:
                    self.status_badge.setText(T("Motor Durduruldu"))
                theme.set_state(self.status_badge, "error")
                if hasattr(self, 'act_view_log'):
                    self.act_view_log.setText(T("Hatayı İncele"))
                    self.act_view_log.setIcon(theme.icon("dialog-error"))
                if hasattr(self, 'btn_quick_fix'):
                    self.btn_quick_fix.show()

    def stop_daemon(self):
        try:
            if self.daemon_proc is not None:
                try:
                    _terminate_daemon_pid(self.daemon_proc.pid)
                    self.daemon_proc.wait(timeout=0.5)
                except Exception:
                    pass
                self.daemon_proc = None
            else:
                _terminate_daemon_pid(_pid_file_pid())
            common.DAEMON_PROC = None
            try:
                PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            self.update_daemon_status()
        except Exception:
            pass

    def _live_daemon_pid(self):
        if self.daemon_proc is not None and self.daemon_proc.poll() is None:
            return self.daemon_proc.pid
        return _pid_file_pid()

    def request_daemon_reload(self):
        """Profili motoru durdurmadan tazeler (SIGUSR1)."""
        pid = self._live_daemon_pid()
        if pid is None:
            return False
        try:
            os.kill(pid, signal.SIGUSR1)
            return True
        except Exception:
            return False

    def apply_profile_to_daemon(self):
        if getattr(self, "is_manually_stopped", False):
            return
        # Düzenleme/kayıt modunda motor bilinçli olarak kapalıdır; çıkışta açılır.
        if getattr(self, "was_editor_daemon_running", False) or \
                getattr(self, "was_recording_daemon_running", False):
            return
        if self.is_daemon_running() and self.request_daemon_reload():
            self.show_autosave_banner(T("Makro motoru yeniden başlatılmadan güncellendi."))
            return
        self.restart_daemon(show_message=False)

    def restart_daemon(self, show_message=False, force=False):
        # STOP'tan sonra yalnızca açık "Yeniden Başlat" isteği motoru açar.
        if self.is_manually_stopped and not force:
            self.update_daemon_status()
            return False
        self.is_manually_stopped = False
        self.lbl_stopped.hide()
        self.stop_restart_watch()
        if hasattr(self, "btn_restart_after_stop"):
            self.btn_restart_after_stop.setEnabled(False)

        common.DAEMON_BIN, common.PROFILE_PATH = common.locate_paths()
        try:
            if self.daemon_proc is not None:
                try:
                    _terminate_daemon_pid(self.daemon_proc.pid)
                    self.daemon_proc.wait(timeout=0.5)
                except Exception:
                    pass
                self.daemon_proc = None
            else:
                # Yalnızca pidfile ile doğrulanmış kendi motorumuz sonlandırılır.
                _terminate_daemon_pid(_pid_file_pid())
            try:
                PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass

            if not common.DAEMON_BIN or not common.DAEMON_BIN.exists():
                cargo_dir = SCRIPT_DIR if (SCRIPT_DIR / "Cargo.toml").exists() else None

                if cargo_dir and shutil.which("cargo"):
                    self.status_badge.setText(T("Motor derleniyor..."))
                    theme.set_state(self.status_badge, "info")
                    QApplication.processEvents()
                    try:
                        subprocess.run(["cargo", "build", "--release"], cwd=cargo_dir, check=False)
                        built = cargo_dir / "target" / "release" / "macrostat-daemon"
                        if built.exists():
                            shutil.copy2(built, SCRIPT_DIR / "macrostat-daemon")
                            os.chmod(SCRIPT_DIR / "macrostat-daemon", 0o755)
                        common.DAEMON_BIN, common.PROFILE_PATH = common.locate_paths()
                    except Exception:
                        pass

            if not common.DAEMON_BIN or not common.DAEMON_BIN.exists():
                if show_message:
                    QMessageBox.warning(self, T("Motor Bulunamadı"), T("Lütfen terminalde 'cargo build --release' komutunu çalıştırın."))
                self.update_daemon_status()
                return

            log_f = open_rotated_log()
            try:
                self._daemon_log_offset = LOG_FILE.stat().st_size
            except OSError:
                self._daemon_log_offset = 0
            self.daemon_proc = subprocess.Popen(
                [str(common.DAEMON_BIN.resolve()), str(common.PROFILE_PATH.resolve())],
                cwd=str(SCRIPT_DIR),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            log_f.close()
            common.DAEMON_PROC = self.daemon_proc
            try:
                PID_FILE.write_text(str(self.daemon_proc.pid), encoding="utf-8")
            except OSError:
                pass

            if show_message:
                time.sleep(0.3)
                self.failed_status_checks = 0
                self.update_daemon_status()
                QMessageBox.information(self, T("Başarılı"), T("Makro motoru başlatıldı."))
            else:
                QTimer.singleShot(350, self.update_daemon_status)
        except Exception as e:
            if show_message:
                QMessageBox.critical(self, T("Hata"), str(e))

    def start_restart_watch(self):
        """STOP sonrası atanmış tuşu dinleyen hafif izleyiciyi başlatır."""
        if self.restart_watch_proc is not None:
            if getattr(self, "_restart_watch_key", None) == self.restart_key:
                return
            # Tuş değişti: eski izleyici yeni tuşu dinlemez, yenisiyle değiştirilir.
            self.stop_restart_watch()
        common.DAEMON_BIN, common.PROFILE_PATH = common.locate_paths()
        if not common.DAEMON_BIN or not common.DAEMON_BIN.exists():
            return
        command = common.restart_watch_command(common.DAEMON_BIN, self.restart_key)
        proc = QProcess(self)
        proc.setProgram(command[0])
        proc.setArguments(command[1:])
        proc.finished.connect(self._restart_watch_finished)
        proc.errorOccurred.connect(lambda _err: self.stop_restart_watch())
        self.restart_watch_proc = proc
        self._restart_watch_key = self.restart_key
        proc.start()

    def stop_restart_watch(self):
        proc = self.restart_watch_proc
        self.restart_watch_proc = None
        self._restart_watch_key = None
        if proc is None:
            return
        try:
            # Bilinçli durdurulan izleyicinin `finished` sinyali hata banner'ı üretmesin.
            proc.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            if proc.state() != QProcess.ProcessState.NotRunning:
                proc.terminate()
        except Exception:
            pass
        proc.deleteLater()

    def _restart_watch_finished(self, exit_code, _exit_status):
        proc = self.restart_watch_proc
        if proc is None:
            # Zaten durdurulmuş (elle yeniden başlatma/kapanış) izleyicinin geç gelen çıkışı.
            return
        self.restart_watch_proc = None
        self._restart_watch_key = None
        proc.deleteLater()
        if exit_code == common.RESTART_WATCH_EXIT_CODE:
            self.show_autosave_banner(T(
                "Yeniden başlatma tuşuna basıldı; makro motoru açılıyor."))
            self.restart_daemon(show_message=False, force=True)
        elif exit_code not in (0, None):
            self.show_autosave_banner(T(
                "Yeniden başlatma tuşu dinlenemedi (kod {}).").format(exit_code))

    def restart_after_stop(self):
        """STOP sonrası motoru düğmeyle yeniden başlatır."""
        self.stop_restart_watch()
        self.restart_daemon(show_message=False, force=True)
        if self.is_daemon_running():
            self.show_autosave_banner(T("Makro motoru yeniden başlatıldı."))

    def trigger_panic(self):
        try:
            self.is_manually_stopped = True
            self.lbl_stopped.show()
            self.stop_daemon()
            self.status_badge.setText(T("Motor Durduruldu (STOP)"))
            theme.set_state(self.status_badge, "error")
            self.btn_restart_after_stop.setEnabled(True)
            self.start_restart_watch()
            self.show_autosave_banner(T(
                "STOP Tetiklendi! Motor 'Yeniden Başlat' düğmesine veya {} tuşuna "
                "basılana dek kapalı kalacaktır.").format(self.restart_key))
        except Exception:
            pass

    def closeEvent(self, event):
        self.stop_restart_watch()
        if getattr(self, "recording_active", False):
            self.recording_active = False
            self.releaseKeyboard()
        mouse_proc = getattr(self, "_mouse_record_proc", None)
        if mouse_proc is not None:
            mouse_proc.terminate()
            mouse_proc.waitForFinished(1500)
        if not getattr(self, "_force_close", False) and not self.confirm_discard_editor_changes():
            event.ignore()
            return
        try:
            self.status_timer.stop()
        except Exception:
            pass
        common.cleanup_daemon()
        event.accept()
