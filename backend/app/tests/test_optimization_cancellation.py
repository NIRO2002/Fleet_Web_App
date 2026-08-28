from types import SimpleNamespace

import pytest

from app.optimization.assignment_problem import OptimizationCancelled, _CancelCallback


def _algorithm_at(n_gen):
    return SimpleNamespace(n_gen=n_gen)


def test_cancel_callback_noop_when_no_cancel_check():
    callback = _CancelCallback(cancel_check=None)
    for n_gen in (1, 5, 10):
        callback.notify(_algorithm_at(n_gen))  # must not raise


def test_cancel_callback_noop_while_not_cancelled():
    callback = _CancelCallback(cancel_check=lambda: False, check_every=5)
    for n_gen in (5, 10, 15):
        callback.notify(_algorithm_at(n_gen))  # must not raise


def test_cancel_callback_raises_on_a_check_generation():
    callback = _CancelCallback(cancel_check=lambda: True, check_every=5)
    callback.notify(_algorithm_at(3))  # not a multiple of check_every yet
    with pytest.raises(OptimizationCancelled):
        callback.notify(_algorithm_at(5))


def test_cancel_callback_skips_between_check_generations():
    calls = []
    def cancel_check():
        calls.append(True)
        return True
    callback = _CancelCallback(cancel_check=cancel_check, check_every=5)
    callback.notify(_algorithm_at(1))
    callback.notify(_algorithm_at(2))
    assert calls == []  # never polled off the check_every cadence
    with pytest.raises(OptimizationCancelled):
        callback.notify(_algorithm_at(10))
    assert calls == [True]
