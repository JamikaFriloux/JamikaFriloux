export type Tone = "neutral" | "gain" | "loss" | "warn" | "accent";

export const REGIME_TONE: Record<string, Tone> = {
  risk_on: "gain",
  volatile_uptrend: "warn",
  transition: "neutral",
  downtrend: "loss",
  risk_off: "loss",
};

export const REPORT_STATUS: Record<string, { tone: Tone; label: string }> = {
  ok: { tone: "gain", label: "AI narrative" },
  no_llm: { tone: "neutral", label: "LLM disabled" },
  budget: { tone: "warn", label: "Daily LLM cap reached" },
  no_data: { tone: "warn", label: "Not enough data" },
  refused: { tone: "warn", label: "Model declined" },
  llm_error: { tone: "loss", label: "LLM error" },
};

export const SENTIMENT_TONE: Record<string, Tone> = {
  positive: "gain",
  negative: "loss",
  mixed: "warn",
  neutral: "neutral",
};

export const AGENT_TITLE: Record<string, string> = {
  market_intelligence: "Market Intelligence",
  technical_analysis: "Technical Analysis",
  news_sentiment: "News Sentiment",
  performance_analysis: "Performance",
  operations: "Operations",
};
