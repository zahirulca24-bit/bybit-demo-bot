
import threading
import time

_lock = threading.Lock()
_cached = None
_error = None
_expires = 0.0


def get_account_snapshot():
    global _cached, _error, _expires

    with _lock:
        now = time.monotonic()

        if now < _expires:
            return _cached, _error

        try:
            from dashboard.live import live_account
            _cached = live_account()
            _error = None
            _expires = time.monotonic() + 15
        except Exception:
            _cached = None
            _error = "Bybit account data unavailable"
            _expires = time.monotonic() + 5

        return _cached, _error
