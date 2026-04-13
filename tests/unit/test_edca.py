"""Unit tests for EDCA backoff, CW, and queue logic."""

import pytest
from nxwlansim.mac.edca import ACQueue, EDCA_PARAMS
from nxwlansim.mac.frame import MPDUFrame


def _frame(ac="BE"):
    return MPDUFrame(frame_id=1, src="sta0", dst="ap0", ac=ac)


def test_initial_backoff_set_on_enqueue():
    q = ACQueue("BE", seed=0)
    assert q.empty
    q.enqueue(_frame("BE"))
    assert q.backoff >= 0
    assert q.backoff <= EDCA_PARAMS["BE"][0]   # <= CWmin


def test_backoff_decrements():
    q = ACQueue("BE", seed=1)
    q.enqueue(_frame())
    initial = q.backoff
    if initial > 0:
        q.decrement_backoff()
        assert q.backoff == initial - 1


def test_backoff_does_not_go_negative():
    q = ACQueue("BE", seed=0)
    q.enqueue(_frame())
    for _ in range(100):
        q.decrement_backoff()
    assert q.backoff >= 0


def test_collision_doubles_cw():
    q = ACQueue("BE", seed=2)
    q.enqueue(_frame())
    cw_before = q._cw
    q.collision()
    assert q._cw == min(cw_before * 2 + 1, EDCA_PARAMS["BE"][1])


def test_txop_success_resets_cw():
    q = ACQueue("BE", seed=3)
    q.enqueue(_frame())
    q.collision()   # inflate CW
    q.txop_success()
    assert q._cw == EDCA_PARAMS["BE"][0]   # back to CWmin


def test_freeze_stops_decrement():
    q = ACQueue("BE", seed=0)
    q.enqueue(_frame())
    initial = q.backoff
    q.frozen = True
    q.decrement_backoff()
    assert q.backoff == initial   # no change


def test_priority_ordering():
    """VO queue should have smaller CWmin than BE."""
    cw_vo = EDCA_PARAMS["VO"][0]
    cw_be = EDCA_PARAMS["BE"][0]
    assert cw_vo < cw_be
