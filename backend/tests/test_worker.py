from app.workers.arq_worker import expire_credit_lots, ping, poll_due_monitors, WorkerSettings


def test_worker_registers_ping():
    assert ping in WorkerSettings.functions
    assert expire_credit_lots in WorkerSettings.functions
    assert poll_due_monitors in WorkerSettings.functions
    assert WorkerSettings.redis_settings is not None
    cron_fns = [job.coroutine for job in WorkerSettings.cron_jobs]
    assert poll_due_monitors in cron_fns
