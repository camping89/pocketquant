import { createRootRoute, Link, Outlet } from '@tanstack/react-router'
import { SymbolSelector } from '../components/controls/symbol-selector'

export interface RootSearchParams {
  /** Composite symbol string: "{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE" */
  symbol: string
}

export const Route = createRootRoute({
  validateSearch: (search: Record<string, unknown>): RootSearchParams => ({
    symbol: typeof search.symbol === 'string' && search.symbol ? search.symbol : 'BTCUSDT:BINANCE',
  }),
  component: RootLayout,
})

function RootLayout() {
  const { symbol } = Route.useSearch()
  const navigate = Route.useNavigate()

  const handleSymbolChange = (v: string) => {
    void navigate({ search: { symbol: v } })
  }

  return (
    <div className="app-shell">
      <nav className="app-nav">
        <SymbolSelector value={symbol} onChange={handleSymbolChange} />
        <Link to="/" search={{ symbol }} activeProps={{ className: 'active' }} activeOptions={{ exact: true }}>
          Charts
        </Link>
        <Link to="/strategies" activeProps={{ className: 'active' }}>
          Strategies
        </Link>
        <Link to="/monitor" search={{ symbol }} activeProps={{ className: 'active' }}>
          Monitor
        </Link>
      </nav>
      <Outlet />
    </div>
  )
}
