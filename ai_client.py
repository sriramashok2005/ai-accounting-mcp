import asyncio
import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_DIR = Path(__file__).resolve().parent
MODEL_NAME = "llama3.2"
OLLAMA_URL = "http://localhost:11434/api/chat"



def read_user_message():
    """
    Read a single-line question or a multi-line transaction request.

    For a transaction, start with a complete action such as
    'Record a transaction:' and press Enter on a blank line
    after entering all fields.
    """

    first_line = input("\nYou: ").strip()

    if first_line.lower() in {"exit", "quit"}:
        return first_line

    if not first_line:
        return ""

    is_transaction_request = re.search(
        r"\b(record|add|create|enter|book|post|save)\b"
        r".*\b(transaction|journal entry|sale|purchase|"
        r"expense|payment|income)\b",
        first_line,
        re.IGNORECASE,
    )

    if not is_transaction_request:
        return first_line

    lines = [first_line]

    print("Enter the remaining details.")
    print("Press Enter on an empty line when finished.")

    while True:
        line = input("... ")

        if not line.strip():
            break

        lines.append(line.strip())

    return "\n".join(lines).strip()



def ask_ollama(messages, tools):
    """Send the conversation and available tools to Ollama."""

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "tools": tools,
        "stream": False,
    }

    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=180) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        return result["message"]

    except HTTPError as error:
        details = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Ollama API error ({error.code}): {details}"
        ) from error

    except URLError as error:
        raise RuntimeError(
            "Cannot connect to Ollama. "
            "Check that Ollama is running."
        ) from error




def get_tool_text(result):
    """Convert an MCP response into text for the AI model."""

    structured = getattr(
        result,
        "structuredContent",
        None,
    )

    if structured is not None:
        return json.dumps(
            structured,
            ensure_ascii=False,
        )

    parts = []

    for item in getattr(result, "content", []):
        item_text = getattr(item, "text", None)

        if item_text is not None:
            parts.append(item_text)

    output = "\n".join(parts)

    if getattr(result, "isError", False):
        return f"TOOL ERROR: {output}"

    return output or "The tool returned no text."


def convert_mcp_tools(mcp_tools):
    """Convert MCP tool definitions into Ollama tool definitions."""

    converted_tools = []

    for tool in mcp_tools:
        converted_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }
        )

    return converted_tools




def get_field(question, field_pattern):
    """
    Read one explicitly labelled field from the original request.

    Examples:
        description: Office rent
        debit account: Rent Expense
        credit account: Cash
        amount: 100 rupees
        date: 2026-10-20
    """

    pattern = (
        r"^\s*(?:"
        + field_pattern
        + r")\s*[:=]\s*(.*?)\s*$"
    )

    match = re.search(
        pattern,
        question,
        re.IGNORECASE | re.MULTILINE,
    )

    if not match:
        return None

    value = match.group(1).strip()

    return value if value else None


def parse_money(value):
    """Parse an explicitly provided amount without guessing."""

    if value is None:
        raise ValueError("Amount is missing.")

    cleaned = str(value).strip()
    cleaned = cleaned.replace(",", "")

    cleaned = re.sub(
        r"^(?:₹|INR|Rs\.?)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*(?:rupees?|INR|Rs\.?)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    try:
        amount = Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError("Amount must be numeric.") from error

    if not amount.is_finite() or amount <= 0:
        raise ValueError("Amount must be greater than zero.")

    return amount


def validate_transaction_arguments(arguments, question):
    """
    Compare the proposed tool arguments with the user's original
    request. Do not let the model invent missing transaction details.

    Returns:
        (validated_arguments, None) on success
        (None, error_message) on failure
    """

    action_is_explicit = re.search(
        r"\b(record|add|create|enter|book|post|save)\b"
        r".*\b(transaction|journal entry|sale|purchase|"
        r"expense|payment|income)\b",
        question,
        re.IGNORECASE,
    )

    if not action_is_explicit:
        return None, (
            "Transaction blocked. Start with 'Record a transaction:' "
            "and provide all required details in one request."
        )

    if not isinstance(arguments, dict):
        return None, "Transaction blocked: invalid tool arguments."

    # Read required fields from the original user message.
    requested_description = get_field(
        question,
        r"description",
    )

    requested_debit = get_field(
        question,
        r"debit(?:\s+account|_account)",
    )

    requested_credit = get_field(
        question,
        r"credit(?:\s+account|_account)",
    )

    requested_amount_text = get_field(
        question,
        r"amount",
    )

    requested_date = get_field(
        question,
        r"date|entry_date",
    )

    missing_fields = []

    if not requested_description:
        missing_fields.append("description")

    if not requested_debit:
        missing_fields.append("debit account")

    if not requested_credit:
        missing_fields.append("credit account")

    if not requested_amount_text:
        missing_fields.append("amount")

    if not requested_date:
        missing_fields.append("date")

    if missing_fields:
        return None, (
            "Transaction blocked. Missing required details: "
            + ", ".join(missing_fields)
            + ". No transaction was saved."
        )

    
    try:
        requested_amount = parse_money(
            requested_amount_text
        )
    except ValueError as error:
        return None, f"Transaction blocked: {error}"

    # Validate the original date.
    try:
        date.fromisoformat(requested_date)
    except ValueError:
        return None, (
            "Transaction blocked. Date must use YYYY-MM-DD format."
        )

    # The accounts must be different.
    if (
        requested_debit.casefold()
        == requested_credit.casefold()
    ):
        return None, (
            "Transaction blocked. Debit and credit accounts "
            "must be different."
        )

    # Compare model-proposed values against the user's values.
    proposed_description = arguments.get("description")
    proposed_debit = arguments.get("debit_account")
    proposed_credit = arguments.get("credit_account")

    if not isinstance(proposed_description, str):
        return None, (
            "Transaction blocked: the proposed description is invalid."
        )

    if not isinstance(proposed_debit, str):
        return None, (
            "Transaction blocked: the proposed debit account is invalid."
        )

    if not isinstance(proposed_credit, str):
        return None, (
            "Transaction blocked: the proposed credit account is invalid."
        )

    if proposed_description.strip() != requested_description:
        return None, (
            "Transaction blocked. The proposed description does not "
            "match the description you supplied."
        )

    if proposed_debit.strip().casefold() != requested_debit.casefold():
        return None, (
            "Transaction blocked. The proposed debit account does not "
            "match your request."
        )

    if proposed_credit.strip().casefold() != requested_credit.casefold():
        return None, (
            "Transaction blocked. The proposed credit account does not "
            "match your request."
        )

    try:
        proposed_amount = parse_money(
            arguments.get("amount")
        )
    except ValueError as error:
        return None, (
            f"Transaction blocked: invalid proposed amount. {error}"
        )

    if proposed_amount != requested_amount:
        return None, (
            f"Transaction blocked. You requested "
            f"₹{requested_amount:.2f}, but the AI proposed "
            f"₹{proposed_amount:.2f}."
        )

    proposed_date = arguments.get(
        "entry_date",
        arguments.get("date"),
    )

    if proposed_date != requested_date:
        return None, (
            f"Transaction blocked. You requested the date "
            f"{requested_date}, but the AI proposed {proposed_date}."
        )

    
    validated_arguments = {
        "description": requested_description,
        "debit_account": requested_debit,
        "credit_account": requested_credit,
        "amount": float(requested_amount),
        "entry_date": requested_date,
    }

    return validated_arguments, None


def confirm_transaction(arguments):
    """Show the exact transaction and require explicit confirmation."""

    print("\nTRANSACTION REVIEW")
    print("=" * 42)
    print(f"Description:    {arguments['description']}")
    print(f"Debit account:  {arguments['debit_account']}")
    print(f"Credit account: {arguments['credit_account']}")
    print(f"Amount:         ₹{arguments['amount']:.2f}")
    print(f"Date:           {arguments['entry_date']}")
    print("=" * 42)

    print("Verify every field before confirming.")

    answer = input(
        "Type CONFIRM to save, or anything else to cancel: "
    ).strip()

    return answer == "CONFIRM"



async def run_assistant():
    """Connect the Ollama model to the Accounting MCP server."""

    server_parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(PROJECT_DIR / "main.py")],
    )

    async with stdio_client(server_parameters) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            tools_result = await session.list_tools()

            ollama_tools = convert_mcp_tools(
                tools_result.tools
            )

            available_tools = {
                tool.name: tool
                for tool in tools_result.tools
            }

            print("\nAccounting AI Assistant")
            print("=" * 40)
            print(f"Model: {MODEL_NAME}")
            print("MCP tools connected:")

            for tool in tools_result.tools:
                print(f"- {tool.name}")

            print("\nAsk an accounting question.")
            print("For a transaction, enter all fields together.")
            print("Type 'exit' to stop.")

            while True:
                try:
                    question = read_user_message()

                except (EOFError, KeyboardInterrupt):
                    print("\nAssistant stopped.")
                    break

                if question.lower() in {"exit", "quit"}:
                    print("Assistant stopped.")
                    break

                if not question:
                    continue

                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an accounting assistant for an "
                            "Indian business. All monetary amounts are "
                            "in Indian Rupees (INR). Always use ₹, not $. "
                            "Use MCP tools when current financial data "
                            "is needed. Base financial answers on actual "
                            "tool results and never invent values. "
                            "For transaction requests, use only the "
                            "description, accounts, amount and date "
                            "explicitly supplied in the current user "
                            "message. Never guess or change these values. "
                            "If details are missing, ask the user for "
                            "them. Never claim a transaction was saved "
                            "unless the transaction tool actually ran "
                            "and returned a successful result."
                        ),
                    },
                    {
                        "role": "user",
                        "content": question,
                    },
                ]

                try:
                    # Limit each user question to five model/tool rounds.
                    for _ in range(5):
                        assistant_message = ask_ollama(
                            messages,
                            ollama_tools,
                        )

                        messages.append(assistant_message)

                        tool_calls = assistant_message.get(
                            "tool_calls",
                            [],
                        )

                        if not tool_calls:
                            answer = assistant_message.get(
                                "content",
                                "",
                            )

                            print(f"\nAssistant: {answer}\n")
                            break

                        stop_current_turn = False

                        for tool_call in tool_calls:
                            function = tool_call["function"]
                            tool_name = function["name"]

                            arguments = function.get(
                                "arguments",
                                {},
                            )

                            if isinstance(arguments, str):
                                try:
                                    arguments = json.loads(arguments)
                                except json.JSONDecodeError:
                                    arguments = None

                            if tool_name not in available_tools:
                                tool_output = (
                                    f"Unknown MCP tool: {tool_name}"
                                )

                            elif tool_name == "add_transaction":
                                validated, error = (
                                    validate_transaction_arguments(
                                        arguments,
                                        question,
                                    )
                                )

                                if error:
                                    print(f"\n{error}")
                                    print(
                                        "No transaction was saved.\n"
                                    )

                                    # Stop the current model/tool round
                                    # so the AI cannot silently retry
                                    # the write operation with new values.
                                    stop_current_turn = True
                                    break

                                if not confirm_transaction(validated):
                                    print(
                                        "\nTransaction cancelled. "
                                        "Nothing was saved.\n"
                                    )

                                    stop_current_turn = True
                                    break

                                print(
                                    "\n[Calling MCP tool: "
                                    "add_transaction]"
                                )

                                try:
                                    result = await session.call_tool(
                                        "add_transaction",
                                        arguments=validated,
                                    )

                                    tool_output = get_tool_text(result)

                                    print("Transaction tool result:")
                                    print(tool_output)

                                except Exception as error:
                                    tool_output = (
                                        "Transaction execution failed: "
                                        f"{error}"
                                    )

                                    print(tool_output)

                            else:
                                # Read-only tools do not need write
                                # confirmation.
                                print(
                                    f"\n[Calling MCP tool: {tool_name}]"
                                )

                                try:
                                    result = await session.call_tool(
                                        tool_name,
                                        arguments=arguments,
                                    )

                                    tool_output = get_tool_text(result)

                                except Exception as error:
                                    tool_output = (
                                        f"Tool execution failed: {error}"
                                    )

                            messages.append(
                                {
                                    "role": "tool",
                                    "name": tool_name,
                                    "content": tool_output,
                                }
                            )

                        if stop_current_turn:
                            break

                    else:
                        print(
                            "\nAssistant: Tool-call limit reached. "
                            "Please make your request more specific.\n"
                        )

                except (
                    RuntimeError,
                    KeyError,
                    ValueError,
                    TypeError,
                ) as error:
                    print(f"\nError: {error}\n")


if __name__ == "__main__":
    asyncio.run(run_assistant())