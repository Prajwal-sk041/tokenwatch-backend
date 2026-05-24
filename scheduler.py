from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


def run_alert_checks():
    print("[SCHEDULER] ⏰ Running alert checks...")
    try:
        from routers.alerts import check_alerts_for_all_users
        check_alerts_for_all_users()
        print("[SCHEDULER] ✅ Alert checks complete")
    except Exception as e:
        print(f"[SCHEDULER ERROR] ❌ {e}")


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(
        run_alert_checks,
        trigger          = IntervalTrigger(hours=1),
        id               = "alert_checker",
        name             = "TokenWatch Alert Checker",
        replace_existing = True,
        misfire_grace_time = 60,
    )
    scheduler.start()
    print("[SCHEDULER] 🚀 Started — checks every hour")
    return scheduler