import { useState } from 'react'
import { Eye, ShoppingCart } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import type { ExecutionOrderRow } from '../api'
import { getExecutionOrders } from '../api'
import { compactTime, firstJsonValue, formatNumber, formatPercent, statusClass } from './format'
import { EmptyState, Panel } from './primitives'

export function ExecutionOrdersPanel({
  symbol,
  interval,
  limit,
}: {
  symbol: string
  interval: string
  limit: number
}) {
  const [selectedOrder, setSelectedOrder] = useState<ExecutionOrderRow | null>(null)
  const ordersQuery = useQuery({
    queryKey: ['execution-orders', symbol, interval, limit],
    queryFn: () => getExecutionOrders({ symbol, interval, limit }),
    refetchInterval: 30_000,
  })

  return (
    <Panel title="Execution / Orders" icon={<ShoppingCart size={17} />}>
      {ordersQuery.error ? <div className="empty">{ordersQuery.error.message}</div> : null}
      {ordersQuery.data?.orders.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Side</th>
                <th>Order Status</th>
                <th>Execution</th>
                <th>Order ID</th>
                <th>Decision</th>
                <th>Qty</th>
                <th>Quote</th>
                <th>Avg Price</th>
                <th>Realized PnL</th>
                <th>Commission</th>
                <th>Reason</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {ordersQuery.data.orders.map((row) => (
                <tr key={`${row.exchange_order_id}:${row.decision_journal_id}`}>
                  <td>{compactTime(row.created_at ?? row.reference_time)}</td>
                  <td>
                    <span className={`badge ${statusClass(row.side === 'buy' ? 'up' : 'down')}`}>{row.side}</span>
                  </td>
                  <td>
                    <span className={`badge ${statusClass(row.order_status)}`}>{row.order_status}</span>
                  </td>
                  <td>{row.execution_status}</td>
                  <td>{row.exchange_order_id ?? '-'}</td>
                  <td>{row.decision_journal_id ? `#${row.decision_journal_id}` : '-'}</td>
                  <td>{formatNumber(row.executed_quantity, 8)}</td>
                  <td>{`$${formatNumber(row.quote_quantity, 2)}`}</td>
                  <td>{row.average_price ? `$${formatNumber(row.average_price, 2)}` : '-'}</td>
                  <td>
                    {row.realized_pnl_usdt === null
                      ? '-'
                      : `${row.realized_pnl_usdt >= 0 ? '+' : ''}$${formatNumber(row.realized_pnl_usdt, 2)} (${formatPercent(row.realized_pnl_pct)})`}
                  </td>
                  <td className="truncate">{Object.keys(row.commission).length ? firstJsonValue(row.commission) : '-'}</td>
                  <td className="truncate">{row.decision_reason || '-'}</td>
                  <td className="actions">
                    <button type="button" className="icon-button" title="View raw order" onClick={() => setSelectedOrder(row)}>
                      <Eye size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState message={ordersQuery.isLoading ? 'Loading execution orders...' : 'No submitted Spot Demo orders found.'} />
      )}
      {selectedOrder ? (
        <div className="drawer-backdrop" onClick={() => setSelectedOrder(null)}>
          <aside className="drawer" onClick={(event) => event.stopPropagation()}>
            <header>
              <span>{`Order ${selectedOrder.exchange_order_id ?? '-'}`}</span>
              <button type="button" onClick={() => setSelectedOrder(null)}>Close</button>
            </header>
            <pre>{JSON.stringify(selectedOrder, null, 2)}</pre>
          </aside>
        </div>
      ) : null}
    </Panel>
  )
}
