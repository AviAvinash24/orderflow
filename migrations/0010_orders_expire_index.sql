-- Speeds up: status='placed' AND expires_at <= now()
CREATE INDEX IF NOT EXISTS idx_orders_placed_expires_at
    ON orders (expires_at)
    WHERE status = 'placed' AND expires_at IS NOT NULL;