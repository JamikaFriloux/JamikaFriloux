/** Human-readable names for risk-engine checks (keys match backend check names). */
export const CHECK_LABELS: Record<string, string> = {
  kill_switch: "kill switch engaged",
  strategy_status: "strategy not in PAPER / LIVE_CANDIDATE",
  account_snapshot: "no fresh account snapshot",
  account_not_blocked: "account blocked",
  entry_window: "outside entry window",
  market_open: "market closed",
  universe: "not in current universe",
  earnings_blackout: "no earnings clearance / blackout",
  quote: "no fresh two-sided quote",
  spread: "spread too wide",
  no_existing_exposure: "already held or ordered",
  daily_loss: "daily loss limit",
  drawdown: "drawdown limit",
  concurrent_positions: "max positions",
  trades_today: "max trades today",
  stop_below_entry: "stop not below entry",
  size: "size below one share",
  position_held: "no position to exit",
  no_pending_exit: "exit already working",
};

export const checkLabel = (name: string) => CHECK_LABELS[name] ?? name;

export const STATUS_TONE: Record<string, "gain" | "loss" | "warn" | "neutral" | "accent"> = {
  NEW: "accent",
  ORDERED: "gain",
  SHADOWED: "neutral",
  REJECTED: "loss",
  EXPIRED: "neutral",
  STOPPED_OUT: "warn",
  RESEARCH: "neutral",
  PAPER: "gain",
  LIVE_CANDIDATE: "accent",
  RETIRED: "neutral",
  FILLED: "gain",
  PARTIALLY_FILLED: "warn",
  ACKNOWLEDGED: "accent",
  SUBMITTED: "accent",
  CANCELLED: "neutral",
};
