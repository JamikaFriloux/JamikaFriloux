"""Research-agent runner.

Every agent works the same way:
  1. compute **features** deterministically in code (indicators, counts, metrics). These are
     the source of truth and are stored whether or not an LLM is available;
  2. optionally ask the LLM for a **narrative** over those features, parsed into a Pydantic
     schema and checked again in code (``check``);
  3. persist one ``AgentReport``.

Agents are advisory. Nothing in the trading path (signals, risk engine, executor) reads agent
reports, and agents have no broker credentials, no order or configuration access. External
text (news) reaches the model only through ``wrap_untrusted``.

Cost controls: identical inputs (same features, extra text and prompt version) reuse the
previous report instead of calling the model again, and all agents share a daily call cap
(``ATLAS_LLM_MAX_CALLS_PER_DAY``).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atlas.core.data.calendar import NY
from atlas.core.models.db import AgentReport
from atlas.core.observability.logging import get_logger
from atlas.integrations.llm.base import (
    DisabledProvider,
    LLMError,
    LLMProvider,
    LLMRefusalError,
    LLMSchemaError,
)

log = get_logger(__name__)

# Statuses of a report. Only the first three mean a model call was made.
OK = "ok"
REFUSED = "refused"
LLM_ERROR = "llm_error"
NO_LLM = "no_llm"  # provider disabled: features only
BUDGET = "budget"  # daily cap reached: features only
NO_DATA = "no_data"  # not enough data to compute features; the model is not asked
CALLED = (OK, REFUSED, LLM_ERROR)

PROMPT_RULES = (
    "Use only the facts given in this message. The JSON features were computed by ATLAS from "
    "stored market and account data and are authoritative: do not recompute, contradict or "
    "embellish them, and do not cite numbers that are not in them. You give context and "
    "explanation only; you never recommend specific orders, position sizes, or changes to "
    "risk limits or configuration. Keep it short and concrete."
)


class Narrative(BaseModel):
    """Default narrative schema: a short explanation of the features."""

    summary: str = Field(max_length=1500)
    key_points: list[str] = Field(max_length=6)
    risks: list[str] = Field(max_length=5)
    data_gaps: list[str] = Field(
        max_length=5, description="What information was missing or insufficient."
    )


@dataclass(frozen=True)
class AgentSpec[T: BaseModel]:
    name: str
    prompt_version: str
    system: str
    schema: type[T]
    # Post-validation against the features; raise LLMSchemaError to reject the output.
    check: Callable[[T, dict[str, Any]], None] | None = None


@dataclass
class AgentInput:
    scope: str
    as_of: date
    features: dict[str, Any]
    extra: str = ""  # additional prompt text, e.g. wrapped untrusted news
    has_data: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


def jsonable(value: Any) -> Any:
    """Plain JSON types; Decimals become strings so money never turns into a float."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 6)
    return value


def input_hash(spec: AgentSpec[Any], inp: AgentInput, model: str | None) -> str:
    payload = json.dumps(
        {
            "agent": spec.name,
            "v": spec.prompt_version,
            "scope": inp.scope,
            "features": jsonable(inp.features),
            "extra": inp.extra,
            "model": model,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def calls_today(session: Session, now: datetime) -> int:
    start = datetime.combine(now.astimezone(NY).date(), time.min, NY).astimezone(UTC)
    return int(
        session.scalar(
            select(func.count())
            .select_from(AgentReport)
            .where(AgentReport.created_at >= start, AgentReport.status.in_(CALLED))
        )
        or 0
    )


def build_prompt(spec: AgentSpec[Any], inp: AgentInput) -> str:
    features = json.dumps(jsonable(inp.features), indent=1, sort_keys=True)
    parts = [
        f"Agent: {spec.name}. Scope: {inp.scope}. As of session: {inp.as_of.isoformat()}.",
        f"Features (computed by ATLAS, authoritative):\n```json\n{features}\n```",
    ]
    if inp.extra:
        parts.append(inp.extra)
    parts.append(PROMPT_RULES)
    return "\n\n".join(parts)


def run_agent(
    session: Session,
    spec: AgentSpec[Any],
    inp: AgentInput,
    provider: LLMProvider,
    *,
    now: datetime,
    max_calls_per_day: int,
    model: str | None = None,
) -> AgentReport:
    llm_enabled = not isinstance(provider, DisabledProvider)
    digest = input_hash(spec, inp, model if llm_enabled else None)
    cached = session.scalars(
        select(AgentReport)
        .where(
            AgentReport.agent == spec.name,
            AgentReport.input_hash == digest,
            AgentReport.status.in_((OK, NO_LLM, NO_DATA)),
        )
        .order_by(AgentReport.created_at.desc())
        .limit(1)
    ).first()
    if cached is not None:
        return cached  # same inputs: reuse rather than pay for an identical answer

    report = AgentReport(
        created_at=now,
        agent=spec.name,
        scope=inp.scope,
        as_of=inp.as_of,
        prompt_version=spec.prompt_version,
        input_hash=digest,
        features=jsonable({**inp.features, **({"meta": inp.meta} if inp.meta else {})}),
        narrative=None,
        provider=provider.name,
    )
    if not inp.has_data:
        report.status = NO_DATA
    elif not llm_enabled:
        report.status = NO_LLM
    elif calls_today(session, now) >= max_calls_per_day:
        report.status, report.error = BUDGET, f"daily LLM cap of {max_calls_per_day} reached"
    else:
        try:
            result = provider.structured(
                system=spec.system, prompt=build_prompt(spec, inp), schema=spec.schema
            )
            if spec.check is not None:
                spec.check(result.output, inp.features)
            report.narrative = result.output.model_dump(mode="json")
            report.status = OK
            report.model = result.model
            report.input_tokens, report.output_tokens = result.input_tokens, result.output_tokens
        except LLMRefusalError as exc:
            report.status, report.error = REFUSED, str(exc)
        except LLMSchemaError as exc:
            report.status, report.error = LLM_ERROR, f"invalid output: {str(exc)[:500]}"
        except LLMError as exc:
            report.status, report.error = LLM_ERROR, str(exc)[:500]
    session.add(report)
    session.flush()
    log.info(
        "agent_report",
        agent=spec.name,
        scope=inp.scope,
        status=report.status,
        tokens=report.input_tokens + report.output_tokens,
    )
    return report


def latest_report(session: Session, agent: str, scope: str = "market") -> AgentReport | None:
    return session.scalars(
        select(AgentReport)
        .where(AgentReport.agent == agent, AgentReport.scope == scope)
        .order_by(AgentReport.created_at.desc(), AgentReport.id.desc())
        .limit(1)
    ).first()
