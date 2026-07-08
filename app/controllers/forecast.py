import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import get_settings
from database import get_session
from exceptions import (
    BadRequestException,
    InsufficientFundsException,
    InternalServerErrorException,
    NotFoundException,
)
from models.enums import ForecastStatus
from models.forecast import ForecastJobFilter
from models.user import User
from security import get_current_user
from services.forecast_service import ForecastService

router = APIRouter()

DEFAULT_COST = 10.0
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def get_forecast_service(db: Session = Depends(get_session)) -> ForecastService:
    return ForecastService(db)


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload sales CSV and create forecast job",
    responses={
        201: {"description": "Job created successfully"},
        400: {"description": "Invalid file"},
        401: {"description": "Not authenticated"},
    },
)
async def upload_and_create_job(
    file: UploadFile = File(..., description="CSV with columns: id, date, sales (+ optional sell_price, snap, event_name_1, event_type_1, event_type_2)"),
    horizon: int = Query(default=28, ge=1, le=365, description="Forecast horizon in days"),
    current_user: User = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
) -> Dict:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .csv files are accepted")

    settings = get_settings()
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(upload_dir, unique_name)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large (max 100 MB)")
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        job = forecast_service.create_job(
            user_id=current_user.id,
            input_file_path=file_path,
            horizon=horizon,
        )
        return {
            "message": "Forecast job created successfully",
            "job_id": str(job.id),
            "status": job.status.value,
            "horizon": job.horizon,
        }
    except (NotFoundException, BadRequestException) as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=e.status_code, detail=str(e.detail))
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.post(
    "/job/{job_id}/process",
    summary="Start processing a forecast job",
    responses={
        200: {"description": "Job accepted for processing"},
        400: {"description": "Invalid status or insufficient funds"},
        403: {"description": "Access denied"},
        404: {"description": "Job not found"},
    },
)
async def process_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
) -> Dict:
    try:
        job = forecast_service.get_job_with_result(job_id)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e.detail))

    if job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        forecast_service.process_job(job_id, DEFAULT_COST)
        return {
            "message": "Job accepted for processing",
            "job_id": str(job_id),
            "status": "processing",
        }
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e.detail))
    except InsufficientFundsException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e.detail))
    except InternalServerErrorException as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e.detail))
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error")


@router.get(
    "/job/{job_id}",
    summary="Get forecast job status and result metadata",
    responses={
        200: {"description": "Job information"},
        403: {"description": "Access denied"},
        404: {"description": "Job not found"},
    },
)
async def get_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
) -> Dict:
    try:
        job = forecast_service.get_job_with_result(job_id)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e.detail))

    if job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    response: Dict = {
        "job_id": str(job.id),
        "status": job.status.value,
        "cost": job.cost,
        "horizon": job.horizon,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
    if job.result:
        response["result"] = {
            "n_series": job.result.n_series,
        }
    return response


@router.get(
    "/job/{job_id}/download",
    summary="Download forecast result CSV",
    responses={
        200: {"description": "CSV file with forecasts", "content": {"text/csv": {}}},
        400: {"description": "Job not completed yet"},
        403: {"description": "Access denied"},
        404: {"description": "Job or result not found"},
    },
)
async def download_result(
    job_id: int,
    current_user: User = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    try:
        job = forecast_service.get_job_with_result(job_id)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e.detail))

    if job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if job.status != ForecastStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is not completed yet (status: {job.status.value})",
        )

    if not job.result or not os.path.exists(job.result.result_file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result file not found")

    return FileResponse(
        path=job.result.result_file_path,
        media_type="text/csv",
        filename=f"forecast_job_{job_id}.csv",
    )


@router.get(
    "/jobs",
    summary="List current user's forecast jobs",
    responses={
        200: {"description": "List of forecast jobs"},
        401: {"description": "Not authenticated"},
    },
)
async def list_jobs(
    current_user: User = Depends(get_current_user),
    job_status: Optional[ForecastStatus] = Query(None, description="Filter by status"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    forecast_service: ForecastService = Depends(get_forecast_service),
) -> List[Dict]:
    filters = ForecastJobFilter(
        status=job_status,
        start_date=start_date,
        end_date=end_date,
    )
    try:
        jobs = forecast_service.get_user_jobs(current_user.id, filters, limit, offset)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e.detail))

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
