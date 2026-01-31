"""Order document model for MongoDB."""

from datetime import datetime
from pydantic import BaseModel, Field

from src.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType


class OrderDocument(BaseModel):
    """MongoDB document for order persistence."""

    id: str = Field(alias="_id")
    strategy_id: str
    symbol: str
    exchange: str
    side: str
    order_type: str
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    status: str
    filled_quantity: float = 0.0
    filled_price: float | None = None
    broker_order_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"populate_by_name": True}

    @classmethod
    def from_aggregate(cls, order: OrderAggregate) -> "OrderDocument":
        return cls(
            _id=order.id,
            strategy_id=order.strategy_id,
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=order.quantity,
            price=order.price,
            stop_price=order.stop_price,
            status=order.status.value,
            filled_quantity=order.filled_quantity,
            filled_price=order.filled_price,
            broker_order_id=order.broker_order_id,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )

    def to_aggregate(self) -> OrderAggregate:
        return OrderAggregate(
            id=self.id,
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            exchange=self.exchange,
            side=OrderSide(self.side),
            order_type=OrderType(self.order_type),
            quantity=self.quantity,
            price=self.price,
            stop_price=self.stop_price,
            status=OrderStatus(self.status),
            filled_quantity=self.filled_quantity,
            filled_price=self.filled_price,
            broker_order_id=self.broker_order_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
