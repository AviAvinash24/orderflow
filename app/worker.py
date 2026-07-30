"""
RQ outbox worker.

- A light scheduler thread enqueues drain jobs on an interval
  (only if the queue is empty — avoids backlog spam).
- An RQ Worker consumes the queue and runs process_outbox_batch.

Run: python -m app.worker
"""
import logging
import threading
import time

from redis import Redis
from rq import Queue, Worker

from app.core.config import OUTBOX_POLL_SECONDS, REDIS_URL
from app.jobs.outbox import process_outbox_batch

logger = logging.getLogger(__name__)

QUEUE_NAME = "outbox"


def enqueue_loop() -> None:
    redis = Redis.from_url(REDIS_URL)
    queue = Queue(QUEUE_NAME, connection=redis)
    logger.info(
        "Outbox enqueue loop started (interval=%ss, redis=%s)",
        OUTBOX_POLL_SECONDS,
        REDIS_URL,
    )
    while True:
        try:
            if queue.count == 0:
                queue.enqueue(process_outbox_batch, job_timeout=60)
        except Exception:
            logger.exception("Failed to enqueue outbox drain job")
        time.sleep(OUTBOX_POLL_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    threading.Thread(target=enqueue_loop, daemon=True).start()

    redis = Redis.from_url(REDIS_URL)
    logger.info("RQ worker listening on queue=%s", QUEUE_NAME)
    Worker([QUEUE_NAME], connection=redis).work(with_scheduler=False)


if __name__ == "__main__":
    main()