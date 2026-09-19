"""Asynchronous update checks and explicit, cancellable installation."""
from __future__ import annotations

from pathlib import Path
import shutil
import threading

from PySide6.QtCore import QObject, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QProgressDialog, QPushButton, QVBoxLayout

from config.settings import application_root, save_settings
from config.version import BuildInfo
from gui.sizing import resize_dialog_to_content
from updater.release import Release, ReleaseClient, UpdateError
from updater.service import cleanup_helper, prepare, start_helper
from updater.transaction import WORK, discard_operation, read_json, safe_tree
from updater.windows import InstallationLock


class UpdateWorker(QThread):
    progress = Signal(int, int)

    def __init__(self, action, parent=None) -> None:
        super().__init__(parent)
        self.action = action
        self.cancel = threading.Event()
        self.result = None
        self.error = None

    def run(self) -> None:
        try:
            self.result = self.action(self.cancel, self.progress.emit)
        except Exception as exc:
            self.error = exc.code if isinstance(exc, UpdateError) else (
                "permissions" if isinstance(exc, PermissionError) else "install")


class UpdateOffer(QDialog):
    def __init__(self, window, current: str, release: Release) -> None:
        super().__init__(window)
        t = window.t
        self.setWindowTitle(t("update_title"))
        self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self)
        label = QLabel(t("update_available").format(current, release.version))
        label.setWordWrap(True)
        label.setTextFormat(Qt.PlainText)
        layout.addWidget(label)
        notes = QPushButton(t("update_notes"))
        notes.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release.url)))
        layout.addWidget(notes)
        install = QPushButton(t("update_now"))
        install.setObjectName("primaryButton")
        install.clicked.connect(self.accept)
        layout.addWidget(install)
        later = QPushButton(t("update_later"))
        later.clicked.connect(self.reject)
        later.setDefault(True)
        layout.addWidget(later)
        resize_dialog_to_content(self)


class UpdateController(QObject):
    def __init__(self, window, info: BuildInfo) -> None:
        super().__init__(window)
        self.window, self.info = window, info
        self.root = application_root()
        self.worker = None
        self.progress_dialog = None
        self.offer = None
        self.operation = None
        self.helper = None
        self.helper_directory = None
        self.lock = None
        self.close_pending = False
        self.handing_off = False
        self.manual = False
        self.cleanup_attempts = 0
        self.mode = ""
        self.action = QAction(window)
        self.action.triggered.connect(lambda: self.check(True))
        self.menu = window.menuBar().addMenu("")
        self.menu.addAction(self.action)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self._poll_helper)
        self.retranslate()
        if info.update_enabled:
            QTimer.singleShot(1500, lambda: self.check(False))
        QTimer.singleShot(0, self._show_result)

    def retranslate(self) -> None:
        self.menu.setTitle(self.window.t("update_menu"))
        self.action.setText(self.window.t("update_check"))

    def _show_result(self) -> None:
        if not self.info.update_enabled:
            return
        self._cleanup_helper()
        result = self.root / WORK / "result.json"
        try:
            if result.exists():
                code = read_json(result).get("code", "install")
                result.unlink()
                self.window.statusBar().showMessage(self.window.t("update_" + code), 30000)
        except (OSError, UpdateError):
            self.window.statusBar().showMessage(self.window.t("update_recovery"), 30000)

    def _cleanup_helper(self) -> None:
        self.cleanup_attempts += 1
        if not cleanup_helper(self.root) and self.cleanup_attempts < 10:
            QTimer.singleShot(2000, self._cleanup_helper)

    def check(self, manual: bool) -> None:
        if self.worker or self.helper or self.offer:
            return
        if not self.info.update_enabled:
            if manual:
                QMessageBox.information(self.window, self.window.t("update_title"), self.window.t("update_development"))
            return
        self.manual = manual
        self.mode = "check"
        self.window.statusBar().showMessage(self.window.t("update_checking"))
        self._run(lambda cancel, progress: ReleaseClient().latest(self.info.version, cancel))

    def _run(self, action) -> None:
        self.action.setEnabled(False)
        self.worker = UpdateWorker(action, self)
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _progress(self, done: int, total: int) -> None:
        if self.progress_dialog and total:
            self.progress_dialog.setRange(0, 100)
            self.progress_dialog.setValue(min(99, int(done * 100 / total)))
            if done == total:
                self.progress_dialog.setLabelText(self.window.t("update_verifying"))

    def _finished(self) -> None:
        worker = self.worker
        self.worker = None
        result, error = worker.result, worker.error
        if worker.cancel.is_set():
            error = "cancelled"
        worker.deleteLater()
        if self.mode == "prepare" and result is not None and (error or self.close_pending):
            try:
                discard_operation(self.root, result)
            except (OSError, UpdateError):
                pass
        if self.close_pending:
            if self.lock:
                self.lock.close()
                self.lock = None
            self._close_progress()
            self.window.close()
            return
        if error:
            self._finish_error(error)
            return
        if self.mode == "check":
            self.action.setEnabled(True)
            if result is None:
                self.window.statusBar().showMessage(self.window.t("update_current"), 15000)
                if self.manual:
                    QMessageBox.information(self.window, self.window.t("update_title"), self.window.t("update_current"))
            else:
                self._offer(result)
        else:
            self.operation = result
            if self.lock:
                self.lock.close()
                self.lock = None
            try:
                self.helper, self.helper_directory = start_helper(
                    self.root, ["--job", str(self.operation / "job.json")])
                self.progress_dialog.setRange(0, 0)
                self.progress_dialog.setLabelText(self.window.t("update_verifying"))
                self.poll_timer.start()
            except (OSError, UpdateError):
                self._finish_error("install")

    def _offer(self, release: Release) -> None:
        if self.close_pending:
            return
        if QApplication.activeModalWidget() is not None:
            QTimer.singleShot(500, lambda: self._offer(release))
            return
        self.window.statusBar().showMessage(self.window.t("update_available").format(self.info.version, release.version))
        self.offer = UpdateOffer(self.window, self.info.version, release)
        self.offer.accepted.connect(lambda: self._install(release))
        self.offer.finished.connect(self._offer_closed)
        self.offer.open()

    def _offer_closed(self, result: int) -> None:
        if self.offer:
            self.offer.deleteLater()
            self.offer = None

    def _install(self, release: Release) -> None:
        if self.worker or self.helper:
            return
        try:
            self.lock = InstallationLock(self.root, "update").acquire()
        except UpdateError as exc:
            self._finish_error(exc.code)
            return
        self.mode = "prepare"
        self.manual = True
        self.progress_dialog = QProgressDialog(self.window.t("update_downloading"),
                                               self.window.t("update_cancel"), 0, 0, self.window)
        self.progress_dialog.setWindowTitle(self.window.t("update_title"))
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.setAutoReset(False)
        self.progress_dialog.canceled.connect(self.cancel)
        resize_dialog_to_content(self.progress_dialog)
        self.progress_dialog.show()
        self._run(lambda cancel, progress: prepare(self.root, release, cancel, progress))

    def cancel(self) -> None:
        if self.worker:
            self.worker.cancel.set()
        if self.operation and self.helper:
            (self.operation / "cancel").touch()
        if self.progress_dialog:
            self.progress_dialog.setLabelText(self.window.t("update_cancelling"))
            self.progress_dialog.setCancelButton(None)

    def _poll_helper(self) -> None:
        try:
            error = self.operation / "error.json"
            if error.exists():
                if self.helper.poll() is not None:
                    self._finish_error(read_json(error).get("code", "install"))
                return
            if self.helper.poll() is not None:
                self._finish_error("install")
                return
            if (self.operation / "cancel").exists():
                return
            if (self.operation / "ready.json").exists():
                # A modal progress dialog excludes concurrent certificate,
                # export and CRUD dialogs during the entire handoff.
                save_settings(self.window.settings)
                self.handing_off = True
                self.poll_timer.stop()
                self._close_progress()
                self.window.close()
        except (OSError, UpdateError):
            self.cancel()

    def _close_progress(self) -> None:
        if self.progress_dialog:
            self.progress_dialog.canceled.disconnect(self.cancel)
            self.progress_dialog.close()
            self.progress_dialog.deleteLater()
            self.progress_dialog = None

    def _finish_error(self, code: str) -> None:
        self.poll_timer.stop()
        if self.lock:
            self.lock.close()
            self.lock = None
        self._close_progress()
        if self.helper_directory and (not self.helper or self.helper.poll() is not None):
            try:
                safe_tree(self.helper_directory)
                shutil.rmtree(self.helper_directory)
            except OSError:
                pass
        if self.operation:
            try:
                discard_operation(self.root, self.operation)
            except (OSError, UpdateError):
                pass
        self.helper = None
        self.operation = None
        self.helper_directory = None
        self.action.setEnabled(True)
        text = self.window.t("update_" + code)
        if text == "update_" + code:
            text = self.window.t("update_install")
        self.window.statusBar().showMessage(text, 30000)
        if self.close_pending:
            self.window.close()
        elif self.manual and code != "cancelled":
            QMessageBox.warning(self.window, self.window.t("update_title"), text)

    def can_close(self) -> bool:
        if self.handing_off:
            return True
        if self.worker or self.helper:
            self.close_pending = True
            self.cancel()
            return False
        return True
