import threading


class StopRequested(RuntimeError):
    pass


_STOP_EVENT = threading.Event()


def reset_stop():
    _STOP_EVENT.clear()


def request_stop():
    _STOP_EVENT.set()


def is_stop_requested():
    return _STOP_EVENT.is_set()


def ensure_running():
    if is_stop_requested():
        raise StopRequested("Остановлено пользователем")
