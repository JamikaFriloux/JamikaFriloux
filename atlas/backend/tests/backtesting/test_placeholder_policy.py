"""Backtesting is Phase 4. This guards the documented engine decision until then."""

from pathlib import Path


def test_backtesting_adr_exists():
    adr = Path(__file__).resolve().parents[3] / "docs" / "adr" / "0003-backtesting-engine.md"
    assert adr.exists()
