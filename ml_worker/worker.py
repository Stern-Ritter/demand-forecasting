import json
import logging

from exceptions import NotFoundException
from app.models.enums import ForecastStatus
from app.models.forecast import ForecastJob
from database import SessionLocal
from services.forecast_service import WorkerForecastService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, result_dir: str, model_dir: str):
        self.result_dir = result_dir
        self.model_dir = model_dir

    def callback(self, ch, method, properties, body):
        session = SessionLocal()
        job_id_int = None
        try:
            message = json.loads(body)
            raw_job_id = message.get("job_id")
            if not raw_job_id:
                logger.error(f"Invalid message - missing job_id: {message}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            job_id_int = int(raw_job_id)
            logger.info(f"Processing forecast job {job_id_int}")

            forecast_service = WorkerForecastService(session, self.result_dir, self.model_dir)
            result = forecast_service.process_job(job_id_int)

            session.commit()
            logger.info(f"Job {job_id_int} done: {result.n_series} series")
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except NotFoundException as e:
            logger.error(f"Job not found: {e.detail}")
            session.rollback()
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.exception(f"Error processing job {job_id_int}: {e}")
            try:
                if job_id_int:
                    job = session.get(ForecastJob, job_id_int)
                    if job:
                        job.status = ForecastStatus.FAILED
                        session.commit()
            except Exception:
                pass
            session.rollback()
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        finally:
            session.close()
