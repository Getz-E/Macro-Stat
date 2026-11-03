# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Sistem sekmesi, motor süreç denetimi, izinler ve yedekleme."""

from . import common, theme
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
        btn_fix = QPushButton(T("🛡️ Donanım İzinlerini Otomatik Düzelt (udev)"))
        theme.set_variant(btn_fix, "primary")
        btn_fix.clicked.connect(self.fix_permissions)
        p_box.addWidget(btn_fix)

        btn_ref = QPushButton(T("🔄 Durumu Yenile"))
        btn_ref.clicked.connect(self.refresh_system_status)
        p_box.addWidget(btn_ref)

        btn_restore = QPushButton(T("⏪ Son Yedeği Geri Yükle"))
        btn_restore.clicked.connect(self.restore_last_backup)
        p_box.addWidget(btn_restore)

        layout.addLayout(p_box)
        self.refresh_system_status()

    def restore_last_backup(self):
        backup = common.PROFILE_PATH.with_name(common.PROFILE_PATH.name + ".bak")
        if not backup.exists():
            QMessageBox.warning(self, T("Yedek Geri Yükleme"),
                                T("Yedek dosyası bulunamadı."))
            return
        answer = QMessageBox.question(
            self, T("Yedek Geri Yükleme"),
            T("Yedek geri yüklensin mi? Mevcut profil bu yedekle değiştirilecek."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            raw = backup.read_bytes()
            json.loads(raw.decode("utf-8"))  # geçerlilik denetimi
            tmp = common.PROFILE_PATH.with_name(common.PROFILE_PATH.name + ".restore.tmp")
            with open(tmp, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, common.PROFILE_PATH)
            self.profile_data = self.load_profile()
            common.PANIC_KEY = self.profile_data.get("panicKey") or "KEY_PAUSE"
            self.populate_profile_combo()
            self.refresh_macro_table()
            self.apply_profile_to_daemon()
            self.show_autosave_banner(T("Profil yedeği geri yüklendi."))
        except Exception as e:
            QMessageBox.critical(self, T("Yedek Geri Yükleme"),
                                 T("Yedek okunamadı: ") + str(e))

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
            T("✔ Erişilebilir (Yazma İzni Var)") if uinput_ok
            else T("❌ Erişim Yok (İzin Gerekli)"),
            common.DAEMON_BIN or T("İkili Dosya Bulunamadı (cargo build --release çalıştırın)"),
            common.PROFILE_PATH.resolve() if common.PROFILE_PATH else T("Bulunamadı"),
            common.PANIC_KEY,
            LOG_FILE,
        )
        self.sys_info.setPlainText(guide_text)

    def fix_permissions(self):
        try:
            import getpass
            username = os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
            if not username or not all(c.isalnum() or c in "._-" for c in username):
                raise ValueError(T("Geçersiz kullanıcı adı"))

            # Geniş chmod 666 / setfacl yerine yalnızca udev uaccess + input grubu.
            script = (
                "modprobe uinput 2>/dev/null || true\n"
                "cat > /etc/udev/rules.d/99-cachymacro.rules <<'EOF'\n"
                'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", '
                'OPTIONS+="static_node=uinput", GROUP="input", MODE="0660"\n'
                'SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess", '
                'GROUP="input", MODE="0660"\n'
                "EOF\n"
                "udevadm control --reload-rules\n"
                "udevadm trigger\n"
                f"usermod -aG input {username}\n"
            )
            elevated = ["pkexec", "sh", "-c", script] if shutil.which("pkexec") \
                else ["sudo", "sh", "-c", script]
            result = subprocess.run(elevated)
            if result.returncode != 0:
                raise RuntimeError(T("Yetkilendirme başarısız (çıkış kodu {})").format(result.returncode))
            time.sleep(0.3)
            self.restart_daemon(show_message=False)
            self.refresh_system_status()
            QMessageBox.information(
                self, T("İzinler Düzeltildi"),
                T("udev kuralı kuruldu ve motor başlatıldı.\n"
                  "Grup üyeliği yeni oturumda etkinleşir; sorun sürerse oturumu kapatıp açın."),
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
            self.status_badge.setText(T("🔴 Motor Durduruldu (STOP)"))
            theme.set_state(self.status_badge, "error")
            return
        if getattr(self, "was_editor_daemon_running", False):
            self.status_badge.setText(T("🛑 Düzenleme Modu (Beklemede)"))
            theme.set_state(self.status_badge, "info")
            return
        if self.is_daemon_running():
            self.failed_status_checks = 0
            self.status_badge.setText(T("🟢 Aktif"))
            theme.set_state(self.status_badge, "ok")
            self.btn_view_log.setText("📋")
            self.btn_view_log.setToolTip(T("📋 Günlüğü İncele"))
            theme.set_variant(self.btn_view_log, "")
            if hasattr(self, 'btn_quick_fix'):
                self.btn_quick_fix.hide()
        else:
            # Fiziksel STOP tuşu motoru kapatır; bu durum oturum boyunca korunur.
            if self._daemon_stopped_by_panic():
                self.is_manually_stopped = True
                self.lbl_stopped.show()
                self.status_badge.setText(T("🔴 Motor Durduruldu (STOP)"))
                theme.set_state(self.status_badge, "error")
                if hasattr(self, 'btn_restart_daemon'):
                    theme.set_variant(self.btn_restart_daemon, "success")
                return
            self.failed_status_checks += 1
            if self.failed_status_checks >= 2:
                exit_code = self.daemon_proc.poll() if self.daemon_proc is not None else None
                if exit_code not in (None, 0):
                    self.status_badge.setText(T("🔴 Motor Çöktü (kod {})").format(exit_code))
                else:
                    self.status_badge.setText(T("🔴 Motor Durduruldu"))
                theme.set_state(self.status_badge, "error")
                self.btn_view_log.setText("⚠️")
                self.btn_view_log.setToolTip(T("⚠️ Hatayı İncele"))
                theme.set_variant(self.btn_view_log, "danger")
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
            self.show_autosave_banner(T("♻️ Makro motoru yeniden başlatılmadan güncellendi."))
            return
        self.restart_daemon(show_message=False)

    def restart_daemon(self, show_message=False, force=False):
        # STOP'tan sonra yalnızca açık "Yeniden Başlat" isteği motoru açar.
        if self.is_manually_stopped and not force:
            self.update_daemon_status()
            return False
        self.is_manually_stopped = False
        self.lbl_stopped.hide()
        if hasattr(self, 'btn_restart_daemon'):
            theme.set_variant(self.btn_restart_daemon, "")

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
                    self.status_badge.setText(T("⚙️ Motor derleniyor..."))
                    theme.set_state(self.status_badge, "info")
                    QApplication.processEvents()
                    try:
                        subprocess.run(["cargo", "build", "--release"], cwd=cargo_dir, check=False)
                        built = cargo_dir / "target" / "release" / "cachymacro-daemon"
                        if built.exists():
                            shutil.copy2(built, SCRIPT_DIR / "cachymacro-daemon")
                            os.chmod(SCRIPT_DIR / "cachymacro-daemon", 0o755)
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

    def trigger_panic(self):
        try:
            self.is_manually_stopped = True
            self.lbl_stopped.show()
            self.stop_daemon()
            self.status_badge.setText(T("🔴 Motor Durduruldu (STOP)"))
            theme.set_state(self.status_badge, "error")
            theme.set_variant(self.btn_restart_daemon, "success")
            self.show_autosave_banner(T("🛑 STOP Tetiklendi! Motor 'Yeniden Başlat' butonuna basılana dek kapalı kalacaktır."))
        except Exception:
            pass

    def show_daemon_log(self):
        content = T("Log dosyası henüz oluşmadı.")
        if LOG_FILE.exists():
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                content = T("Log okunamadı: ") + str(e)
        dlg = QDialog(self)
        dlg.setWindowTitle(T("Motor Günlüğü"))
        dlg.resize(600, 400)
        l = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(content)
        l.addWidget(txt)
        dlg.exec()

    def closeEvent(self, event):
        if getattr(self, "recording_active", False):
            self.recording_active = False
            self.releaseKeyboard()
        if not getattr(self, "_force_close", False) and not self.confirm_discard_editor_changes():
            event.ignore()
            return
        try:
            self.status_timer.stop()
        except Exception:
            pass
        common.cleanup_daemon()
        event.accept()
