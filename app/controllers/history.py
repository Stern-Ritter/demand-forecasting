from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_session
from exceptions import NotFoundException
from models.enums import ForecastStatus, TransactionType, Currency
from models.finance import TransactionFilter
from models.forecast import ForecastJobFilter
from models.user import User
from security import get_current_user
from services.finance_service import FinanceService
from services.forecast_service import ForecastService

router = APIRouter()


def get_finance_service(db: Session = Depends(get_session)):
    return FinanceService(db)


def get_forecast_service(db: Session = Depends(get_session)):
    return ForecastService(db)


@router.get("/transactions/{user_id}", summary="Get transaction history")
async def get_transaction_history(
    user_id: int,
    current_user: User = Depends(get_current_user),
    transaction_type: Optional[TransactionType] = Query(None),
    currency: Optional[Currency] = Query(None),
    min_amount: Optional[float] = Query(None, ge=0),
    max_amount: Optional[float] = Query(None, ge=0),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    description: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    finance_service: FinanceService = Depends(get_finance_service),
) -> List[Dict]:
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        filters = TransactionFilter(
            type=transaction_type,
            currency=currency,
            min_amount=min_amount,
            max_amount=max_amount,
            start_date=start_date,
            end_date=end_date,
            description=description,
        )
        transactions = finance_service.get_user_transactions(user_id, filters, limit, offset)
        return [
            {
                "id": str(t.id),
                "type": t.type.value,
                "amount": t.amount,
                "currency": t.currency.value,
                "description": t.description,
                "created_at": t.created_at,
                "user_id": t.user_id,
            }
            for t in transactions
        ]
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e.detail))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get("/forecasts/{user_id}", summary="Get forecast job history")
async def get_forecast_history(
    user_id: int,
    current_user: User = Depends(get_current_user),
    job_status: Optional[ForecastStatus] = Query(None),
    min_cost: Optional[float] = Query(None, ge=0),
    max_cost: Optional[float] = Query(None, ge=0),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    forecast_service: ForecastService = Depends(get_forecast_service),
) -> List[Dict]:
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    try:
        filters = ForecastJobFilter(
            status=job_status,
            min_cost=min_cost,
            max_cost=max_cost,
            start_date=start_date,
            end_date=end_date,
        )
        jobs = forecast_service.get_user_jobs(user_id, filters, limit, offset)
        result = []
        for job in jobs:
            item: Dict = {
                "job_id": str(job.id),
                "status": job.status.value,
                "cost": job.cost,
                "horizon": job.horizon,
                "created_at": job.created_at,
            }
            if job.result:
                item["result"] = {
                    "n_series": job.result.n_series,
                }
            result.append(item)
        return result
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e.detail))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")
