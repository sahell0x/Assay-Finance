"""Shared fixtures.

The yfinance fixtures under ``fixtures/`` are real captured statement frames for five
tickers chosen because their row labels differ: a hardware manufacturer (AAPL), a bank
(JPM, no cost of revenue and no current-asset split), a REIT (O), and two more software
names. Tests never touch the network.
"""

from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _to_frame(payload: dict | None) -> pd.DataFrame | None:
    if not payload:
        return None
    return pd.DataFrame(
        payload["data"],
        index=payload["index"],
        columns=[pd.Timestamp(c) for c in payload["columns"]],
    )


def load_statements(ticker: str):
    from src.data.fundamentals import Statements

    raw = json.loads((FIXTURES / f"{ticker}.json").read_text())
    return (
        Statements(
            income=_to_frame(raw.get("income_stmt")),
            balance=_to_frame(raw.get("balance_sheet")),
            cashflow=_to_frame(raw.get("cashflow")),
            q_income=_to_frame(raw.get("quarterly_income_stmt")),
            q_balance=_to_frame(raw.get("quarterly_balance_sheet")),
            q_cashflow=_to_frame(raw.get("quarterly_cashflow")),
        ),
        raw.get("market", {}),
    )


@pytest.fixture
def statements():
    return load_statements


@pytest.fixture
def aapl_fixture():
    return load_statements("AAPL")


@pytest.fixture
def jpm_fixture():
    return load_statements("JPM")


@pytest.fixture
def reit_fixture():
    return load_statements("O")


# API fixtures live in their own module so the analytics suite never imports the
# database machinery.
from conftest_api import *  # noqa: E402,F401,F403
