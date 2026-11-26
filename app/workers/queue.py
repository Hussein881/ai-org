"""Procrastinate app. Jobs are disposable: our tasks table is the only record of work."""

from typing import Protocol

from procrastinate import App, Blueprint, PsycopgConnector


class Runtime(Protocol):
    async def execute(self, task_id: str) -> None: ...

    async def sweep(self) -> None: ...


_runtime: Runtime | None = None
blueprint = Blueprint()


def bind(runtime: Runtime) -> None:
    global _runtime
    _runtime = runtime


def runtime() -> Runtime:
    if _runtime is None:
        raise RuntimeError("no worker runtime bound: jobs only run inside app.workers.host")
    return _runtime


@blueprint.task(name="run_task", queue="agent")
async def run_task(task_id: str) -> None:
    await runtime().execute(task_id)


@blueprint.periodic(cron="* * * * *")
@blueprint.task(name="sweep", queue="system", queueing_lock="sweep")
async def sweep(timestamp: int) -> None:
    await runtime().sweep()


def conninfo(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def make_app(database_url: str) -> App:
    app = App(connector=PsycopgConnector(conninfo=conninfo(database_url), min_size=1, max_size=8))
    app.add_tasks_from(blueprint, namespace="aiorg")
    return app
