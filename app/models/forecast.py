from pydantic import BaseModel
from sqlalchemy import Column, Integer, Float, String, ForeignKey, Enum as SQLAlchemyEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column

from typing import Optional, TYPE_CHECKING
from datetime import datetime

from .base import BaseEntity
from .enums import ForecastStatus

if TYPE_CHECKING:
    from .user import User


class ForecastJob(BaseEntity):
    __tablename__ = "forecast_jobs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status = Column(SQLAlchemyEnum(ForecastStatus), default=ForecastStatus.PENDING, nullable=False)
    cost = Column(Float, default=0.0)
    input_file_path = Column(String(512), nullable=False)
    horizon = Column(Integer, default=28, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="forecast_jobs")
    result: Mapped[Optional["ForecastResult"]] = relationship(
        "ForecastResult",
        uselist=False,
        back_populates="job",
        cascade="all, delete-orphan"
    )

    def start_processing(self, cost: float):
        self.status = ForecastStatus.PROCESSING
        self.cost = cost
        self.update_timestamp()


class ForecastResult(BaseEntity):
    __tablename__ = "forecast_results"

    job_id: Mapped[int] = mapped_column(ForeignKey("forecast_jobs.id"), unique=True, nullable=False)
    result_file_path = Column(String(512), nullable=False)
    n_series = Column(Integer, nullable=True)

    job: Mapped["ForecastJob"] = relationship("ForecastJob", back_populates="result")


class ForecastJobCreate(BaseModel):
    horizon: int = 28


class ForecastJobFilter(BaseModel):
    status: Optional[ForecastStatus] = None
    min_cost: Optional[float] = None
    max_cost: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
