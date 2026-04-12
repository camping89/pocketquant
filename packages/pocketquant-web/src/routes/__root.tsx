import { createRootRoute, Link, Outlet } from '@tanstack/react-router'

export const Route = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  return (
    <div className="app-shell">
      <nav className="app-nav">
        <Link to="/" activeProps={{ className: 'active' }} activeOptions={{ exact: true }}>
          Charts
        </Link>
        <Link to="/monitor" activeProps={{ className: 'active' }}>
          Monitor
        </Link>
      </nav>
      <Outlet />
    </div>
  )
}
