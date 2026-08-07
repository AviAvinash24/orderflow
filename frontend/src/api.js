const API_BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : 'Request failed')
    this.status = status
    this.detail = detail
  }
}

async function request(path, { method = 'GET', body, token } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (res.status === 204) return null

  const text = await res.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!res.ok) {
    const detail = data?.detail ?? data ?? res.statusText
    throw new ApiError(res.status, detail)
  }

  return data
}

export function formatError(err) {
  if (err instanceof ApiError) {
    if (typeof err.detail === 'string') return err.detail
    if (Array.isArray(err.detail)) {
      return err.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
    }
    return err.message
  }
  return err?.message || 'Something went wrong'
}

export const api = {
  signup: (email, password) =>
    request('/auth/signup', { method: 'POST', body: { email, password } }),
  login: (email, password) =>
    request('/auth/login', { method: 'POST', body: { email, password } }),
  me: (token) => request('/me', { token }),
  listProducts: () => request('/products'),
  createOrder: (items, token) =>
    request('/orders', { method: 'POST', body: { items }, token }),
  getOrder: (orderId, token) => request(`/orders/${orderId}`, { token }),
  cancelOrder: (orderId, token) =>
    request(`/orders/${orderId}/cancel`, { method: 'POST', token }),
  simulatePayment: (orderId, status = 'succeeded') =>
    request('/webhooks/payment', {
      method: 'POST',
      body: {
        order_id: orderId,
        gateway_event_id: `demo-${crypto.randomUUID()}`,
        status,
      },
    }),
}
