import sqlite3
from contextlib import contextmanager
from pathlib import Path



BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "accounting.db"



@contextmanager
def get_connection():
    """
    Open a database connection.

    Commit changes when successful.
    Roll back changes if an error occurs.
    Always close the connection.
    """

    connection = sqlite3.connect(
        DB_PATH,
        timeout=10,
    )

    connection.row_factory = sqlite3.Row

    
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def initialize_database():
    """
    Create the accounting tables and default accounts
    if they do not already exist.
    """

    with get_connection() as connection:

        
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                account_code TEXT UNIQUE NOT NULL,

                account_name TEXT UNIQUE NOT NULL,

                account_type TEXT NOT NULL CHECK (
                    account_type IN (
                        'Asset',
                        'Liability',
                        'Equity',
                        'Income',
                        'Expense'
                    )
                ),

                normal_balance TEXT NOT NULL CHECK (
                    normal_balance IN (
                        'Debit',
                        'Credit'
                    )
                )
            )
            """
        )

        # Journal entries table
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                entry_date TEXT NOT NULL,

                description TEXT NOT NULL,

                debit_account_id INTEGER NOT NULL,

                credit_account_id INTEGER NOT NULL,

                amount REAL NOT NULL CHECK (
                    amount > 0
                ),

                FOREIGN KEY (debit_account_id)
                    REFERENCES accounts(id),

                FOREIGN KEY (credit_account_id)
                    REFERENCES accounts(id),

                CHECK (
                    debit_account_id != credit_account_id
                )
            )
            """
        )

        # Default chart of accounts
        default_accounts = [
            ("1000", "Cash", "Asset", "Debit"),
            ("1010", "Bank", "Asset", "Debit"),

            (
                "2000",
                "Accounts Payable",
                "Liability",
                "Credit",
            ),

            (
                "3000",
                "Owner's Capital",
                "Equity",
                "Credit",
            ),

            (
                "4000",
                "Sales Revenue",
                "Income",
                "Credit",
            ),

            (
                "5000",
                "Rent Expense",
                "Expense",
                "Debit",
            ),

            (
                "5010",
                "Salary Expense",
                "Expense",
                "Debit",
            ),

            (
                "5020",
                "Utilities Expense",
                "Expense",
                "Debit",
            ),
        ]

        connection.executemany(
            """
            INSERT OR IGNORE INTO accounts (
                account_code,
                account_name,
                account_type,
                normal_balance
            )
            VALUES (?, ?, ?, ?)
            """,
            default_accounts,
        )

        # Indexes improve common account and date lookups.
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_journal_debit_account
            ON journal_entries(debit_account_id)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_journal_credit_account
            ON journal_entries(credit_account_id)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_journal_entry_date
            ON journal_entries(entry_date)
            """
        )




def get_accounts():
    """
    Return all accounts ordered by account code.
    """

    initialize_database()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                account_code,
                account_name,
                account_type,
                normal_balance
            FROM accounts
            ORDER BY account_code
            """
        ).fetchall()

    return [dict(row) for row in rows]



def get_account_by_name(account_name: str):
    """
    Find an account using its name.
    The search is case-insensitive.
    """

    if not account_name or not account_name.strip():
        raise ValueError("Account name cannot be empty.")

    initialize_database()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                account_code,
                account_name,
                account_type,
                normal_balance
            FROM accounts
            WHERE LOWER(account_name) = LOWER(?)
            """,
            (account_name.strip(),),
        ).fetchone()

    if row is None:
        return None

    return dict(row)




if __name__ == "__main__":

    initialize_database()

    print("Accounting database initialized successfully.")
    print(f"Database location: {DB_PATH}")

    accounts = get_accounts()

    print(f"\nTotal accounts: {len(accounts)}")
    print("-" * 75)

    for account in accounts:
        print(
            f'{account["account_code"]} | '
            f'{account["account_name"]} | '
            f'{account["account_type"]} | '
            f'{account["normal_balance"]}'
        )

    print("-" * 75)