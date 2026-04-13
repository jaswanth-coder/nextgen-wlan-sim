"""Unit tests for Block Acknowledgement scoreboard."""

import pytest
from nxwlansim.mac.ampdu import BlockAckSession


def make_session():
    return BlockAckSession(peer_mac="aa:bb:cc:dd:ee:ff", tid=0, link_id="6g")


def test_mark_and_check_received():
    s = make_session()
    s.mark_received(0)
    assert s.is_received(0)
    assert not s.is_received(1)


def test_window_advance():
    s = make_session()
    s.mark_received(0)
    s.mark_received(1)
    s.mark_received(2)
    s.advance_window()
    assert s.win_start == 3


def test_window_no_advance_with_gap():
    s = make_session()
    s.mark_received(0)
    s.mark_received(2)   # gap at seq 1
    s.advance_window()
    assert s.win_start == 1   # stops at the gap


def test_missing_seqs():
    s = make_session()
    s.mark_received(0)
    s.mark_received(2)
    missing = s.missing_seqs()
    assert 1 in missing


def test_seq_wrap():
    """Sequence numbers wrap at 4096."""
    s = BlockAckSession(peer_mac="aa:bb:cc:dd:ee:ff", tid=0, link_id="6g", win_start=4094)
    s.mark_received(4094)
    s.mark_received(4095)
    s.mark_received(0)    # wrapped
    assert s.is_received(4094)
    assert s.is_received(0)
