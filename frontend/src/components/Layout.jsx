import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import { useCart } from '../cart'

export default function Layout() {
  const { user, logout } = useAuth()
  const { count } = useCart()

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          Orderflow
        </NavLink>
        <nav>
          <NavLink to="/" end>
            Catalog
          </NavLink>
          <NavLink to="/cart">
            Cart{count > 0 ? ` (${count})` : ''}
          </NavLink>
        </nav>
        <div className="userchip">
          <span>{user?.email}</span>
          <button type="button" className="linkish" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
