from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select

from models.user import (
    User,
    Role,
    UserCreate,
    UserUpdate,
    UserLogin,
    UserChangePassword,
    RoleCreate
)
from models.finance import Balance
from models.enums import (
    RoleName,
    Currency
)
from exceptions import (
    NotFoundException,
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    ConflictException
)


class RoleService:
    def __init__(self, db: Session):
        self.db = db

    def get_role_by_id(self, role_id: int) -> Role:
        role = self.db.get(Role, role_id)
        if not role:
            raise NotFoundException(f"Role with id {role_id} not found")
        return role

    def get_role_by_name(self, role_name: RoleName) -> Role:
        stmt = select(Role).where(Role.name == role_name)
        role = self.db.scalar(stmt)
        if not role:
            raise NotFoundException(f"Role with name {role_name} not found")
        return role

    def get_all_roles(self) -> List[Role]:
        stmt = select(Role)
        return list(self.db.scalars(stmt).all())

    def create_role(self, role: RoleCreate) -> Role:
        existing_role = self.get_role_by_name(role.name)
        if existing_role:
            raise ConflictException(
                f"Role with name {role.name} already exists")

        role = Role(name=role.name)
        self.db.add(role)
        self.db.flush()
        return role

    def delete_role(self, role_id: int) -> bool:
        role = self.get_role_by_id(role_id)

        user_stmt = select(User).where(User.role_id == role_id).limit(1)
        user_exists = self.db.scalar(user_stmt)
        if user_exists:
            raise BadRequestException(
                f"Cannot delete role {role_id} as it is in use by users")

        self.db.delete(role)
        return True


class UserService:
    def __init__(self, db: Session, role_service: RoleService):
        self.db = db
        self.role_service = role_service

    def get_user_by_id(self, user_id: int) -> User:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFoundException(f"User with id {user_id} not found")
        return user

    def get_user_by_login(self, login: str) -> Optional[User]:
        stmt = select(User).where(User.login == login)
        return self.db.scalar(stmt)

    def get_user_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        return self.db.scalar(stmt)

    def create_user(self, user_data: UserCreate, role_id: int) -> User:
        try:
            self.role_service.get_role_by_id(role_id)
        except NotFoundException:
            raise BadRequestException(
                f"Role with id {role_id} not found")

        if self.get_user_by_login(user_data.login):
            raise ConflictException(
                f"User with login {user_data.login} already exists")

        if self.get_user_by_email(user_data.email):
            raise ConflictException(
                f"User with email {user_data.email} already exists")

        user = User(
            login=user_data.login,
            email=user_data.email,
            display_name=user_data.display_name,
            password=user_data.password,
            role_id=role_id
        )

        self.db.add(user)
        self.db.flush()

        balance = Balance(
            user_id=user.id,
            value=0.0,
            currency=Currency.RUB
        )
        self.db.add(balance)
        self.db.flush()

        return user

    def update_user(self, user_id: int, update_data: UserUpdate) -> User:
        user = self.get_user_by_id(user_id)
        update_dict = update_data.model_dump(exclude_unset=True)

        if not user:
            raise NotFoundException(f"User with id {user_id} not found")

        if 'email' in update_dict and update_dict['email'] != user.email:
            if self.get_user_by_email(update_dict['email']):
                raise ConflictException(
                    f"Email {update_dict['email']} already in use")

        if 'login' in update_dict and update_dict['login'] != user.login:
            if self.get_user_by_login(update_dict['login']):
                raise ConflictException(
                    f"Login {update_dict['login']} already in use")

        for field, value in update_dict.items():
            setattr(user, field, value)

        user.update_timestamp()
        self.db.flush()
        self.db.refresh(user)

        return user

    def authenticate_user(self, login_data: UserLogin) -> User:
        user = self.get_user_by_login(login_data.login)

        if not user:
            raise NotFoundException(
                f"User with login {login_data.login} not found")

        if not user.verify_password(login_data.password):
            raise UnauthorizedException("Invalid password")

        if not user.is_active:
            raise ForbiddenException("User account is deactivated")

        return user

    def change_password(self, user_id: int, password_data: UserChangePassword):
        user = self.get_user_by_id(user_id)

        if not user:
            raise NotFoundException(f"User with id {user_id} not found")

        if not user.change_password(password_data.old_password, password_data.new_password):
            raise UnauthorizedException("Invalid password")

    def deactivate_user(self, user_id: int):
        user = self.get_user_by_id(user_id)

        if not user:
            raise NotFoundException(f"User with id {user_id} not found")

        if not user.is_active:
            raise BadRequestException("User is already deactivated")

        user.is_active = False
        user.update_timestamp()
        self.db.flush()

    def activate_user(self, user_id: int):
        user = self.get_user_by_id(user_id)

        if not user:
            raise NotFoundException(f"User with id {user_id} not found")

        if user.is_active:
            raise BadRequestException("User is already active")

        user.is_active = True
        user.update_timestamp()
        self.db.flush()
