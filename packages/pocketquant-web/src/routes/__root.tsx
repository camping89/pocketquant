import { createRootRoute, Link, Outlet } from '@tanstack/react-router'
import { SymbolSelector } from '../components/controls/symbol-selector'
import type { SelectedSymbol } from '../types/market-data'

export type RootSearchParams = SelectedSymbol

export const Route = createRootRoute({
  validateSearch: (search: Record<string, unknown>): RootSearchParams => ({
    exchange: typeof search.exchange === 'string' && search.exchange ? search.exchange : 'BINANCE',
    symbol: typeof search.symbol === 'string' && search.symbol ? search.symbol : 'BTCUSDT',
  }),
  component: RootLayout,
})

function RootLayout() {
  const { exchange, symbol } = Route.useSearch()
  const navigate = Route.useNavigate()

  const selected: SelectedSymbol = { exchange, symbol }
  const handleSymbolChange = (v: SelectedSymbol) => {
    void navigate({ search: { exchange: v.exchange, symbol: v.symbol } })
  }

  return (
    <div className="app-shell">
      <nav className="app-nav">
        <SymbolSelector value={selected} onChange={handleSymbolChange} />
        <Link to="/" search={{ exchange, symbol }} activeProps={{ className: 'active' }} activeOptions={{ exact: true }}>
          Charts
        </Link>
        <Link to="/monitor" search={{ exchange, symbol }} activeProps={{ className: 'active' }}>
          Monitor
        </Link>
      </nav>
      <Outlet />
    </div>
  )
}
