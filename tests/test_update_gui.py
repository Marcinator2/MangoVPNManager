from __future__ import annotations

from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from config.settings import AppSettings
from gui.i18n import Translator, TRANSLATIONS
from updater.release import Release


@pytest.fixture
def gui(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
    from gui.update_controller import UpdateController
    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.t = Translator("en")
    window.settings = AppSettings()
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[2]))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[2]))
    info = SimpleNamespace(version="v1.0.0", update_enabled=False)
    controller = UpdateController(window, info)
    controller.root = tmp_path
    yield app, window, controller, messages
    if controller.worker:
        controller.worker.cancel.set()
        controller.worker.wait(3000)
        app.processEvents()
    controller.poll_timer.stop()
    if controller.offer:
        controller.offer.reject()
    window.close()
    window.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("language", ["en", "de"])
def test_update_offer_and_localization(gui, language):
    from gui.update_controller import UpdateOffer
    from PySide6.QtWidgets import QPushButton, QLabel
    app, window, controller, messages = gui
    window.t.set_language(language)
    controller.retranslate()
    assert controller.action.text() == window.t("update_check")
    release = Release("v1.1.0", "https://github.com/Marcinator2/OpenVPN-Manager/releases/tag/v1.1.0", "", "", "", 1)
    dialog = UpdateOffer(window, "v1.0.0", release)
    dialog.show()
    app.processEvents()
    assert "v1.0.0" in dialog.findChild(QLabel).text()
    assert "v1.1.0" in dialog.findChild(QLabel).text()
    assert window.t("update_now") in [button.text() for button in dialog.findChildren(QPushButton)]
    assert dialog.width() <= app.primaryScreen().availableGeometry().width()
    dialog.close()


def test_all_update_messages_have_both_languages():
    english = {key for key in TRANSLATIONS["en"] if key.startswith("update_")}
    german = {key for key in TRANSLATIONS["de"] if key.startswith("update_")}
    assert english == german
    assert all(TRANSLATIONS[lang][key] for lang in ("en", "de") for key in english)


def test_development_manual_check_does_not_contact_network(gui, monkeypatch):
    from gui import update_controller
    _, _, controller, messages = gui
    monkeypatch.setattr(update_controller, "ReleaseClient", lambda: pytest.fail("Network must not be used"))
    controller.check(True)
    assert messages and "packaged stable" in messages[0]
    assert controller.worker is None


def test_worker_does_not_block_gui_and_reports_errors(gui):
    from updater.release import UpdateError
    app, _, controller, messages = gui
    controller.manual = True
    controller.mode = "check"
    barrier = threading.Event()
    def action(cancel, progress):
        barrier.wait(1)
        raise UpdateError("network")
    controller._run(action)
    assert not controller.action.isEnabled()
    app.processEvents()
    assert controller.worker is not None
    barrier.set()
    deadline = time.monotonic() + 3
    while controller.worker and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert controller.worker is None
    assert controller.action.isEnabled()
    assert messages and "connection" in messages[-1]


def test_close_waits_for_worker_cancellation(gui):
    app, _, controller, _ = gui
    started = threading.Event()
    def action(cancel, progress):
        started.set()
        cancel.wait(2)
    controller.mode = "check"
    controller._run(action)
    assert started.wait(1)
    assert not controller.can_close()
    assert controller.worker.cancel.is_set()
    deadline = time.monotonic() + 3
    while controller.worker and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert controller.can_close()


def test_ready_handoff_saves_then_closes_without_cancelling(gui, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QProgressDialog
    from gui import update_controller
    _, window, controller, _ = gui
    operation = tmp_path / "operation"
    operation.mkdir()
    (operation / "ready.json").write_text("{}")
    controller.operation = operation
    controller.helper = SimpleNamespace(poll=lambda: None)
    controller.progress_dialog = QProgressDialog(window)
    controller.progress_dialog.canceled.connect(controller.cancel)
    events = []
    monkeypatch.setattr(update_controller, "save_settings", lambda settings: events.append("saved"))
    monkeypatch.setattr(window, "close", lambda: events.append("closed"))
    controller._poll_helper()
    assert events == ["saved", "closed"]
    assert controller.handing_off
    assert not (operation / "cancel").exists()
    controller.helper = None


def test_cancel_during_helper_preparation_keeps_application_open(gui, tmp_path):
    _, _, controller, _ = gui
    operation = tmp_path / "operation"
    operation.mkdir()
    (operation / "ready.json").write_text("{}")
    controller.operation = operation
    controller.helper = SimpleNamespace(poll=lambda: None)
    controller.cancel()
    controller._poll_helper()
    assert (operation / "cancel").exists()
    assert not controller.handing_off
    controller.helper = None
