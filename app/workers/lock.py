"""One executor at a time: a Postgres session advisory lock held on a dedicated connection."""

from sqlalchemy import Connection, Engine, text

LOCK_KEY = 4_811_047


class ExecutorLock:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.conn: Connection | None = None

    def acquire(self) -> bool:
        conn = self.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        if conn.execute(text("select pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar():
            self.conn = conn
            return True
        conn.close()
        return False

    def alive(self) -> bool:
        if self.conn is None:
            return False
        try:
            self.conn.execute(text("select 1"))
        except Exception:  # any failure means we can no longer prove we hold the lock
            return False
        return True

    def release(self) -> None:
        if self.conn is not None:
            self.conn.invalidate()  # really close it: a pooled connection would keep the lock
            self.conn.close()
            self.conn = None
