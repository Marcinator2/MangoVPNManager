from PySide6.QtCore import QSize

from gui.sizing import bounded_dialog_size, button_row_fits


def test_dialog_grows_to_translated_content_width() -> None:
    size = bounded_dialog_size(
        QSize(1080, 600),
        QSize(1920, 1080),
        minimum_width=760,
        minimum_height=620,
    )
    assert size == QSize(1080, 620)


def test_dialog_is_limited_to_available_screen() -> None:
    size = bounded_dialog_size(
        QSize(1600, 1000),
        QSize(1280, 720),
        minimum_width=760,
        minimum_height=620,
    )
    assert size == QSize(1232, 672)


def test_long_translated_buttons_stack_when_they_do_not_fit() -> None:
    assert button_row_fits([220, 410], 700)
    assert not button_row_fits([420, 700], 704)
