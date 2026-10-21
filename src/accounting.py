from builtins import ValueError, float, print, round, str
from datetime import date

from src.database import get_connection, initialize_database


def record_transaction(
    description: str,
    debit_account: str,
    credit_account: str,
    amount: float,
    entry_date: str | None = None,
):
    initialize_database()

    description = description.strip()
    debit_account = debit_account.strip()
    credit_account = credit_account.strip()

    if not description:
        raise ValueError("Description cannot be empty.")

    if not debit_account or not credit_account:
        raise ValueError("Debit and credit accounts are required.")

    if debit_account.lower() == credit_account.lower():
        raise ValueError(
            "Debit and credit accounts must be different."
        )

    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    if entry_date is None:
        entry_date = date.today().isoformat()

    try:
        date.fromisoformat(entry_date)
    except ValueError:
        raise ValueError("Date must use YYYY-MM-DD format.")

    with get_connection() as connection:
        debit = connection.execute(
            """
            SELECT id, account_name
            FROM accounts
            WHERE LOWER(account_name) = LOWER(?)
            """,
            (debit_account,),
        ).fetchone()

        credit = connection.execute(
            """
            SELECT id, account_name
            FROM accounts
            WHERE LOWER(account_name) = LOWER(?)
            """,
            (credit_account,),
        ).fetchone()

        if debit is None:
            raise ValueError(
                f"Debit account not found: {debit_account}"
            )

        if credit is None:
            raise ValueError(
                f"Credit account not found: {credit_account}"
            )

        cursor = connection.execute(
            """
            INSERT INTO journal_entries (
                entry_date,
                description,
                debit_account_id,
                credit_account_id,
                amount
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry_date,
                description,
                debit["id"],
                credit["id"],
                amount,
            ),
        )

        entry_id = cursor.lastrowid

    return {
        "message": "Transaction recorded successfully.",
        "entry_id": entry_id,
        "date": entry_date,
        "description": description,
        "debit_account": debit["account_name"],
        "credit_account": credit["account_name"],
        "amount": amount,
    }


def get_trial_balance():
    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                a.account_code,
                a.account_name,
                a.account_type,
                COALESCE(
                    SUM(
                        CASE
                            WHEN j.debit_account_id = a.id
                            THEN j.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_debit,
                COALESCE(
                    SUM(
                        CASE
                            WHEN j.credit_account_id = a.id
                            THEN j.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_credit
            FROM accounts a
            LEFT JOIN journal_entries j
                ON j.debit_account_id = a.id
                OR j.credit_account_id = a.id
            GROUP BY
                a.id,
                a.account_code,
                a.account_name,
                a.account_type
            ORDER BY a.account_code
            """
        ).fetchall()

    trial_balance = []
    total_debit = 0
    total_credit = 0

    for row in rows:
        debit = round(row["total_debit"], 2)
        credit = round(row["total_credit"], 2)

        trial_balance.append(
            {
                "account_code": row["account_code"],
                "account_name": row["account_name"],
                "account_type": row["account_type"],
                "debit": debit,
                "credit": credit,
            }
        )

        total_debit += debit
        total_credit += credit

    total_debit = round(total_debit, 2)
    total_credit = round(total_credit, 2)

    return {
        "accounts": trial_balance,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "is_balanced": total_debit == total_credit,
    }


def get_profit_loss():
    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                a.account_name,
                a.account_type,
                COALESCE(
                    SUM(
                        CASE
                            WHEN j.debit_account_id = a.id
                            THEN j.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_debit,
                COALESCE(
                    SUM(
                        CASE
                            WHEN j.credit_account_id = a.id
                            THEN j.amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_credit
            FROM accounts a
            LEFT JOIN journal_entries j
                ON j.debit_account_id = a.id
                OR j.credit_account_id = a.id
            WHERE a.account_type IN ('Income', 'Expense')
            GROUP BY
                a.id,
                a.account_name,
                a.account_type
            ORDER BY a.account_type, a.account_name
            """
        ).fetchall()

    income_accounts = []
    expense_accounts = []
    total_income = 0
    total_expenses = 0

    for row in rows:
        debit = round(row["total_debit"], 2)
        credit = round(row["total_credit"], 2)

        if row["account_type"] == "Income":
            balance = round(credit - debit, 2)
            total_income += balance

            income_accounts.append(
                {
                    "account_name": row["account_name"],
                    "amount": balance,
                }
            )

        elif row["account_type"] == "Expense":
            balance = round(debit - credit, 2)
            total_expenses += balance

            expense_accounts.append(
                {
                    "account_name": row["account_name"],
                    "amount": balance,
                }
            )

    total_income = round(total_income, 2)
    total_expenses = round(total_expenses, 2)
    net_profit = round(total_income - total_expenses, 2)

    return {
        "income_accounts": income_accounts,
        "expense_accounts": expense_accounts,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "result": "Profit" if net_profit >= 0 else "Loss",
    }


if __name__ == "__main__":
    result = get_profit_loss()

    print("\nPROFIT & LOSS REPORT")
    print("=" * 45)

    print("\nINCOME")

    for account in result["income_accounts"]:
        print(
            f'{account["account_name"]:<25} '
            f'{account["amount"]:>10.2f}'
        )

    print(
        f'Total Income:              '
        f'{result["total_income"]:>10.2f}'
    )

    print("\nEXPENSES")

    for account in result["expense_accounts"]:
        print(
            f'{account["account_name"]:<25} '
            f'{account["amount"]:>10.2f}'
        )

    print(
        f'Total Expenses:            '
        f'{result["total_expenses"]:>10.2f}'
    )

    print("-" * 45)

    print(
        f'Net {result["result"]}:                '
        f'{result["net_profit"]:>10.2f}'
    )