"""The live ISO's graphical ZFS installation wizard (native Wayland/Qt)."""

import json
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from model import KEYBOARDS, LOCALES, TIMEZONES, validate


class Installer(QWidget):
    pages = ["Welcome", "Storage", "Account", "Review", "Installing", "Complete"]

    def __init__(self):
        super().__init__()
        self.busy = False
        self.request = None
        self.setMinimumSize(840, 650)
        self.resize(960, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        title = QLabel("NixOS  /  ZFS")
        title.setFont(QFont("sans-serif", 24, QFont.Weight.Bold))
        layout.addWidget(title)
        layout.addWidget(QLabel("Umbriel + Noctalia v5 · CachyOS kernel"))
        self.steps = QLabel()
        layout.addWidget(self.steps)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #f38ba8;")
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        self.back = QPushButton("戻る (&B)")
        self.back.clicked.connect(lambda: self.show_page(self.stack.currentIndex() - 1))
        buttons.addWidget(self.back)
        buttons.addStretch()
        self.next = QPushButton("次へ (&N)")
        self.next.setDefault(True)
        self.next.clicked.connect(self.advance)
        buttons.addWidget(self.next)
        layout.addLayout(buttons)
        self.make_welcome()
        self.make_storage()
        self.make_account()
        self.make_review()
        self.make_progress()
        self.make_complete()
        self.show_page(0)

    def page(self, heading, description):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(heading)
        label.setFont(QFont("sans-serif", 18, QFont.Weight.Bold))
        layout.addWidget(label)
        text = QLabel(description)
        text.setWordWrap(True)
        layout.addWidget(text)
        self.stack.addWidget(widget)
        return layout

    def make_welcome(self):
        layout = self.page("NixOSへようこそ", "このウィザードで、UmbrielとNoctalia v5を使うNixOSをZFSへインストールします。")
        layout.addWidget(QLabel("1. ネットワークに接続\n2. インストール先を選択\n3. ユーザーと地域を設定\n4. ディスク消去を確認してインストール"))
        network = QPushButton("ネットワーク接続を設定")
        network.clicked.connect(lambda: QProcess.startDetached("nm-connection-editor", []))
        layout.addWidget(network, alignment=Qt.AlignmentFlag.AlignLeft)
        text = QLabel("必要条件: UEFI起動、32 GiB以上のディスク、インターネット接続。\n選択したディスク全体を消去します。既存データの保持・暗号化・ミラー・デュアルブートには対応していません。")
        text.setWordWrap(True)
        layout.addWidget(text)
        if not Path("/sys/firmware/efi").is_dir():
            warning = QLabel("BIOSモードで起動しています。インストールするにはUSB/ISOをUEFIモードで起動し直してください。")
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #fab387;")
            layout.addWidget(warning)
        layout.addStretch()

    def make_storage(self):
        layout = self.page("インストール先", "ディスク全体をZFSとして使用します。容量、モデル、シリアル番号を確認してください。")
        self.disks = QComboBox()
        label = QLabel("ディスク (&D)")
        label.setBuddy(self.disks)
        layout.addWidget(label)
        layout.addWidget(self.disks)
        refresh = QPushButton("ディスクを再検出 (&R)")
        refresh.clicked.connect(self.refresh_disks)
        layout.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(QLabel("構成: FAT32 EFI 1 GiB + ZFS rpool\nデータセット: /、/home、/nix\n圧縮: zstd / ブートローダー: systemd-boot"))
        layout.addStretch()

    def refresh_disks(self):
        self.disks.clear()
        try:
            data = json.loads(subprocess.check_output(["lsblk", "--json", "--bytes", "-o", "PATH,TYPE,SIZE,MODEL,SERIAL,RO,MOUNTPOINTS,MAJ:MIN"], text=True, timeout=10))
            def in_use(device):
                return any(device.get("mountpoints") or []) or device["type"] not in ("disk", "part") or any(in_use(child) for child in device.get("children", []))
            for disk in data["blockdevices"]:
                if disk["type"] != "disk" or disk["ro"] or disk["size"] < 32 * 1024**3 or in_use(disk):
                    continue
                disk["identity"] = subprocess.check_output(["lsblk", "-bdnro", "MAJ:MIN,SIZE,SERIAL", disk["path"]], text=True, timeout=10).strip()
                text = f"{disk['path']}  ·  {disk['size'] / 1024**3:.1f} GiB  ·  {(disk.get('model') or '').strip()}  ·  {disk.get('serial') or ''}"
                self.disks.addItem(text, disk)
            if not self.disks.count():
                self.error.setText("使用可能な32 GiB以上の未マウントディスクが見つかりません。")
        except (OSError, ValueError, subprocess.SubprocessError):
            self.error.setText("ディスク情報を取得できませんでした。再検出してください。")

    def make_account(self):
        layout = self.page("ユーザーと地域", "管理者権限を使えるユーザーを作成します。このパスワードでログインし、sudoを使います。")
        form = QFormLayout()
        self.hostname = QLineEdit("nixos")
        self.username = QLineEdit("nixos")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_password = QLineEdit()
        self.confirm_password.setEchoMode(QLineEdit.EchoMode.Password)
        for caption, field in (("ホスト名 (&H)", self.hostname), ("ユーザー名 (&U)", self.username), ("パスワード (&P)", self.password), ("パスワードを再入力 (&C)", self.confirm_password)):
            form.addRow(caption, field)
        self.locale = QComboBox()
        for label, value in LOCALES.items():
            self.locale.addItem(label, value)
        self.keyboard = QComboBox()
        for label, value in KEYBOARDS.items():
            self.keyboard.addItem(label, value)
        self.timezone = QComboBox()
        self.timezone.addItems(TIMEZONES)
        form.addRow("言語 (&L)", self.locale)
        form.addRow("キーボード (&K)", self.keyboard)
        form.addRow("タイムゾーン (&T)", self.timezone)
        layout.addLayout(form)
        layout.addWidget(QLabel("パスワードは8文字以上。rootアカウントはロックし、作成したユーザーからsudoで管理します。"))
        layout.addStretch()

    def make_review(self):
        layout = self.page("インストール内容を確認", "ここで開始するまでは、ディスクを変更しません。")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.erase = QCheckBox("選択したディスクの全データ消去に同意する (&E)")
        layout.addWidget(self.erase)
        self.confirm_disk = QLineEdit()
        label = QLabel("表示された確認文字列を入力 (&D)")
        label.setBuddy(self.confirm_disk)
        layout.addWidget(label)
        layout.addWidget(self.confirm_disk)
        layout.addStretch()

    def make_progress(self):
        layout = self.page("インストール中", "完了まで電源を切らず、インターネットへの接続を保ってください。")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status = QLabel()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        layout.addWidget(self.progress)
        layout.addWidget(self.status)
        layout.addWidget(self.log, 1)

    def make_complete(self):
        layout = self.page("インストールが完了しました", "USB/ISOを取り外して再起動してください。作成したユーザーで、Umbriel + Noctalia v5のデスクトップにログインできます。")
        reboot = QPushButton("再起動 (&R)")
        reboot.clicked.connect(lambda: QProcess.startDetached("sudo", ["-n", "systemctl", "reboot"]))
        layout.addWidget(reboot, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()

    def show_page(self, index):
        self.error.clear()
        self.stack.setCurrentIndex(index)
        self.setWindowTitle("NixOS Installer — " + self.pages[index])
        self.steps.setText("  →  ".join(("● " if n == index else "") + text for n, text in enumerate(["開始", "ディスク", "ユーザー", "確認", "処理", "完了"])))
        self.back.setVisible(0 < index < 4)
        self.next.setVisible(index < 4)
        self.next.setText("インストール開始 (&I)" if index == 3 else "次へ (&N)")
        self.next.setEnabled(index != 0 or Path("/sys/firmware/efi").is_dir())
        if index == 1:
            self.refresh_disks()
        if index == 2:
            self.hostname.setFocus()
        print("GUI_PAGE " + self.pages[index], flush=True)

    def collect(self):
        disk = self.disks.currentData()
        if not disk:
            raise ValueError("インストール先のディスクを選択してください。")
        return {
            "disk": disk["path"], "identity": disk["identity"],
            "hostname": self.hostname.text(), "username": self.username.text(),
            "password": self.password.text(), "locale": self.locale.currentData(),
            "keyboard": self.keyboard.currentData(), "timezone": self.timezone.currentText(),
            "confirmation": self.confirm_disk.text(),
        }

    def advance(self):
        index = self.stack.currentIndex()
        try:
            if index == 1 and not self.disks.currentData():
                raise ValueError("インストール先のディスクを選択してください。")
            if index == 2:
                request = self.collect()
                if request["password"] != self.confirm_password.text():
                    raise ValueError("パスワードが一致しません。")
                request["confirmation"] = "ERASE " + request["disk"]
                validate(request)
                self.confirm_disk.clear()
                self.erase.setChecked(False)
                self.summary.setText(f"消去するディスク: {self.disks.currentText()}\nホスト名: {request['hostname']}\nユーザー: {request['username']}\nデスクトップ: Umbriel + Noctalia v5\nシステム: CachyOS + ZFS\n言語: {self.locale.currentText()} / キーボード: {self.keyboard.currentText()}\n\n確認文字列: ERASE {request['disk']}")
            if index == 3:
                if not self.erase.isChecked():
                    raise ValueError("ディスク消去への同意を確認してください。")
                request = validate(self.collect())
                self.start_install(request)
                return
            self.show_page(index + 1)
        except ValueError as error:
            self.error.setText(str(error))

    def start_install(self, request):
        self.busy = True
        self.show_page(4)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.pending = ""
        self.process.start("sudo", ["-n", sys.executable, str(Path(__file__).with_name("backend.py"))])
        if not self.process.waitForStarted(10000):
            return
        self.process.write(json.dumps(request).encode())
        self.process.closeWriteChannel()
        self.password.clear()
        self.confirm_password.clear()
        request.clear()

    def read_output(self):
        self.pending += bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            if line.startswith("@@PHASE:"):
                _, percent, message = line.split(":", 2)
                self.progress.setValue(int(percent))
                self.status.setText(message)
            self.log.appendPlainText(line)

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.busy = False
            self.error.setText("インストール処理を開始できませんでした。")

    def finished(self, code, status):
        self.read_output()
        self.busy = False
        if code == 0 and status == QProcess.ExitStatus.NormalExit:
            self.show_page(5)
            print("GUI_INSTALL_SUCCESS", flush=True)
        else:
            self.error.setText("インストールに失敗しました。上のログを確認してください。作成済みの領域が /mnt に残っている場合があります。")
            print("GUI_INSTALL_FAILED", flush=True)

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("QWidget { background: #1e1e2e; color: #cdd6f4; font-size: 15px; } QPushButton { background: #313244; padding: 10px 20px; border-radius: 7px; } QPushButton:focus, QPushButton:hover { background: #45475a; } QLineEdit, QComboBox, QPlainTextEdit { background: #181825; padding: 8px; border: 1px solid #585b70; border-radius: 5px; } QProgressBar { text-align: center; } QProgressBar::chunk { background: #89b4fa; }")
    window = Installer()
    window.show()
    sys.exit(app.exec())
