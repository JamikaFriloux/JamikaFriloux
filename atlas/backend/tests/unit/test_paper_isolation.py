"""Static guarantees that live trading is technically inaccessible in this deployment."""

import ast
import re
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[2]
PROJECT = BACKEND.parent
SRC = BACKEND / "atlas"


def _py_files():
    return [p for p in SRC.rglob("*.py")]


def test_no_live_client_construction():
    for path in _py_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "paper":
                assert isinstance(node.value, ast.Constant) and node.value.value is True, (
                    f"{path}: TradingClient must be constructed with paper=True literal"
                )
            if isinstance(node, ast.keyword) and node.arg == "url_override":
                raise AssertionError(f"{path}: url_override is forbidden")


def test_live_endpoint_only_appears_in_deny_list():
    pattern = re.compile(r"https://api\.alpaca\.markets")
    for path in _py_files():
        if pattern.search(path.read_text()):
            raise AssertionError(f"{path} references the live trading endpoint")


def test_broker_settings_only_loaded_by_executor_and_scripts():
    allowed = {"executor", "scripts", "configuration", "alpaca"}
    for path in _py_files():
        text = path.read_text()
        if re.search(r"BrokerSettings\(", text):
            rel = path.relative_to(SRC).parts
            assert set(rel) & allowed, f"{path} constructs BrokerSettings"


def test_api_and_agents_do_not_import_alpaca_sdk():
    for sub in ("apps/api", "apps/worker", "agents", "core"):
        for path in (SRC / sub).rglob("*.py"):
            text = path.read_text()
            assert "from alpaca" not in text and "import alpaca" not in text, path


def test_only_executor_container_gets_broker_credentials():
    compose = yaml.safe_load((PROJECT / "docker-compose.yml").read_text())
    for name, svc in compose["services"].items():
        env_files = svc.get("env_file", [])
        env_files = [env_files] if isinstance(env_files, str) else env_files
        env_files = [e if isinstance(e, str) else e.get("path", "") for e in env_files]
        env = svc.get("environment", {}) or {}
        keys = env if isinstance(env, list) else list(env)
        has_broker = any("ALPACA" in str(k) for k in keys) or any("broker" in e for e in env_files)
        if name == "executor":
            assert has_broker, "executor must receive broker credentials"
        else:
            assert not has_broker, f"service {name} must not receive broker credentials"


def test_env_example_has_no_real_secrets():
    text = (PROJECT / ".env.example").read_text() + (PROJECT / "broker.env.example").read_text()
    assert not re.search(r"(PK|AK)[A-Z0-9]{16,}", text)
    assert "paper-api.alpaca.markets" in text


def test_agents_cannot_reach_execution_or_change_config():
    """Agents are advisory: no execution, broker, order or policy-writing code paths."""
    banned = (
        "atlas.core.execution",
        "atlas.apps.executor",
        "atlas.integrations.alpaca",
        "kill_switch.engage",
        "kill_switch.resume",
        "set_status",
        "submit_",
        "write_text",
    )
    for path in (SRC / "agents").rglob("*.py"):
        text = path.read_text()
        for word in banned:
            assert word not in text, f"{path} contains {word!r}"
