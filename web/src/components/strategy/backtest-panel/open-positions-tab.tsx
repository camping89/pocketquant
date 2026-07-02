import type { BacktestPosition } from '../../../api/backtest-api'
import { fmtDateTime, fmtPrice } from './positions-utils'
import { useTimezone } from '../../../lib/use-timezone'
import { formatQty } from '../../../lib/number-format'

/** Still-open lots at run-end — a small, non-paged list (kept out of the paged
 *  closed-trades table so cursor paging only ever walks ``backtest_trades``). */
export function OpenPositionsTab({ positions }: { positions: BacktestPosition[] }) {
  const { mode } = useTimezone()

  if (positions.length === 0) {
    return (
      <div className="backtest-panel__tab-content">
        <div className="empty-state">No open positions at run end.</div>
      </div>
    )
  }

  return (
    <div className="backtest-panel__tab-content positions-tab">
      <div className="positions-tab__toolbar">
        <div className="positions-tab__footer">
          <span>{positions.length} open</span>
        </div>
      </div>
      <div className="positions-tab__table-wrap">
        <table className="positions-table">
          <thead>
            <tr>
              <th className="positions-table__th positions-table__th--num">#</th>
              <th className="positions-table__th">Entry Time</th>
              <th className="positions-table__th">Dir</th>
              <th className="positions-table__th positions-table__th--num">Entry</th>
              <th className="positions-table__th positions-table__th--num">Qty</th>
              <th className="positions-table__th positions-table__th--num">SL</th>
              <th className="positions-table__th positions-table__th--num">TP</th>
              <th className="positions-table__th positions-table__th--num">Fee</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p, i) => {
              const dir = p.direction ?? 'LONG'
              return (
                <tr key={i} className="positions-table__row">
                  <td className="positions-table__td--num">{i + 1}</td>
                  <td>{fmtDateTime(p.entry_time, mode)}</td>
                  <td>
                    <span className={`direction-badge direction-badge--${dir.toLowerCase()}`}>{dir}</span>
                  </td>
                  <td className="positions-table__td--num">{fmtPrice(p.entry_price)}</td>
                  <td className="positions-table__td--num">{formatQty(p.quantity)}</td>
                  <td className="positions-table__td--num">{p.sl_price != null ? fmtPrice(p.sl_price) : '—'}</td>
                  <td className="positions-table__td--num">{p.tp_price != null ? fmtPrice(p.tp_price) : '—'}</td>
                  <td className="positions-table__td--num">{p.commission.toFixed(4)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
