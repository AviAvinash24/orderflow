import { createContext, useContext, useMemo, useState } from 'react'

const CartContext = createContext(null)

export function CartProvider({ children }) {
  const [items, setItems] = useState([])

  const value = useMemo(
    () => ({
      items,
      count: items.reduce((n, i) => n + i.quantity, 0),
      add(product, quantity = 1) {
        setItems((prev) => {
          const existing = prev.find((i) => i.product_id === product.id)
          if (existing) {
            return prev.map((i) =>
              i.product_id === product.id
                ? {
                    ...i,
                    quantity: Math.min(
                      i.quantity + quantity,
                      product.quantity_available,
                    ),
                  }
                : i,
            )
          }
          return [
            ...prev,
            {
              product_id: product.id,
              name: product.name,
              price: product.price,
              sku: product.sku,
              quantity: Math.min(quantity, product.quantity_available),
              quantity_available: product.quantity_available,
            },
          ]
        })
      },
      setQuantity(productId, quantity) {
        setItems((prev) =>
          prev
            .map((i) =>
              i.product_id === productId
                ? {
                    ...i,
                    quantity: Math.max(
                      0,
                      Math.min(quantity, i.quantity_available),
                    ),
                  }
                : i,
            )
            .filter((i) => i.quantity > 0),
        )
      },
      remove(productId) {
        setItems((prev) => prev.filter((i) => i.product_id !== productId))
      },
      clear() {
        setItems([])
      },
    }),
    [items],
  )

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used within CartProvider')
  return ctx
}
