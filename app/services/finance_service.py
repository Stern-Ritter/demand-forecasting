from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select

from models.user import (
    User
)
from models.finance import (
    Balance,
    Transaction,
    DepositRequest,
    WithdrawRequest,
    TransactionFilter
)
from models.enums import Currency, TransactionType
from exceptions import (
    NotFoundException,
    BadRequestException,
    InsufficientFundsException
)


class FinanceService:
    def __init__(self, db: Session):
        self.db = db

    def get_balance(self, user_id: int) -> Balance:
        stmt = select(Balance).where(Balance.user_id == user_id)
        balance = self.db.scalar(stmt)
        if not balance:
            raise NotFoundException(
                f"Balance for user with id {user_id} not found")
        return balance

    def deposit(self, deposit_data: DepositRequest) -> Transaction:
        balance = self.get_balance(deposit_data.user_id)

        if not balance:
            raise NotFoundException(
                f"Balance for user with id {deposit_data.user_id} not found")

        if deposit_data.amount <= 0:
            raise BadRequestException("Deposit amount must be positive")

        balance.deposit(deposit_data.amount)

        transaction = Transaction(
            type=TransactionType.DEPOSIT,
            amount=deposit_data.amount,
            currency=deposit_data.currency or Currency.RUB,
            description=deposit_data.description,
            user_id=deposit_data.user_id
        )

        self.db.add(transaction)
        self.db.flush()
        return transaction

    def withdraw(self, withdraw_data: WithdrawRequest) -> Transaction:
        balance = self.get_balance(withdraw_data.user_id)

        if not balance:
            raise NotFoundException(
                f"Balance for user with id {withdraw_data.user_id} not found")

        if withdraw_data.amount <= 0:
            raise BadRequestException("Withdrawal amount must be positive")

        if balance.value < withdraw_data.amount:
            raise InsufficientFundsException(
                f"Insufficient funds. Available: {balance.value}, Requested: {withdraw_data.amount}"
            )

        balance.withdraw(withdraw_data.amount)

        transaction = Transaction(
            type=TransactionType.WITHDRAWAL,
            amount=withdraw_data.amount,
            currency=withdraw_data.currency or Currency.RUB,
            description=withdraw_data.description,
            user_id=withdraw_data.user_id
        )

        self.db.add(transaction)
        self.db.flush()
        return transaction

    def get_transaction_by_id(self, transaction_id: int) -> Transaction:
        transaction = self.db.get(Transaction, transaction_id)
        if not transaction:
            raise NotFoundException(
                f"Transaction with id {transaction_id} not found")
        return transaction

    def get_user_transactions(
        self,
        user_id: int,
        filters: Optional[TransactionFilter] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Transaction]:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFoundException(f"User with id {user_id} not found")

        stmt = select(Transaction).where(Transaction.user_id == user_id)

        if filters:
            if filters.type:
                stmt = stmt.where(Transaction.type == filters.type)
            if filters.currency:
                stmt = stmt.where(Transaction.currency == filters.currency)
            if filters.min_amount:
                stmt = stmt.where(Transaction.amount >= filters.min_amount)
            if filters.max_amount:
                stmt = stmt.where(Transaction.amount <= filters.max_amount)
            if filters.start_date:
                stmt = stmt.where(Transaction.created_at >= filters.start_date)
            if filters.end_date:
                stmt = stmt.where(Transaction.created_at <= filters.end_date)
            if filters.description:
                stmt = stmt.where(Transaction.description.ilike(
                    f"%{filters.description}%"))

        stmt = stmt.order_by(Transaction.created_at.desc()
                             ).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())
