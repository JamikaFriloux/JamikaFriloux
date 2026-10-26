import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { OrderRow } from "@/lib/api";
import { fmtTime, fmtUsd } from "@/lib/utils";
import { STATUS_TONE } from "./labels";

export function OrdersTable({ orders }: { orders: OrderRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Paper orders</CardTitle>
        <span className="text-[11px] text-muted">Entries, exits and broker-side protective stops</span>
      </CardHeader>
      <CardContent>
        {orders.length === 0 ? (
          <p className="text-sm text-muted">
            No orders. Only strategies in PAPER status can order, and promotion requires the Phase 4 validation gates.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-[11px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="py-2 font-medium">Submitted</th>
                  <th className="py-2 font-medium">Order</th>
                  <th className="py-2 text-right font-medium">Qty</th>
                  <th className="py-2 text-right font-medium">Price</th>
                  <th className="py-2 text-right font-medium">Filled</th>
                  <th className="py-2 font-medium pl-4">State</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.client_order_id} className="border-t border-line">
                    <td className="py-2 text-xs text-muted">{fmtTime(o.submitted_at ?? o.created_at)}</td>
                    <td className="py-2">
                      <span className="font-medium">{o.symbol}</span>{" "}
                      <span className={o.side === "buy" ? "text-gain" : "text-loss"}>{o.side}</span>{" "}
                      <span className="text-xs text-muted">{o.purpose?.replace("_", " ") ?? o.type} · {o.time_in_force}</span>
                    </td>
                    <td className="num py-2 text-right">{o.qty}</td>
                    <td className="num py-2 text-right">
                      {o.type === "stop" ? `stop ${fmtUsd(o.stop_price)}` : fmtUsd(o.limit_price)}
                    </td>
                    <td className="num py-2 text-right">
                      {o.filled_qty && Number(o.filled_qty) > 0 ? `${o.filled_qty} @ ${fmtUsd(o.filled_avg_price)}` : "—"}
                    </td>
                    <td className="py-2 pl-4" title={o.last_error ?? undefined}>
                      <Badge tone={STATUS_TONE[o.state] ?? "neutral"}>{o.state}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
