-- Speeds up: status='pending' ORDER BY created_at
CREATE INDEX IF NOT EXISTS idx_outbox_pending_created_at
    ON outbox_events (created_at, id)
    WHERE status = 'pending';