/* eslint-disable react-refresh/only-export-components -- TanStack Router requires Route export alongside components */
import { createRootRoute, Link, Outlet } from '@tanstack/react-router'
import { TimezoneSwitcher } from '../components/layout/timezone-switcher'

export const Route = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  return (
    <div className="app-shell">
      <nav className="app-nav">
        <Link
          to="/"
          search={(prev: { symbol?: string }) => ({ symbol: prev?.symbol ?? 'BTCUSDT:BINANCE' })}
          activeProps={{ className: 'active' }}
          activeOptions={{ exact: true }}
        >
          Charts
        </Link>
        <Link to="/strategies" activeProps={{ className: 'active' }}>
          Strategies
        </Link>
        <Link to="/backtest" activeProps={{ className: 'active' }}>
          Backtest
        </Link>
        <Link to="/monitor" activeProps={{ className: 'active' }}>
          Monitor
        </Link>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', alignItems: 'center', paddingRight: 4 }}>
          <TimezoneSwitcher />
        </div>
      </nav>
      <Outlet />
    </div>
  )
}
