from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Dict

from database import get_session
from services.finance_service import FinanceService
from models.finance import DepositRequest, WithdrawRequest
from models.user import User
from exceptions import (
    NotFoundException,
    BadRequestException,
    InsufficientFundsException
)
from security import get_current_user

router = APIRouter()


def get_finance_service(db: Session = Depends(get_session)):
    return FinanceService(db)


@router.get(
    "/{user_id}",
    summary="Get User Balance",
    description="Retrieve current balance information for a specific user",
    response_description="Current balance details including value and currency",
    responses={
        200: {"description": "Balance information retrieved successfully"},
        404: {"description": "User or balance not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_balance(
    user_id: int,
    finance_service: FinanceService = Depends(get_finance_service),
    current_user: User = Depends(get_current_user)
) -> Dict:
    """
    Получение текущего баланса пользователя.

    Возвращает информацию о текущем состоянии баланса пользователя,
    включая доступную сумму, валюту и время последнего обновления.

    Args:
        user_id: Идентификатор пользователя

    Returns:
        Dict с информацией о балансе:
            - user_id: ID пользователя
            - value: Текущая сумма на балансе
            - currency: Валюта баланса
            - updated_at: Время последнего обновления баланса

    Raises:
        HTTPException 403: Если запрашивается баланс другого пользователя
        HTTPException 404: Если пользователь или его баланс не найден
        HTTPException 500: При внутренних ошибках сервера
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot view another user's balance"
        )
    try:
        balance = finance_service.get_balance(user_id)
        return {
            "user_id": balance.user_id,
            "balance": balance.value,
            "currency": balance.currency.value,
            "updated_at": balance.updated_at
        }
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e.detail)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/deposit",
    summary="Deposit Funds",
    description="Deposit funds to user's balance",
    response_description="Confirmation of successful deposit with transaction details",
    responses={
        200: {"description": "Deposit completed successfully"},
        400: {"description": "Invalid deposit amount (must be positive)"},
        404: {"description": "User or balance not found"},
        500: {"description": "Internal server error"}
    }
)
async def deposit(
    deposit_data: DepositRequest,
    finance_service: FinanceService = Depends(get_finance_service),
    current_user: User = Depends(get_current_user)
) -> Dict:
    """
    Пополнение баланса пользователя.

    Зачисляет указанную сумму на баланс пользователя и создает запись
    о транзакции типа DEPOSIT.

    Args:
        deposit_data: Данные для пополнения:
            - user_id: Идентификатор пользователя
            - amount: Сумма для зачисления (должна быть положительной)
            - currency: Валюта операции
            - description: Описание операции (опционально)

    Returns:
        Dict с результатом операции:
            - message: Сообщение об успехе
            - transaction_id: ID созданной транзакции
            - new_balance: Новый баланс после операции
            - currency: Валюта баланса

    Raises:
        HTTPException 400: Если сумма для пополнения не положительная
        HTTPException 403: Если пополнение для другого пользователя
        HTTPException 404: Если пользователь или его баланс не найден
        HTTPException 500: При внутренних ошибках сервера
    """
    if deposit_data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot deposit for another user"
        )
    try:
        transaction = finance_service.deposit(deposit_data)
        balance = finance_service.get_balance(deposit_data.user_id)

        return {
            "message": "Deposit successful",
            "transaction_id": str(transaction.id),
            "new_balance": balance.value if balance else 0,
            "currency": balance.currency.value if balance else "RUB"
        }
    except BadRequestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.detail)
        )
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e.detail)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/withdraw",
    summary="Withdraw Funds",
    description="Withdraw funds from user's balance",
    response_description="Confirmation of successful withdrawal with transaction details",
    responses={
        200: {"description": "Withdrawal completed successfully"},
        400: {"description": "Invalid withdrawal amount or insufficient funds"},
        404: {"description": "User or balance not found"},
        500: {"description": "Internal server error"}
    }
)
async def withdraw(
    withdraw_data: WithdrawRequest,
    finance_service: FinanceService = Depends(get_finance_service),
    current_user: User = Depends(get_current_user)
) -> Dict:
    """
    Снятие средств с баланса пользователя.

    Списание указанной суммы с баланса пользователя при условии достаточного
    количества средств и создание записи о транзакции типа WITHDRAWAL.

    Args:
        withdraw_data: Данные для снятия:
            - user_id: Идентификатор пользователя
            - amount: Сумма для списания (должна быть положительной)
            - currency: Валюта операции
            - description: Описание операции (опционально)

    Returns:
        Dict с результатом операции:
            - message: Сообщение об успехе
            - transaction_id: ID созданной транзакции
            - new_balance: Новый баланс после операции
            - currency: Валюта баланса

    Raises:
        HTTPException 400: Если сумма для снятия не положительная
        HTTPException 400: Если недостаточно средств на балансе
        HTTPException 403: Если снятие для другого пользователя
        HTTPException 404: Если пользователь или его баланс не найден
        HTTPException 500: При внутренних ошибках сервера
    """
    if withdraw_data.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot withdraw for another user"
        )
    try:
        transaction = finance_service.withdraw(withdraw_data)
        balance = finance_service.get_balance(withdraw_data.user_id)

        return {
            "message": "Withdrawal successful",
            "transaction_id": str(transaction.id),
            "new_balance": balance.value if balance else 0,
            "currency": balance.currency.value if balance else "RUB"
        }
    except BadRequestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.detail)
        )
    except InsufficientFundsException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.detail)
        )
    except NotFoundException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e.detail)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
