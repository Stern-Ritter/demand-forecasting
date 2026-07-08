from enum import Enum


class RoleName(str, Enum):
    USER = 'user'
    ADMIN = 'admin'


class Currency(str, Enum):
    RUB = 'RUB'
    USD = 'USD'
    EUR = 'EUR'


class TransactionType(str, Enum):
    DEPOSIT = 'deposit'
    WITHDRAWAL = 'withdrawal'


class ForecastStatus(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
