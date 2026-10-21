# AI-Powered Accounting & Financial Intelligence Assistant

An accounting assistant built with Python, SQLite, the Model Context
Protocol (MCP), and Ollama's Llama 3.2 model.

The application records double-entry accounting transactions,
calculates the Trial Balance and Profit & Loss report, and allows an
AI model to use accounting tools through MCP.

## Features

- Record accounting transactions using debit and credit accounts.
- Generate a Trial Balance and check whether it balances.
- Generate a Profit & Loss report.
- Expose accounting operations as MCP tools.
- Provide a Chart of Accounts through an MCP resource.
- Provide reusable financial analysis instructions through an MCP prompt.
- Use Llama 3.2 with Ollama to select MCP tools for user questions.
- Validate transaction details and request confirmation before saving.
- Run automated accounting tests with pytest.

## Technology Stack

- Python 3.11
- SQLite
- Model Context Protocol (MCP)
- Ollama
- Llama 3.2
- pytest

## Project Structure

ACCOUNTING MCP/
├── main.py
├── ai_client.py
├── accounting.db
├── README.md
├── src/
│   ├── database.py
│   └── accounting.py
└── tests/
    └── test_accounting.py