"""Unit tests for NAV controller."""

from nxwlansim.mac.nav import NAVController


def test_nav_not_busy_initially():
    nav = NAVController()
    assert not nav.is_busy(0)


def test_nav_busy_after_set():
    nav = NAVController()
    nav.set(duration_ns=10_000, now_ns=0)
    assert nav.is_busy(5_000)
    assert not nav.is_busy(10_001)


def test_nav_extends_on_longer_duration():
    nav = NAVController()
    nav.set(10_000, 0)
    nav.set(20_000, 0)
    assert nav.is_busy(15_000)


def test_nav_does_not_shorten():
    nav = NAVController()
    nav.set(20_000, 0)
    nav.set(5_000, 0)   # shorter — should not change
    assert nav.is_busy(15_000)


def test_nav_reset():
    nav = NAVController()
    nav.set(10_000, 0)
    nav.reset()
    assert not nav.is_busy(5_000)
