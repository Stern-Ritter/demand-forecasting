from pydantic import BaseModel
from sqlalchemy import Column, Float, String, ForeignKey, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column

from typing import TYPE_CHECKING, Optional
from datetime import datetime

from .base import BaseEntity
from .enums import Currency, TransactionType

if TYPE_CHECKING:
    from .user import User


class Balance(BaseEntity):
    __tablename__ = "balances"

    value = Column(Float, default=0.0, nullable=False)
    currency = Column(SQLAlchemyEnum(Currency),
                      nullable=False, default=Currency.RUB)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="balance")

    def deposit(self, amount: float):
        self.value += amount
        self.update_timestamp()

    def withdraw(self, amount: float):
        self.value -= amount
        self.update_timestamp()


class Transaction(BaseEntity):
    __tablename__ = "transactions"

    type = Column(SQLAlchemyEnum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(SQLAlchemyEnum(Currency), nullable=False)
    description = Column(String(256))
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="transactions")


class DepositRequest(BaseModel):
    user_id: int
    amount: float
    currency: Optional[Currency] = None
    description: Optional[str] = None


class WithdrawRequest(BaseModel):
    user_id: int
    amount: float
    currency: Optional[Currency] = None
    description: Optional[str] = None


class TransactionFilter(BaseModel):
    type: Optional[TransactionType] = None
    currency: Optional[Currency] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    description: Optional[str] = None
