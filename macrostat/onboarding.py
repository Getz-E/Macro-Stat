# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""İlk kurulum sihirbazı: durum kontrolü, dar udev izni ve motor başlatma."""

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWizard, QWizardPage,
)

from . import common, theme
from .common import T


def uaccess_installed():
    """udev kuralı oturum sahibine `uaccess` ile yazma izni veriyor mu?

    Geniş `input` grubu üyeliği artık istenmez; oturum açan kullanıcı
    `/dev/uinput` ve `event*` aygıtlarına doğrudan erişebilmelidir.
    """
    return common.udev_rule_installed() and os.access("/dev/uinput", os.W_OK)


def uinput_writable():
    """`/dev/uinput` var ve yazılabilir mi?"""
    path = Path("/dev/uinput")
    return path.exists() and os.access(path, os.W_OK)


def daemon_available():
    binary = getattr(common, "DAEMON_BIN", None)
    return bool(binary and Path(binary).is_file())


def collect_checks():
    """Sihirbaz ve özet için (anahtar, başarılı, başlık, açıklama) listesi."""
    return [
        ("uinput", uinput_writable(),
         T("Donanım Erişimi (/dev/uinput)"),
         T("Motorun tuş gönderebilmesi için /dev/uinput yazılabilir olmalıdır.")),
        ("uaccess", uaccess_installed(),
         T("Oturum izni (uaccess)"),
         T("udev kuralı yalnızca oturum sahibine yazma izni verir; "
           "geniş 'input' grubu gerekmez.")),
        ("udev", common.udev_rule_installed(),
         T("udev kuralı kurulu"),
         T("Giriş aygıtlarına dar kapsamlı izinler tanımlar (chmod 666 kullanılmaz).")),
        ("daemon", daemon_available(),
         T("Motor ikilisi bulundu"),
         T("'cargo build --release' ile derlenmiş motor ikilisi gerekir.")),
    ]


class StatusPage(QWizardPage):
    """Adım 1: ortam kontrolü; her satır ✓/✗ ve tek cümle açıklama."""

    def __init__(self):
        super().__init__()
        self.setTitle(T("Sistem Durumu"))
        self.setSubTitle(T("Kuruluma başlamadan önce ortamınızı kontrol edelim."))
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._rows = {}
        for key, _ok, title, description in collect_checks():
            row = QHBoxLayout()
            row.setSpacing(10)
            mark = QLabel("…")
            mark.setObjectName("onboardingStatus")
            mark.setFixedWidth(18)
            row.addWidget(mark, 0)
            text = QVBoxLayout()
            text.setSpacing(0)
            title_label = QLabel(title)
            title_label.setObjectName("onboardingTitle")
            detail = QLabel(description)
            detail.setObjectName("onboardingDetail")
            detail.setWordWrap(True)
            text.addWidget(title_label)
            text.addWidget(detail)
            row.addLayout(text, 1)
            layout.addLayout(row)
            self._rows[key] = (mark, title_label)

        layout.addStretch()
        row = QHBoxLayout()
        refresh = QPushButton(T("Durumu Yenile"))
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        row.addStretch()
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        for key, ok, _title, _description in collect_checks():
            mark, title_label = self._rows[key]
            mark.setText("✓" if ok else "✗")
            theme.set_state(mark, "ok" if ok else "error")

    def initializePage(self):
        self.refresh()

    def isComplete(self):
        return True


class PermissionsPage(QWizardPage):
    """Adım 2: onay kutusu işaretlenmeden dar udev kuralı kurulmaz."""

    def __init__(self):
        super().__init__()
        self.setTitle(T("İzinleri Düzelt"))
        self.setSubTitle(T("Yalnızca giriş aygıtları için udev kuralı kurulur; geniş chmod 666 kullanılmaz."))
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info = QLabel(T(
            "Kurulacak kural /dev/uinput ve event aygıtlarına yalnızca oturum "
            "açan kullanıcıya erişim verir (MODE=0660, uaccess). Geniş 'input' "
            "grubu üyeliği gerekmez; kural sonraki oturumda da geçerlidir."))
        info.setWordWrap(True)
        layout.addWidget(info)

        # `uaccess` ACL'i uygulama başına değil, oturum açan kullanıcı
        # genelinde uygulanır; kurulum öncesi bu sınır açıkça bildirilir.
        scope = QLabel(T(
            "Gizlilik notu: bu izin kullanıcı genelindedir, uygulama başına "
            "değildir. Oturum açıkken hesabınızda çalışan her program "
            "input/event* aygıtlarını okuyabilir ve /dev/uinput üzerine "
            "yazabilir. udev tek başına süreç bazlı yalıtım sağlayamaz; "
            "bu ayrıcalıklı bir aracı gerektirir."))
        scope.setObjectName("onboardingDetail")
        scope.setWordWrap(True)
        layout.addWidget(scope)

        self.chk_consent = QCheckBox(
            T("udev kuralını kurmak için yönetici izni istemini onaylıyorum."))
        self.chk_consent.toggled.connect(lambda checked: self.btn_install.setEnabled(checked))
        layout.addWidget(self.chk_consent)

        row = QHBoxLayout()
        self.btn_install = QPushButton(T("İzinleri Kur"))
        theme.set_variant(self.btn_install, "primary")
        self.btn_install.setEnabled(False)
        self.btn_install.clicked.connect(self.install)
        row.addWidget(self.btn_install)
        row.addStretch()
        layout.addLayout(row)

        self.lbl_result = QLabel("")
        self.lbl_result.setObjectName("onboardingResult")
        self.lbl_result.setWordWrap(True)
        layout.addWidget(self.lbl_result)

        # pkexec/sudo bulunmayan sistemlerde sihirbaz çıkmaz sokak olmasın:
        # kullanıcı bilinçli olarak atlayıp izni sonra kurabilir.
        self.chk_skip = QCheckBox(T(
            "İzinleri şimdilik atla; daha sonra Sistem sayfasından kurabilirim "
            "(izin kurulana kadar motor çalışmaz)."))
        self.chk_skip.toggled.connect(lambda _checked: self.completeChanged.emit())
        layout.addWidget(self.chk_skip)
        layout.addStretch()

    def initializePage(self):
        if common.udev_rule_installed():
            self.lbl_result.setText(T("Kural zaten kurulu; bu adımı atlayabilirsiniz."))
            theme.set_state(self.lbl_result, "ok")
        else:
            self.lbl_result.clear()

    def isComplete(self):
        return common.udev_rule_installed() or self.chk_skip.isChecked()

    def install(self):
        if not self.chk_consent.isChecked():
            return
        self.btn_install.setEnabled(False)
        QApplication.processEvents()
        ok, detail = common.install_udev_rule()
        self.btn_install.setEnabled(True)
        if ok:
            self.lbl_result.setText(
                T("İzinler başarıyla kuruldu. Kural yeni oturumda etkinleşir."))
            theme.set_state(self.lbl_result, "ok")
        else:
            self.lbl_result.setText(T("Kurulum başarısız: {}").format(detail))
            theme.set_state(self.lbl_result, "error")
        self.completeChanged.emit()


class ReadyPage(QWizardPage):
    """Adım 3: özet ve motoru başlatma onayı."""

    def __init__(self):
        super().__init__()
        self.setTitle(T("Hazır"))
        self.setSubTitle(T("Kurulum tamamlandı. Motoru şimdi başlatabilirsiniz."))
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.summary = QLabel("")
        self.summary.setObjectName("onboardingResult")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.chk_start = QCheckBox(T("Motoru şimdi başlat"))
        self.chk_start.setChecked(True)
        layout.addWidget(self.chk_start)
        layout.addStretch()

    def initializePage(self):
        checks = collect_checks()
        missing = [title for _key, ok, title, _d in checks if not ok]
        if missing:
            self.summary.setText(
                T("Eksik görünen adımlar: {}").format(", ".join(missing)))
            theme.set_state(self.summary, "info")
        else:
            self.summary.setText(T("Tüm kontroller başarılı."))
            theme.set_state(self.summary, "ok")

    def start_engine_requested(self):
        return self.chk_start.isChecked()


class OnboardingWizard(QWizard):
    """Üç adımlı ilk kurulum sihirbazı."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("MacroStat Kurulum"))
        self.resize(620, 460)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        self.status_page = StatusPage()
        self.permissions_page = PermissionsPage()
        self.ready_page = ReadyPage()
        self.addPage(self.status_page)
        self.addPage(self.permissions_page)
        self.addPage(self.ready_page)

        self.setButtonText(QWizard.WizardButton.BackButton, T("Geri"))
        self.setButtonText(QWizard.WizardButton.NextButton, T("İleri"))
        self.setButtonText(QWizard.WizardButton.FinishButton, T("Bitir"))
        self.setButtonText(QWizard.WizardButton.CancelButton, T("İptal"))

    def accept(self):
        data = common.load_settings()
        data["onboarding_completed"] = True
        common.save_settings(data)
        super().accept()

    def start_engine_requested(self):
        return self.ready_page.start_engine_requested()
