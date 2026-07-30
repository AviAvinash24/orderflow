from typing import Literal

from pydantic import BaseModel


class PaymentWebhookRequest(BaseModel):
    order_id: str
    gateway_event_id: str
    status: Literal["succeeded", "failed"]


class PaymentWebhookResponse(BaseModel):
    ok: bool = True