from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict

from database import get_session
from services.user_service import UserService, RoleService
from models.user import User, UserUpdate, UserChangePassword
from exceptions import (
    NotFoundException,
    BadRequestException,
    UnauthorizedException,
    ConflictException
)
from security import get_current_user

router = APIRouter()


def get_user_service(db: Session = Depends(get_session)):
    role_service = RoleService(db)
    return UserService(db, role_service)


@router.get(
    "/{user_id}",
    summary="Get User Information",
    description="Retrieve detailed information about a specific user",
    response_description="User details including profile information",
    responses={
        200: {"description": "User information retrieved successfully"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"}
    }
)
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
) -> Dict:
    """
    Получение детальной информации о пользователе.

    Возвращает полную информацию о пользователе, включая контактные данные,
    статус активности, роль и метаданные.

    Args:
        user_id: Идентификатор пользователя

    Returns:
        Dict с детальной информацией о пользователе

    Raises:
        HTTPException 403: Если запрашивается другой пользователь
        HTTPException 404: Если пользователь с указанным ID не найден
        HTTPException 500: При внутренних ошибках сервера
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot view another user's profile"
        )
    try:
        user = user_service.get_user_by_id(user_id)
        return {
            "id": user.id,
            "login": user.login,
            "email": user.email,
            "display_name": user.display_name,
            "is_active": user.is_active,
            "role_id": user.role_id,
            "created_at": user.created_at,
            "updated_at": user.updated_at
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


@router.put(
    "/{user_id}",
    summary="Update User Information",
    description="Update user profile information",
    response_description="Confirmation of successful update",
    responses={
        200: {"description": "User updated successfully"},
        400: {"description": "Invalid input data"},
        404: {"description": "User not found"},
        409: {"description": "Login or email already in use"},
        500: {"description": "Internal server error"}
    }
)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Обновление информации профиля пользователя.

    Позволяет частично или полностью обновить информацию пользователя.
    Проверяет уникальность логина и email при их изменении.

    Args:
        user_id: Идентификатор пользователя для обновления
        update_data: Данные для обновления (частичное обновление поддерживается)

    Returns:
        Dict с сообщением об успешном обновлении

    Raises:
        HTTPException 400: Если данные для обновления некорректны
        HTTPException 404: Если пользователь не найден
        HTTPException 409: Если новый логин или email уже используется другим пользователем
        HTTPException 500: При внутренних ошибках сервера
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot update another user's profile"
        )
    try:
        user_service.update_user(user_id, update_data)
        return {
            "message": "User updated successfully"
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
    except ConflictException as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e.detail)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/{user_id}/change-password",
    summary="Change User Password",
    description="Change user's password with old password verification",
    response_description="Confirmation of successful password change",
    responses={
        200: {"description": "Password changed successfully"},
        400: {"description": "Invalid password data"},
        401: {"description": "Invalid current password"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"}
    }
)
async def change_password(
    user_id: int,
    password_data: UserChangePassword,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Смена пароля пользователя.

    Требует подтверждения текущего пароля перед установкой нового пароля.
    Новый пароль должен соответствовать политике безопасности системы.

    Args:
        user_id: Идентификатор пользователя
        password_data: Данные для смены пароля:
            - old_password: Текущий пароль для проверки
            - new_password: Новый пароль

    Returns:
        Dict с сообщением об успешной смене пароля

    Raises:
        HTTPException 400: Если данные пароля некорректны
        HTTPException 401: Если текущий пароль неверен
        HTTPException 404: Если пользователь не найден
        HTTPException 500: При внутренних ошибках сервера
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot change another user's password"
        )
    try:
        user_service.change_password(user_id, password_data)
        return {
            "message": "Password changed successfully"
        }
    except BadRequestException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e.detail)
        )
    except UnauthorizedException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
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
    "/{user_id}/deactivate",
    summary="Deactivate User Account",
    description="Deactivate a user account (soft delete)",
    response_description="Confirmation of successful deactivation",
    responses={
        200: {"description": "User deactivated successfully"},
        400: {"description": "User is already deactivated"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"}
    }
)
async def deactivate_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Деактивация учетной записи пользователя.

    Выполняет мягкое удаление (soft delete) пользователя, устанавливая
    флаг is_active в False. Пользователь больше не может входить в систему,
    но его данные сохраняются в базе.

    Args:
        user_id: Идентификатор пользователя для деактивации

    Returns:
        Dict с сообщением об успешной деактивации

    Raises:
        HTTPException 400: Если пользователь уже деактивирован
        HTTPException 404: Если пользователь не найден
        HTTPException 500: При внутренних ошибках сервера
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot deactivate another user"
        )
    try:
        user_service.deactivate_user(user_id)
        return {
            "message": "User deactivated successfully"
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
    "/{user_id}/activate",
    summary="Activate User Account",
    description="Reactivate a previously deactivated user account",
    response_description="Confirmation of successful activation",
    responses={
        200: {"description": "User activated successfully"},
        400: {"description": "User is already active"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"}
    }
)
async def activate_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Активация учетной записи пользователя.

    Восстанавливает доступ к системе для ранее деактивированного пользователя,
    устанавливая флаг is_active в True.

    Args:
        user_id: Идентификатор пользователя для активации

    Returns:
        Dict с сообщением об успешной активации

    Raises:
        HTTPException 400: Если пользователь уже активен
        HTTPException 404: Если пользователь не найден
        HTTPException 500: При внутренних ошибках сервера
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: cannot activate another user"
        )
    try:
        user_service.activate_user(user_id)
        return {
            "message": "User activated successfully"
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
