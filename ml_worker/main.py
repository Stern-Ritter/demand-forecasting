import logging
import time

import pika
from sqlalchemy.orm import configure_mappers

# Import the full shared ORM model graph so SQLAlchemy can resolve relationship
# targets (e.g. ForecastJob.user -> "User") when the worker queries jobs.
# Importing app.models.user cascades to finance and forecast models.
import app.models.user  # noqa: F401

from config import get_settings
from services.ml_service import load_model_bundle
from worker import Worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    settings = get_settings()

    # Fail fast: ensure every mapper (and its relationship targets) is resolvable.
    configure_mappers()

    # Fail fast and warm the model cache before consuming jobs.
    load_model_bundle(settings.MODEL_DIR)

    connection_parameters = pika.ConnectionParameters(
        host=settings.RABBITMQ_HOST,
        port=settings.RABBITMQ_PORT,
        virtual_host="/",
        credentials=pika.PlainCredentials(
            username=settings.RABBITMQ_USER,
            password=settings.RABBITMQ_PASSWORD,
        ),
        heartbeat=600,
        blocked_connection_timeout=300,
    )

    worker = Worker(result_dir=settings.RESULT_DIR, model_dir=settings.MODEL_DIR)

    while True:
        try:
            connection = pika.BlockingConnection(connection_parameters)
            channel = connection.channel()
            channel.queue_declare(queue=settings.QUEUE_NAME, durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(
                queue=settings.QUEUE_NAME,
                on_message_callback=worker.callback,
                auto_ack=False,
            )
            logger.info(f"Worker started, listening on queue '{settings.QUEUE_NAME}'")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"RabbitMQ connection error: {e}. Retrying in 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            break
        finally:
            try:
                connection.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
