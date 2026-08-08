import pytest

from app import control


def test_stop_request_is_visible_to_workers():
    control.reset_stop()
    assert control.is_stop_requested() is False

    control.request_stop()

    assert control.is_stop_requested() is True
    with pytest.raises(control.StopRequested):
        control.ensure_running()
    control.reset_stop()
