import json

from mcp.server.fastmcp import FastMCP

from src.accounting import (
    record_transaction,
    get_trial_balance,
    get_profit_loss,
)
from src.database import get_accounts


mcp = FastMCP("Accounting Intelligence Assistant")



@mcp.tool()
def add_transaction(
    description: str,
    debit_account: str,
    credit_account: str,
    amount: float,
    entry_date: str | None = None,
    confirmation: str = "",
) -> dict:
    """Record an accounting transaction after explicit confirmation."""

    if confirmation != "CONFIRM":
        raise ValueError(
            "Transaction not recorded. Explicit confirmation is required."
        )

    return record_transaction(
        description=description,
        debit_account=debit_account,
        credit_account=credit_account,
        amount=amount,
        entry_date=entry_date,
    )



@mcp.tool()
def trial_balance() -> dict:
    """Get account debit and credit totals and check whether they balance."""

    return get_trial_balance()



@mcp.tool()
def profit_loss() -> dict:
    """Get total income, expenses, and net profit or loss."""

    return get_profit_loss()



@mcp.resource("accounting://chart-of-accounts")
def chart_of_accounts() -> str:
    """Provide the available accounting accounts and their types."""

    accounts = get_accounts()

    return json.dumps(
        accounts,
        indent=2,
    )



@mcp.prompt(title="Financial Report Analysis")
def financial_report_analysis(question: str) -> str:
    """Create instructions for analyzing accounting reports."""

    question = question.strip()

    if not question:
        raise ValueError("Question cannot be empty.")

    return f"""
You are an accounting and financial analysis assistant.

Help the user understand their accounting records.

Instructions:
1. Use the available accounting tools when financial data is needed.
2. Use trial_balance to check whether total debits equal total credits.
3. Use profit_loss to analyze income, expenses, and net profit or loss.
4. Use the chart of accounts resource to understand account names and types.
5. Base your response on the actual tool results.
6. Do not invent transactions, financial values, or account balances.
7. Explain calculations in simple language.
8. Clearly mention when the available data is insufficient.
9. Treat this project as a prototype, not a replacement for
   professional accounting review.

User question:
{question}
"""


if __name__ == "__main__":
    mcp.run()