import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { AGENT_TITLE, REGIME_TONE, REPORT_STATUS, SENTIMENT_TONE } from "@/components/intelligence/labels";
import { RunAgentsButton } from "@/components/intelligence/run-agents-button";
import { getIntelligence, getMe, getNews, type AgentReport, type NewsFeed } from "@/lib/api";
import { fmtTime, fmtUsd } from "@/lib/utils";

type Row = Record<string, string | number | boolean | null>;
type Narrative = {
  summary?: string;
  key_points?: string[];
  risks?: string[];
  data_gaps?: string[];
  notable?: { symbol: string; note: string }[];
  themes?: string[];
};

const pct = (v: unknown) => (typeof v === "number" ? `${v > 0 ? "+" : ""}${v.toFixed(2)}%` : "—");
const num = (v: unknown, d = 2) => (typeof v === "number" ? v.toFixed(d) : "—");

export default async function IntelligencePage() {
  const [intel, news, me] = await Promise.all([getIntelligence(), getNews(40), getMe()]);
  const a = intel.agents;
  const providers = new Set(Object.values(a).flatMap((r) => (r?.provider ? [r.provider] : [])));
  return (
    <>
      <PageHeader title="AI Intelligence" subtitle="Research agents: deterministic analysis with optional AI explanations">
        {me.role !== "viewer" ? <RunAgentsButton /> : null}
      </PageHeader>
      <p className="mb-4 max-w-3xl text-sm text-muted">
        Advisory only. Agent reports never place orders, change risk limits or touch configuration, and nothing in the
        trading path reads them. Labels and numbers are computed by ATLAS from stored data; the language model, when
        enabled, only explains them, and its output is schema-checked. News text is treated as untrusted input.
      </p>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span>LLM provider: {providers.size ? [...providers].join(", ") : "—"}</span>
        <span>·</span>
        <span className="num">
          Today: {intel.llm_usage_today.calls} calls, {intel.llm_usage_today.input_tokens + intel.llm_usage_today.output_tokens} tokens
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RegimeCard report={a.market_intelligence} />
        <PerformanceCard report={a.performance_analysis} />
      </div>
      <div className="mt-4">
        <TechnicalCard report={a.technical_analysis} />
      </div>
      <div className="mt-4">
        <NewsCard report={a.news_sentiment} news={news} />
      </div>
      <div className="mt-4">
        <OperationsCard report={a.operations} />
      </div>
    </>
  );
}

function AgentHeader({ name, report }: { name: string; report: AgentReport | null }) {
  const st = report ? (REPORT_STATUS[report.status] ?? { tone: "neutral" as const, label: report.status }) : null;
  return (
    <CardHeader>
      <CardTitle>{AGENT_TITLE[name] ?? name}</CardTitle>
      <span className="flex flex-wrap items-center justify-end gap-2">
        {report ? <span className="text-xs text-muted">{fmtTime(report.created_at)}</span> : null}
        {st ? <Badge tone={st.tone}>{st.label}</Badge> : <Badge>not run yet</Badge>}
      </span>
    </CardHeader>
  );
}

function NarrativeBlock({ report }: { report: AgentReport }) {
  const n = report.narrative as Narrative | null;
  if (!n) {
    return (
      <p className="border-t border-line pt-3 text-xs text-muted">
        No AI narrative{report.error ? `: ${report.error}` : report.status === "no_llm" ? " (LLM disabled)" : ""}.
      </p>
    );
  }
  const list = (title: string, items?: string[]) =>
    items && items.length ? (
      <div>
        <div className="text-[11px] uppercase tracking-wider text-muted">{title}</div>
        <ul className="mt-1 list-disc space-y-0.5 pl-4">
          {items.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      </div>
    ) : null;
  return (
    <div className="space-y-2 border-t border-line pt-3 text-sm">
      <div className="flex items-center gap-2 text-[11px] text-muted">
        <Badge tone="accent">AI</Badge>
        <span className="num">
          {report.model} · {report.input_tokens + report.output_tokens} tokens
        </span>
      </div>
      {n.summary ? <p>{n.summary}</p> : null}
      {list("Key points", n.key_points)}
      {list("Themes", n.themes)}
      {list("Risks", n.risks)}
      {list("Data gaps", n.data_gaps)}
    </div>
  );
}

function Facts({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 text-xs sm:grid-cols-2">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-3 border-t border-line py-1">
          <dt className="text-muted">{k}</dt>
          <dd className="num text-right">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function RegimeCard({ report }: { report: AgentReport | null }) {
  const f = (report?.features ?? {}) as Row;
  const regime = typeof f.regime === "string" ? f.regime : null;
  return (
    <Card>
      <AgentHeader name="market_intelligence" report={report} />
      <CardContent className="space-y-3">
        {!report ? (
          <p className="text-sm text-muted">Runs premarket and after the close.</p>
        ) : regime === "unavailable" || !regime ? (
          <p className="text-sm text-muted">Regime unavailable: {String(f.reason ?? "not enough data")}.</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={REGIME_TONE[regime] ?? "neutral"}>{regime.replace(/_/g, " ")}</Badge>
              {f.stale ? <Badge tone="warn">stale data</Badge> : null}
              <span className="text-xs text-muted">
                {String(f.benchmark)} · session {String(f.as_of)} · trend {String(f.trend)}, volatility {String(f.volatility)}
              </span>
            </div>
            <Facts
              rows={[
                ["Close", num(f.close)],
                ["vs SMA200", pct(f.close_vs_sma200_pct)],
                ["SMA50 / SMA200", `${num(f.sma50)} / ${num(f.sma200)}`],
                ["SMA50 slope (20d)", pct(f.sma50_slope_20d_pct)],
                ["Realised vol (20d, ann.)", pct(f.realised_vol_20d_pct).replace("+", "")],
                ["Vol percentile (1y)", num(f.vol_percentile_1y, 1)],
                ["From 1y high", pct(f.drawdown_from_1y_high_pct)],
                [
                  "Breadth above SMA50",
                  f.breadth_above_sma50_pct == null ? "—" : `${num(f.breadth_above_sma50_pct, 1)}% of ${f.breadth_symbols}`,
                ],
              ]}
            />
            <p className="text-[11px] text-muted">
              Rule: trend from close vs SMA50/SMA200; volatility class from the 20-day realised vol percentile. Breadth
              covers the ingested symbols, not the whole market.
            </p>
          </>
        )}
        {report ? <NarrativeBlock report={report} /> : null}
      </CardContent>
    </Card>
  );
}

function PerformanceCard({ report }: { report: AgentReport | null }) {
  const f = (report?.features ?? {}) as Record<string, unknown>;
  const acct = f.account as Row | null | undefined;
  const sig = f.signals as { total: number; by_status: Record<string, number> } | undefined;
  const rd = f.risk_decisions as { total: number; approved: number; rejected: number; top_failed_checks: Record<string, number> } | undefined;
  const ord = f.orders as { total: number } | undefined;
  const strategies = (f.strategies as { id: string; status: string }[] | undefined) ?? [];
  return (
    <Card>
      <AgentHeader name="performance_analysis" report={report} />
      <CardContent className="space-y-3">
        {!report ? (
          <p className="text-sm text-muted">Runs premarket and after the close.</p>
        ) : (
          <>
            <Facts
              rows={[
                ["Equity", acct ? fmtUsd(String(acct.equity)) : "unavailable"],
                ["Day P&L", acct ? fmtUsd(String(acct.day_pl), true) : "unavailable"],
                ["Drawdown / limit", acct ? `${fmtUsd(String(acct.drawdown))} / ${fmtUsd(String(acct.drawdown_limit))}` : "unavailable"],
                ["Cooldown sessions left", acct ? String(acct.drawdown_cooldown_sessions_remaining) : "—"],
                ["Signals (5 sessions)", sig ? String(sig.total) : "—"],
                ["Risk decisions", rd ? `${rd.approved} approved / ${rd.rejected} rejected` : "—"],
                ["Orders (5 sessions)", ord ? String(ord.total) : "—"],
                ["Strategies", strategies.map((s) => `${s.id}: ${s.status}`).join(", ") || "—"],
              ]}
            />
            {rd && Object.keys(rd.top_failed_checks).length ? (
              <p className="text-xs text-muted">
                Most frequent rejections:{" "}
                {Object.entries(rd.top_failed_checks)
                  .map(([k, v]) => `${k} (${v})`)
                  .join(", ")}
              </p>
            ) : null}
          </>
        )}
        {report ? <NarrativeBlock report={report} /> : null}
      </CardContent>
    </Card>
  );
}

function TechnicalCard({ report }: { report: AgentReport | null }) {
  const f = (report?.features ?? {}) as Record<string, unknown>;
  const rows = (f.symbols as Row[] | undefined) ?? [];
  const notes = new Map(((report?.narrative as Narrative | null)?.notable ?? []).map((n) => [n.symbol, n.note]));
  const stale = (f.stale as string[] | undefined) ?? [];
  const missing = (f.missing_history as string[] | undefined) ?? [];
  return (
    <Card>
      <AgentHeader name="technical_analysis" report={report} />
      <CardContent className="space-y-3">
        {rows.length === 0 ? (
          <p className="text-sm text-muted">No indicator snapshot yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="py-2 font-medium">Symbol</th>
                  <th className="py-2 font-medium">Trend</th>
                  <th className="py-2 text-right font-medium">Close</th>
                  <th className="py-2 text-right font-medium">vs SMA50</th>
                  <th className="py-2 text-right font-medium">vs SMA200</th>
                  <th className="py-2 text-right font-medium">RSI14</th>
                  <th className="py-2 text-right font-medium">ATR %</th>
                  <th className="py-2 text-right font-medium">20d</th>
                </tr>
              </thead>
              <tbody className="num">
                {rows.map((r) => (
                  <tr key={String(r.symbol)} className="border-t border-line align-top">
                    <td className="py-1.5 font-sans font-medium">
                      {String(r.symbol)}
                      {notes.has(String(r.symbol)) ? (
                        <div className="max-w-xs font-sans text-[11px] font-normal text-muted">{notes.get(String(r.symbol))}</div>
                      ) : null}
                    </td>
                    <td className="py-1.5 font-sans">
                      <Badge tone={r.trend === "up" ? "gain" : r.trend === "down" ? "loss" : "neutral"}>{String(r.trend).replace(/_/g, " ")}</Badge>
                    </td>
                    <td className="py-1.5 text-right">{num(r.close)}</td>
                    <td className="py-1.5 text-right">{pct(r.vs_sma50_pct)}</td>
                    <td className="py-1.5 text-right">{pct(r.vs_sma200_pct)}</td>
                    <td className="py-1.5 text-right">{num(r.rsi14, 1)}</td>
                    <td className="py-1.5 text-right">{num(r.atr14_pct)}</td>
                    <td className="py-1.5 text-right">{pct(r.return_20d_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {stale.length || missing.length ? (
          <p className="text-xs text-warn">
            {stale.length ? `Stale: ${stale.join(", ")}. ` : ""}
            {missing.length ? `Not enough history: ${missing.join(", ")}.` : ""}
          </p>
        ) : null}
        {report ? <NarrativeBlock report={report} /> : null}
      </CardContent>
    </Card>
  );
}

function NewsCard({ report, news }: { report: AgentReport | null; news: NewsFeed }) {
  return (
    <Card>
      <AgentHeader name="news_sentiment" report={report} />
      <CardContent className="space-y-3">
        {news.articles.length === 0 ? (
          <p className="text-sm text-muted">No news stored yet. The execution service fetches news every 30 minutes.</p>
        ) : (
          <ul className="divide-y divide-line">
            {news.articles.map((n) => (
              <li key={n.id} className="py-2">
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                  <span className="num">{fmtTime(n.published_at)}</span>
                  {n.provider ? <span>{n.provider}</span> : null}
                  <span className="num">{n.symbols.slice(0, 8).join(" ")}</span>
                  {n.assessment ? (
                    <>
                      <Badge tone={SENTIMENT_TONE[n.assessment.sentiment] ?? "neutral"}>{n.assessment.sentiment}</Badge>
                      <Badge>{n.assessment.relevance} relevance</Badge>
                    </>
                  ) : null}
                  {n.injection_suspected ? <Badge tone="loss">contains instructions — ignored</Badge> : null}
                </div>
                <div className="mt-0.5 text-sm">
                  {n.url ? (
                    <a href={n.url} target="_blank" rel="noopener noreferrer nofollow" className="hover:underline">
                      {n.headline}
                    </a>
                  ) : (
                    n.headline
                  )}
                </div>
                {n.assessment ? <div className="text-xs text-muted">{n.assessment.rationale}</div> : null}
              </li>
            ))}
          </ul>
        )}
        <p className="text-[11px] text-muted">
          External headlines, shown as received. Sentiment is shown only when the AI assessed the article; it is never guessed.
        </p>
        {report ? <NarrativeBlock report={report} /> : null}
      </CardContent>
    </Card>
  );
}

function OperationsCard({ report }: { report: AgentReport | null }) {
  const f = (report?.features ?? {}) as Record<string, unknown>;
  const services = (f.services as Row[] | undefined) ?? [];
  const dq = f.data_quality_24h as Row | undefined;
  const uni = f.universe as Row | null | undefined;
  return (
    <Card>
      <AgentHeader name="operations" report={report} />
      <CardContent className="space-y-3">
        {!report ? (
          <p className="text-sm text-muted">Runs premarket and after the close.</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="space-y-1.5">
              {services.map((s) => (
                <div key={String(s.service)} className="flex items-center justify-between gap-2 text-sm">
                  <span>{String(s.service)}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-xs text-muted">
                      {s.continuous ? (s.stale ? "no recent heartbeat" : "live") : s.last_run ? `last run ${fmtTime(String(s.last_run))}` : ""}
                    </span>
                    <Badge tone={s.stale ? "warn" : s.status === "ok" ? "gain" : "loss"}>{s.stale ? "stale" : String(s.status)}</Badge>
                  </span>
                </div>
              ))}
            </div>
            <Facts
              rows={[
                ["Kill switch", (f.kill_switch as Row | undefined)?.engaged ? "engaged" : "released"],
                ["Data-quality reports (24h)", dq ? String(dq.reports) : "—"],
                ["Failing / stale series", dq ? `${dq.failing_count} / ${dq.stale_count}` : "—"],
                ["Universe", uni ? `${uni.members} members, as of ${uni.as_of}${uni.stale ? " (stale)" : ""}` : "none"],
                ["News last fetched", f.news_last_fetched ? fmtTime(String(f.news_last_fetched)) : "never"],
              ]}
            />
          </div>
        )}
        {report ? <NarrativeBlock report={report} /> : null}
      </CardContent>
    </Card>
  );
}
