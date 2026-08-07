import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, formatError } from '../api'
import { useAuth } from '../auth'

function money(value) {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
  }).format(Number(value))
}

function formatWhen(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export default function OrderPage() {
  const { orderId } = useParams()
  const { token } = useAuth()
  const [order, setOrder] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const data = await api.getOrder(orderId, token)
      setOrder(data)
    } catch (err) {
      setError(formatError(err))
    }
  }, [orderId, token])

  useEffect(() => {
    load()
  }, [load])

  async function cancel() {
    setBusy('cancel')
    setNotice('')
    setError('')
    try {
      const data = await api.cancelOrder(orderId, token)
      setOrder(data)
      setNotice('Order cancelled; reserved stock released.')
    } catch (err) {
      setError(formatError(err))
    } finally {
      setBusy('')
    }
  }

  async function pay() {
    setBusy('pay')
    setNotice('')
    setError('')
    try {
      await api.simulatePayment(orderId, 'succeeded')
      await load()
      setNotice('Payment webhook applied.')
    } catch (err) {
      setError(formatError(err))
    } finally {
      setBusy('')
    }
  }

  if (!order && !error) {
    return (
      <section className="page">
        <p className="muted">Loading order…</p>
      </section>
    )
  }

  const canAct = order && (order.status === 'placed' || order.status === 'paid')
  const canPay = order?.status === 'placed'

  return (
    <section className="page fade-in">
      <header className="page-header">
        <div>
          <h1>Order</h1>
          <p className="lede mono">{orderId}</p>
        </div>
        <Link className="btn ghost" to="/">
          Catalog
        </Link>
      </header>

      {error ? <p className="banner error">{error}</p> : null}
      {notice ? <p className="banner ok">{notice}</p> : null}

      {order ? (
        <>
          <div className="order-summary">
            <div>
              <span className="label">Status</span>
              <p className={`status status-${order.status}`}>{order.status}</p>
            </div>
            <div>
              <span className="label">Total</span>
              <p>{money(order.total_amount)}</p>
            </div>
            <div>
              <span className="label">Reservation expires</span>
              <p>{formatWhen(order.expires_at)}</p>
            </div>
          </div>

          <ul className="cart-list">
            {order.items.map((item) => (
              <li key={item.product_id} className="cart-row">
                <div>
                  <h2 className="mono">{item.product_id}</h2>
                  <p className="meta">
                    Qty {item.quantity} · {money(item.unit_price_at_purchase)} each
                  </p>
                </div>
              </li>
            ))}
          </ul>

          <div className="action-row">
            {canPay ? (
              <button
                type="button"
                className="btn primary"
                disabled={Boolean(busy)}
                onClick={pay}
              >
                {busy === 'pay' ? 'Paying…' : 'Simulate payment'}
              </button>
            ) : null}
            {canAct ? (
              <button
                type="button"
                className="btn danger"
                disabled={Boolean(busy)}
                onClick={cancel}
              >
                {busy === 'cancel' ? 'Cancelling…' : 'Cancel order'}
              </button>
            ) : null}
            <button type="button" className="btn ghost" onClick={load}>
              Refresh
            </button>
          </div>
        </>
      ) : null}
    </section>
  )
}
