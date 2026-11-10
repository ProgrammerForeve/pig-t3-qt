"""D3: setup_logging / get_logger."""

import logging

from PIG_T3.logging_config import get_logger, setup_logging


def test_setup_returns_logger():
    lg = setup_logging(verbose=False)
    assert isinstance(lg, logging.Logger)
    assert lg.name == "pig_t3"


def test_setup_verbose_sets_debug_level():
    lg = setup_logging(verbose=True)
    assert lg.level == logging.DEBUG


def test_setup_non_verbose_sets_info_level():
    lg = setup_logging(verbose=False)
    assert lg.level == logging.INFO


def test_setup_idempotent_handlers():
    setup_logging(verbose=False)
    first = len(logging.getLogger("pig_t3").handlers)
    setup_logging(verbose=True)
    second = len(logging.getLogger("pig_t3").handlers)
    assert first == second


def test_get_logger_has_prefix():
    lg = get_logger("mymod")
    assert lg.name == "pig_t3.mymod"


def test_verbose_switch_changes_level():
    setup_logging(verbose=False)
    assert logging.getLogger("pig_t3").level == logging.INFO
    setup_logging(verbose=True)
    assert logging.getLogger("pig_t3").level == logging.DEBUG


def test_third_party_suppressed():
    setup_logging(verbose=True)
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("watchdog").level == logging.WARNING
