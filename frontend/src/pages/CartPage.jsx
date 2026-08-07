import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, formatError } from '../api'
import { useAuth } from '../auth'
import { useCart } from '../cart'

function money(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
  }).format(Number(value))
}

export default function CartPage() {
  const { token } = useAuth()
  const { items, setQuantity, remove, clear, count } = useCart()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const total = items.reduce(
    (sum, item) => sum + Number(item.price) * item.quantity,
    0,
  )

  async function placeOrder() {
    setError('')
    setBusy(true)
    try {
      const order = await api.createOrder(
        items.map(({ product_id, quantity }) => ({ product_id, quantity })),
        token,
      )
      clear()
      navigate(`/orders/${order.id}`)
    } catch (err) {
      setError(formatError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="page fade-in">
      <header className="page-header">
        <div>
          <h1>Cart</h1>
          <p className="lede">
            Placing an order reserves stock until payment, cancel, or expiry.
          </p>
        </div>
        <Link className="btn ghost" to="/">
          Back to catalog
        </Link>
      </header>

      {count === 0 ? (
        <p className="muted">Your cart is empty.</p>
      ) : (
        <>
          <ul className="cart-list">
            {items.map((item) => (
              <li key={item.product_id} className="cart-row">
                <div>
                  <h2>{item.name}</h2>
                  <p className="meta">
                    {item.sku} · {money(item.price)} each
                  </p>
                </div>
                <div className="cart-controls">
                  <label>
                    Qty
                    <input
                      type="number"
                      min={1}
                      max={item.quantity_available}
                      value={item.quantity}
                      onChange={(e) =>
                        setQuantity(item.product_id, Number(e.target.value) || 0)
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="linkish"
                    onClick={() => remove(item.product_id)}
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>

          <div className="checkout-bar">
            <p>
              Total <strong>{money(total)}</strong>
            </p>
            {error ? <p className="banner error">{error}</p> : null}
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={placeOrder}
            >
              {busy ? 'Placing…' : 'Place order'}
            </button>
          </div>
        </>
      )}
    </section>
  )
}
