"""Kill switch, loss halt and the entry gate."""

import asyncio

import pytest

from mentionbot.safety import KillSwitch, LossGuard, evaluate_entry_gate

pytestmark = pytest.mark.asyncio


def gate(**overrides):
    base = dict(
        kill_engaged=False,
        loss_halted=False,
        jev_healthy=True,
        book_stale=False,
        transcript_stale=False,
        audio_connected=True,
        market_data_connected=True,
    )
    base.update(overrides)
    return evaluate_entry_gate(**base)


# -- entry gate ------------------------------------------------------------
async def test_all_clear_allows_entries():
    g = gate()
    assert g.allowed and g.summary == "OK"


@pytest.mark.parametrize(
    "override, fragment",
    [
        ({"kill_engaged": True}, "kill switch"),
        ({"loss_halted": True}, "loss limit"),
        ({"jev_healthy": False}, "Jev unavailable"),
        ({"book_stale": True}, "orderbook data stale"),
        ({"transcript_stale": True}, "transcript data stale"),
        ({"audio_connected": False}, "audio stream down"),
        ({"market_data_connected": False}, "Kalshi market data down"),
    ],
)
async def test_each_condition_blocks_entries(override, fragment):
    g = gate(**override)
    assert not g.allowed
    assert fragment in g.summary


async def test_multiple_reasons_are_all_reported():
    g = gate(kill_engaged=True, jev_healthy=False)
    assert len(g.reasons) == 2


# -- kill switch -----------------------------------------------------------
async def test_kill_switch_starts_disengaged(tmp_path):
    k = KillSwitch(tmp_path)
    assert k.level == 0 and not k.engaged and not k.flatten


async def test_level_one_stops_entries_without_flattening(tmp_path):
    k = KillSwitch(tmp_path)
    k.trigger(1, "test")
    assert k.engaged and not k.flatten


async def test_second_command_escalates_to_flatten(tmp_path):
    k = KillSwitch(tmp_path)
    k.escalate("first")
    k.escalate("second")
    assert k.level == 2 and k.flatten


async def test_level_never_goes_backwards(tmp_path):
    k = KillSwitch(tmp_path)
    k.trigger(2, "flatten")
    k.trigger(1, "stop")
    assert k.level == 2


async def test_level_is_capped_at_two(tmp_path):
    k = KillSwitch(tmp_path)
    for _ in range(5):
        k.escalate("again")
    assert k.level == 2


async def test_stop_file_engages_level_one(tmp_path):
    k = KillSwitch(tmp_path, poll_s=0.01)
    k.start(keyboard=False)
    try:
        (tmp_path / "STOP").write_text("")
        await asyncio.sleep(0.1)
        assert k.engaged and not k.flatten
        assert "STOP" in (k.reason or "")
    finally:
        await k.stop()


async def test_stop_file_with_flatten_escalates(tmp_path):
    k = KillSwitch(tmp_path, poll_s=0.01)
    k.start(keyboard=False)
    try:
        (tmp_path / "STOP").write_text("FLATTEN\n")
        await asyncio.sleep(0.1)
        assert k.flatten
    finally:
        await k.stop()


async def test_stop_file_escalation_after_creation(tmp_path):
    k = KillSwitch(tmp_path, poll_s=0.01)
    k.start(keyboard=False)
    try:
        stop = tmp_path / "STOP"
        stop.write_text("")
        await asyncio.sleep(0.05)
        assert k.level == 1
        stop.write_text("flatten please")
        await asyncio.sleep(0.05)
        assert k.level == 2
    finally:
        await k.stop()


async def test_no_stop_file_means_no_trigger(tmp_path):
    k = KillSwitch(tmp_path, poll_s=0.01)
    k.start(keyboard=False)
    try:
        await asyncio.sleep(0.05)
        assert k.level == 0
    finally:
        await k.stop()


# -- loss guard -------------------------------------------------------------
async def test_loss_guard_halts_at_the_limit():
    g = LossGuard(max_loss_cents=2500)
    assert not g.update(-2499)
    assert g.update(-2500)
    assert g.halted


async def test_loss_guard_stays_halted_after_recovery():
    """A breach is permanent for the event; it must not un-halt on a bounce."""
    g = LossGuard(max_loss_cents=100)
    g.update(-150)
    assert g.update(+500)
    assert g.halted


async def test_loss_guard_ignores_profit():
    g = LossGuard(max_loss_cents=100)
    assert not g.update(1000)


async def test_loss_guard_tracks_the_worst_point():
    g = LossGuard(max_loss_cents=10_000)
    for pnl in (50, -300, -120):
        g.update(pnl)
    assert g.worst_cents == -300
