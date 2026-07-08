from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, String, Boolean, ForeignKey, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
import bcrypt

from typing import List, Optional

from .base import BaseEntity
from .enums import Currency, RoleName
from .finance import Transaction, Balance
from .forecast import ForecastJob


class User(BaseEntity):
    __tablename__ = "users"

    login = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    display_name = Column(String(128), nullable=False)
    password_hash = Column("password_hash", String(256), nullable=False)
    is_active = Column(Boolean, default=True)

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)

    balance: Mapped["Balance"] = relationship(
        "Balance",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    forecast_jobs: Mapped[List["ForecastJob"]] = relationship(
        "ForecastJob",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    role: Mapped["Role"] = relationship("Role", back_populates="users")

    def __init__(self, login: str, email: str, display_name: str,
                 password: str, role_id: int):
        self.login = login
        self.email = email
        self.display_name = display_name
        self.role_id = role_id
        self.is_active = True
        self.set_password(password)

    def set_password(self, password: str):
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode(), salt).decode()

    def verify_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())

    def change_password(self, old_password: str, new_password: str) -> bool:
        if self.verify_password(old_password):
            self.set_password(new_password)
            self.update_timestamp()
            return True
        return False

    def add_transaction(self, transaction: Transaction):
        self.transactions.append(transaction)
        self.update_timestamp()


class Role(BaseEntity):
    __tablename__ = "roles"

    name = Column(SQLAlchemyEnum(RoleName), nullable=False, unique=True)

    users: Mapped[List["User"]] = relationship("User", back_populates="role")


class RoleCreate(BaseModel):
    name: RoleName


class UserCreate(BaseModel):
    login: str
    password: str
    email: EmailStr
    display_name: str


class UserUpdate(BaseModel):
    login: Optional[str] = None
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    login: str
    password: str


class UserChangePassword(BaseModel):
    old_password: str
    new_password: str
