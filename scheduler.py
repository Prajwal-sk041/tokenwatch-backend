import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

def run_alert_checks():
    logger.info("running alert checks")
    try:
        from routers.alerts import check_alerts_for_all_users
        check_alerts_for_all_users()
        logger.info("alert checks complete")
    except Exception:
        logger.exception("alert checks failed")

def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(run_alert_checks, trigger=IntervalTrigger(hours=1), id="alert_checker",
                      name="TokenWatch Alert Checker", replace_existing=True, misfire_grace_time=60)
    scheduler.start()
    logger.info("scheduler started")
    return scheduler
