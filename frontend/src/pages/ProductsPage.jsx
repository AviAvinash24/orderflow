import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, formatError } from '../api'
import { useCart } from '../cart'

function money(value) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
  }).format(Number(value))
}

export default function ProductsPage() {
  const { add } = useCart()
  const [products, setProducts] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [addedId, setAddedId] = useState(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const data = await api.listProducts()
        if (alive) setProducts(data)
      } catch (err) {
        if (alive) setError(formatError(err))
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  function onAdd(product) {
    add(product, 1)
    setAddedId(product.id)
    window.setTimeout(() => setAddedId((id) => (id === product.id ? null : id)), 900)
  }

  return (
    <section className="page fade-in">
      <header className="page-header">
        <div>
          <h1>Catalog</h1>
          <p className="lede">Live stock from the Orderflow inventory service.</p>
        </div>
        <Link className="btn ghost" to="/cart">
          Review cart
        </Link>
      </header>

      {error ? <p className="banner error">{error}</p> : null}
      {loading ? <p className="muted">Loading products…</p> : null}

      {!loading && !error && products.length === 0 ? (
        <p className="muted">No products seeded yet. Run migrations against the API.</p>
      ) : null}

      <ul className="product-list">
        {products.map((product, index) => {
          const out = product.quantity_available <= 0
          return (
            <li
              key={product.id}
              className="product-row"
              style={{ animationDelay: `${index * 40}ms` }}
            >
              <div>
                <h2>{product.name}</h2>
                <p className="meta">
                  {product.sku} · {money(product.price)}
                </p>
              </div>
              <div className="product-actions">
                <span className={`stock ${out ? 'low' : ''}`}>
                  {out ? 'Out of stock' : `${product.quantity_available} available`}
                </span>
                <button
                  type="button"
                  className="btn primary"
                  disabled={out}
                  onClick={() => onAdd(product)}
                >
                  {addedId === product.id ? 'Added' : 'Add'}
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
