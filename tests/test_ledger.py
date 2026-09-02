import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

# pyrefly: ignore [missing-import]
import pytest

from ledger import CreditLedger, InvalidCreditError


def test_applies_credit_once(ledger):
    result = ledger.apply_credit("evt-1", "acc-1", 1000)

    assert result.applied is True
    assert result.balance_cents == 1000
    assert ledger.balance("acc-1") == 1000


def test_different_events_accumulate(ledger):
    ledger.apply_credit("evt-1", "acc-1", 1000)
    ledger.apply_credit("evt-2", "acc-1", 250)

    assert ledger.balance("acc-1") == 1250


def test_accounts_are_independent(ledger):
    ledger.apply_credit("evt-1", "acc-1", 1000)
    ledger.apply_credit("evt-2", "acc-2", 700)

    assert ledger.balance("acc-1") == 1000
    assert ledger.balance("acc-2") == 700


def test_duplicate_event_is_applied_only_once(ledger):
    ledger.apply_credit("evt-1", "acc-1", 1000)
    result = ledger.apply_credit("evt-1", "acc-1", 1000)

    assert result.applied is False
    assert ledger.balance("acc-1") == 1000


def test_duplicate_event_is_ignored_after_restart(database_path):
    CreditLedger(database_path).apply_credit("evt-1", "acc-1", 1000)

    restarted = CreditLedger(database_path)
    result = restarted.apply_credit("evt-1", "acc-1", 1000)

    assert result.applied is False
    assert restarted.balance("acc-1") == 1000


def test_unknown_account_has_zero_balance(ledger):
    assert ledger.balance("acc-inexistente") == 0


def test_concurrent_duplicate_event_is_applied_only_once(ledger):
    workers = 4
    barrier = Barrier(workers)

    def apply_credit():
        barrier.wait()
        return ledger.apply_credit("evt-concurrent", "acc-1", 1000)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda _: apply_credit(), range(workers)))

    assert sum(result.applied for result in results) == 1
    assert sum(not result.applied for result in results) == workers - 1
    assert ledger.balance("acc-1") == 1000


def test_concurrent_duplicate_event_across_instances_is_applied_once(database_path):
    ledgers = [CreditLedger(database_path), CreditLedger(database_path)]
    barrier = Barrier(len(ledgers))

    def apply_credit(ledger):
        barrier.wait()
        return ledger.apply_credit("evt-shared", "acc-1", 750)

    with ThreadPoolExecutor(max_workers=len(ledgers)) as executor:
        results = list(executor.map(apply_credit, ledgers))

    assert sum(result.applied for result in results) == 1
    assert sum(not result.applied for result in results) == 1
    assert ledgers[0].balance("acc-1") == 750


@pytest.mark.parametrize(
    ("event_id", "account_id", "amount_cents"),
    [
        ("", "acc-1", 100),
        ("evt-1", "", 100),
        ("evt-1", "acc-1", 0),
        ("evt-1", "acc-1", -1),
    ],
)
def test_invalid_credit_has_no_effect(
    database_path,
    ledger,
    event_id,
    account_id,
    amount_cents,
):
    with pytest.raises(InvalidCreditError):
        ledger.apply_credit(event_id, account_id, amount_cents)

    assert ledger.balance(account_id) == 0

    with sqlite3.connect(database_path) as conn:
        event_count = conn.execute(
            "SELECT COUNT(*) FROM applied_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()[0]

    assert event_count == 0


def test_event_id_can_be_reused_after_invalid_credit(ledger):
    with pytest.raises(InvalidCreditError):
        ledger.apply_credit("evt-retry", "acc-1", 0)

    result = ledger.apply_credit("evt-retry", "acc-1", 500)

    assert result.applied is True
    assert result.balance_cents == 500
    assert ledger.balance("acc-1") == 500


def test_different_events_accumulate_when_applied_concurrently(ledger):
    credits = [
        ("evt-a", "acc-1", 100),
        ("evt-b", "acc-1", 250),
    ]
    barrier = Barrier(len(credits))

    def apply_credit(credit):
        barrier.wait()
        return ledger.apply_credit(*credit)

    with ThreadPoolExecutor(max_workers=len(credits)) as executor:
        results = list(executor.map(apply_credit, credits))

    assert all(result.applied for result in results)
    assert ledger.balance("acc-1") == 350
