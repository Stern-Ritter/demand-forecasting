import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import pika
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from config import get_settings
from exceptions import (
    BadRequestException,
    InsufficientFundsException,
    InternalServerErrorException,
    NotFoundException,
)
from models.enums import Currency, ForecastStatus, TransactionType
from models.finance import Transaction
from models.forecast import ForecastJob, ForecastJobFilter, ForecastResult
from models.user import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ForecastService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._mq_params = pika.ConnectionParameters(
            host=self.settings.RABBITMQ_HOST,
            port=self.settings.RABBITMQ_PORT,
            virtual_host="/",
            credentials=pika.PlainCredentials(
                username=self.settings.RABBITMQ_USER,
                password=self.settings.RABBITMQ_PASSWORD,
            ),
            heartbeat=30,
            blocked_connection_timeout=2,
        )

    # ------------------------------------------------------------------ CRUD

    def create_job(self, user_id: int, input_file_path: str, horizon: int = 28) -> ForecastJob:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFoundException(f"User {user_id} not found")
        if not user.is_active:
            raise BadRequestException(f"User {user_id} is deactivated")
        if not user.balance:
            raise BadRequestException(f"User {user_id} has no balance")

        job = ForecastJob(
            user_id=user_id,
            input_file_path=input_file_path,
            horizon=horizon,
            status=ForecastStatus.PENDING,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def get_job_by_id(self, job_id: int) -> ForecastJob:
        job = self.db.get(ForecastJob, job_id)
        if not job:
            raise NotFoundException(f"Forecast job {job_id} not found")
        return job

    def get_job_with_result(self, job_id: int) -> ForecastJob:
        stmt = (
            select(ForecastJob)
            .options(joinedload(ForecastJob.user), joinedload(ForecastJob.result))
            .where(ForecastJob.id == job_id)
        )
        job = self.db.scalar(stmt)
        if not job:
            raise NotFoundException(f"Forecast job {job_id} not found")
        return job

    def get_user_jobs(
        self,
        user_id: int,
        filters: Optional[ForecastJobFilter] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ForecastJob]:
        user = self.db.get(User, user_id)
        if not user:
            raise NotFoundException(f"User {user_id} not found")

        stmt = (
            select(ForecastJob)
            .where(ForecastJob.user_id == user_id)
            .options(joinedload(ForecastJob.result))
        )

        if filters:
            if filters.status:
                stmt = stmt.where(ForecastJob.status == filters.status)
            if filters.min_cost is not None:
                stmt = stmt.where(ForecastJob.cost >= filters.min_cost)
            if filters.max_cost is not None:
                stmt = stmt.where(ForecastJob.cost <= filters.max_cost)
            if filters.start_date:
                stmt = stmt.where(ForecastJob.created_at >= filters.start_date)
            if filters.end_date:
                stmt = stmt.where(ForecastJob.created_at <= filters.end_date)

        stmt = stmt.order_by(ForecastJob.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    # ----------------------------------------------------------------- process

    def process_job(self, job_id: int, cost: float) -> int:
        job = self.get_job_with_result(job_id)

        if job.status != ForecastStatus.PENDING:
            raise BadRequestException(
                f"Cannot process job in '{job.status.value}' status. Only 'pending' jobs can be processed."
            )
        if cost <= 0:
            raise BadRequestException("Cost must be positive")

        job.start_processing(cost)
        self.db.flush()

        try:
            if job.user.balance.value < cost:
                job.status = ForecastStatus.FAILED
                self.db.flush()
                raise InsufficientFundsException(
                    f"Insufficient funds. Required: {cost}, Available: {job.user.balance.value}"
                )

            job.user.balance.withdraw(cost)
            transaction = Transaction(
                type=TransactionType.WITHDRAWAL,
                amount=cost,
                currency=Currency.RUB,
                description="Forecast job processing",
                user_id=job.user_id,
            )
            self.db.add(transaction)
            self._publish_job(job)
            self.db.flush()
            return job.id

        except InsufficientFundsException:
            raise
        except Exception as e:
            job.status = ForecastStatus.FAILED
            if job.cost and job.cost > 0:
                job.user.balance.deposit(job.cost)
            self.db.flush()
            raise InternalServerErrorException(f"Failed to enqueue job: {e}")

    # --------------------------------------------------------------- private

    def _publish_job(self, job: ForecastJob):
        message = {
            "job_id": str(job.id),
            "input_file_path": job.input_file_path,
            "horizon": job.horizon,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        }
        try:
            conn = pika.BlockingConnection(self._mq_params)
            ch = conn.channel()
            ch.queue_declare(queue=self.settings.QUEUE_NAME, durable=True)
            ch.basic_publish(
                exchange="",
                routing_key=self.settings.QUEUE_NAME,
                body=json.dumps(message),
                properties=pika.BasicProperties(delivery_mode=2),
            )
            conn.close()
            logger.info(f"Job {job.id} published to queue '{self.settings.QUEUE_NAME}'")
        except Exception as e:
            logger.error(f"Failed to publish job {job.id}: {e}")
            raise
