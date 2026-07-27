CREATE TYPE payment_status AS ENUM ('succeeded', 'failed');

CREATE TABLE payment_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id),
    gateway_event_id TEXT NOT NULL UNIQUE,
    status payment_status NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);