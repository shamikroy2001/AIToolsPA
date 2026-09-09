from app.workers.arq_worker import expire_credit_lots, ping, WorkerSettings


def test_worker_registers_ping():
    assert ping in WorkerSettings.functions
    assert expire_credit_lots in WorkerSettings.functions
    assert WorkerSettings.redis_settings is not None
