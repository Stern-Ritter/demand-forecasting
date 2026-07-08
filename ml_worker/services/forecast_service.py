import logging

from sqlalchemy.orm import Session

from exceptions import NotFoundException
from app.models.enums import ForecastStatus
from app.models.forecast import ForecastJob, ForecastResult
from services.ml_service import load_and_validate, run_forecast

logger = logging.getLogger(__name__)


class WorkerForecastService:
    def __init__(self, db: Session, result_dir: str, model_dir: str):
        self.db = db
        self.result_dir = result_dir
        self.model_dir = model_dir

    def _get_job(self, job_id: int) -> ForecastJob:
        job = self.db.get(ForecastJob, job_id)
        if not job:
            raise NotFoundException(f"Forecast job {job_id} not found")
        return job

    def process_job(self, job_id: int) -> ForecastResult:
        job = self._get_job(job_id)

        df = load_and_validate(job.input_file_path)

        output = run_forecast(
            df=df,
            horizon=job.horizon,
            model_dir=self.model_dir,
            result_dir=self.result_dir,
        )

        result = ForecastResult(
            job_id=job.id,
            result_file_path=output["result_file_path"],
            n_series=output["n_series"],
        )
        self.db.add(result)
        job.status = ForecastStatus.COMPLETED
        self.db.flush()

        logger.info(f"Job {job_id} completed: {output['n_series']} series")
        return result
