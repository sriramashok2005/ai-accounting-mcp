import pytest

from src import database
from src.accounting import (
    record_transaction,
    get_trial_balance,
    get_profit_loss,
)


@pytest.fixture(autouse=True)
def setup_test_database(tmp_path, monkeypatch):
    """Use a separate temporary database for every test."""

    test_db_path = tmp_path / "test_accounting.db"

    monkeypatch.setattr(
        database,
        "DB_PATH",
        test_db_path,
    )

    database.initialize_database()


def test_record_transaction_and_trial_balance():
    result = record_transaction(
        description="Test sale",
        debit_account="Cash",
        credit_account="Sales Revenue",
        amount=1000,
        entry_date="2026-10-20",
    )

    assert result["message"] == "Transaction recorded successfully."
    assert result["amount"] == 1000

    balance = get_trial_balance()

    assert balance["total_debit"] == 1000
    assert balance["total_credit"] == 1000
    assert balance["is_balanced"] is True


def test_zero_amount_is_rejected():
    with pytest.raises(ValueError, match="Amount must be greater than zero"):
        record_transaction(
            description="Invalid transaction",
            debit_account="Cash",
            credit_account="Sales Revenue",
            amount=0,
        )


def test_unknown_account_is_rejected():
    with pytest.raises(ValueError, match="Debit account not found"):
        record_transaction(
            description="Invalid account test",
            debit_account="Unknown Account",
            credit_account="Sales Revenue",
            amount=500,
        )


def test_invalid_date_is_rejected():
    with pytest.raises(ValueError, match="Date must use YYYY-MM-DD"):
        record_transaction(
            description="Invalid date test",
            debit_account="Cash",
            credit_account="Sales Revenue",
            amount=500,
            entry_date="20-10-2026",
        )


def test_profit_loss_calculation():
    record_transaction(
        description="Cash sale",
        debit_account="Cash",
        credit_account="Sales Revenue",
        amount=2500,
        entry_date="2026-10-20",
    )

    record_transaction(
        description="Rent payment",
        debit_account="Rent Expense",
        credit_account="Cash",
        amount=500,
        entry_date="2026-10-20",
    )

    report = get_profit_loss()

    assert report["total_income"] == 2500
    assert report["total_expenses"] == 500
    assert report["net_profit"] == 2000
    assert report["result"] == "Profit"