import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { getStatus } from "@/lib/api";
import { fmtTime } from "@/lib/utils";

export default async function SettingsPage() {
  const s = await getStatus();
  const broker = s.services.find((x) => x.service === "broker");
  return (
    <>
      <PageHeader title="Settings" subtitle="Configuration is code-reviewed and file-based. This page is read-only by design." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Broker connection</CardTitle>
            {broker ? (
              <Badge tone={broker.status === "ok" ? "gain" : broker.status === "error" ? "loss" : "warn"}>{broker.status}</Badge>
            ) : (
              <Badge>never synced</Badge>
            )}
          </CardHeader>
          <CardContent className="text-sm text-muted">
            Alpaca <span className="text-fg">paper</span> endpoint · last sync {fmtTime(broker?.last_seen)}
            {s.account ? <> · account status <span className="text-fg">{s.account.status}</span></> : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Trading mode</CardTitle>
            <Badge tone="warn">PAPER ONLY</Badge>
          </CardHeader>
          <CardContent className="text-sm text-muted">
            There is no live-trading toggle. Live trading requires a separate deployment, separate credentials,
            independent review and explicit owner authorization (see docs/security.md).
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Risk configuration</CardTitle></CardHeader>
          <CardContent className="text-sm text-muted">
            <code className="num">config/policy.yaml</code> · version {s.policy.version} ·{" "}
            <span className="num">{s.policy.sha256.slice(0, 16)}…</span>. Changes require a reviewed commit and restart.
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Notifications · Schedules · Data · Security</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm text-muted">
            <p>Telegram: configured via <code className="num">ATLAS_TELEGRAM_*</code> environment variables.</p>
            <p>Schedules: Celery beat, America/New_York, NYSE calendar aware.</p>
            <p>Market data: Alpaca feed set by <code className="num">ALPACA_DATA_FEED</code> (default IEX).</p>
            <p>Security: Argon2id passwords, short-lived tokens, role-based access, append-only audit log.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
