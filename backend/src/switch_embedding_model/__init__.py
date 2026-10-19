"""uv run switch-embedding-model MODEL: use another embedding model.

Vectors of two models cannot be compared, so every document is embedded
again. The command stops the backend and the worker (they would keep using
the old model), rebuilds the search index for MODEL
(maintenance/switch_embedding.py), writes EMBEDDING_MODEL to backend/.env and,
in production, starts them again. The worker then embeds the documents in the
background; a banner shows the progress to every user.

Production (the docker-compose.prod.yml stack is running): the model is
downloaded first by the `models` job, the only step that needs the internet,
and the index is rebuilt inside the backend image. Development: the
backend's and the worker's processes run from this folder; they are stopped
here, and started again by whoever started them.

Run it with the current model to rebuild the index, e.g. after changing the
chunk size. If it stops midway, run it again.
"""

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from rich.console import Console
from rich.table import Table

from settings import EMBEDDING_MODELS
from setup.env import ENV_PATH, env_value, upsert_env

BACKEND_DIR = ENV_PATH.parent
REPO_DIR = BACKEND_DIR.parent
PROD_COMPOSE = REPO_DIR / "docker-compose.prod.yml"
_STOP_WAIT_SECONDS = 30


def compose(*args: str, capture: bool = False) -> str:
    """docker compose on the production stack, as deploy/deploy.sh runs it,
    with the values of .env as the file has them now."""
    # Compose prefers the environment to --env-file, and this process loaded
    # .env at start: an EMBEDDING_MODEL written since would be ignored and the
    # containers started with the old model.
    from_file = dotenv_values(ENV_PATH)
    env = {name: value for name, value in os.environ.items() if name not in from_file}
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(ENV_PATH), "-f", str(PROD_COMPOSE), *args],
        cwd=REPO_DIR,
        check=True,
        text=True,
        env=env,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout or ""


def production_running() -> bool:
    """By the stack's database, not the backend: a backend whose model does
    not match the index restarts in a loop, and switching is the way out."""
    try:
        return bool(compose("ps", "--status", "running", "-q", "postgres", capture=True).strip())
    except OSError, subprocess.CalledProcessError:
        return False  # no Docker, or no production stack here


def switch_production(console: Console, model: str) -> None:
    console.print(f"Downloading {model} (needs the internet)...")
    compose("--profile", "setup", "run", "--rm", "-e", f"EMBEDDING_MODEL={model}", "models")
    console.print("Stopping the backend and the worker...")
    compose("stop", "backend", "worker")
    try:
        compose(
            "run", "--rm", "--no-deps", "-e", f"EMBEDDING_MODEL={model}",
            "backend", "python", "-m", "maintenance.switch_embedding", model,
        )  # fmt: skip
        upsert_env(ENV_PATH, "EMBEDDING_MODEL", model)
    finally:
        # With the old model if the rebuild failed: the index still matches it.
        console.print("Starting the backend and the worker...")
        compose("up", "-d", "backend", "worker")


def development_processes() -> list[int]:
    """This checkout's backend (uvicorn main:app) and worker (celery -A
    worker) processes, with their `uv run` parents."""
    found: list[int] = []
    for entry in Path("/proc").glob("[0-9]*"):
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
            cwd = (entry / "cwd").resolve()
        except OSError:
            continue  # gone, or another user's
        names = [Path(arg.decode(errors="replace")).name for arg in argv]
        ours = cwd == BACKEND_DIR or BACKEND_DIR in cwd.parents
        backend = "uvicorn" in names and any(name.endswith("main:app") for name in names)
        worker = "celery" in names and "worker" in names
        if ours and (backend or worker) and int(entry.name) != os.getpid():
            found.append(int(entry.name))
    return found


def stop_development(console: Console) -> None:
    pids = development_processes()
    if not pids:
        console.print("No backend or worker is running.")
        return
    console.print(f"Stopping the backend and the worker (processes {', '.join(map(str, pids))})...")
    for pid in pids:
        _signal(pid, signal.SIGTERM)
    deadline = time.monotonic() + _STOP_WAIT_SECONDS
    while time.monotonic() < deadline and any(_alive(pid) for pid in pids):
        time.sleep(0.5)
    for pid in pids:
        # A task cut short is queued again (acks_late).
        _signal(pid, signal.SIGKILL)


def switch_development(console: Console, model: str) -> None:
    from database import engine
    from maintenance.switch_embedding import load_model, switch

    # Before anything stops: a model that cannot load changes nothing.
    load_model(model, console.print)
    stop_development(console)

    async def rebuild() -> None:
        try:
            await switch(model, console.print)
        finally:
            await engine.dispose()

    asyncio.run(rebuild())
    upsert_env(ENV_PATH, "EMBEDDING_MODEL", model)
    console.print(f"Wrote EMBEDDING_MODEL={model} to {ENV_PATH}.")
    console.print("[yellow]Start the backend and the worker again: the worker then embeds the documents.[/]")


def _signal(pid: int, sig: signal.Signals) -> None:
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def _alive(pid: int) -> bool:
    """Running; an exited process its parent has not reaped yet (zombie) is not."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    # The state follows the parenthesised command name, which may hold spaces.
    return stat.rsplit(")", 1)[1].split()[0] != "Z"


def show_models(console: Console) -> None:
    """Usage, the known models with where to read about them, and where to
    look when none fits."""
    current = os.getenv("EMBEDDING_MODEL") or env_value(ENV_PATH, "EMBEDDING_MODEL")
    table = Table(title="Embedding models", title_justify="left")
    table.add_column("MODEL", no_wrap=True)
    table.add_column("Vector size", justify="right")
    # Links wrap rather than end in "…", and stay one clickable link when
    # they wrap: a cut link cannot be opened.
    table.add_column("Details (model card: languages, size, benchmarks)", overflow="fold")
    for name, spec in EMBEDDING_MODELS.items():
        label = f"{name} (current)" if name == current else name
        url = f"https://huggingface.co/{spec.hf_id}"
        table.add_row(label, str(spec.dims), f"[link={url}]{url}[/link]")
    console.print("Usage: uv run switch-embedding-model MODEL\n")
    if current:
        console.print(f"Current model: [bold]{current}[/]\n")
    console.print(table)
    console.print(
        "\nWhich languages each model suits, where it is downloaded to and how long a switch "
        'takes: documentations/deployment.md, section "Changing the embedding model".\n\n'
        "None of them fits? Compare other embedding models on the MTEB leaderboard "
        "(https://huggingface.co/spaces/mteb/leaderboard; filter by your documents' language) or "
        "browse https://huggingface.co/models?library=sentence-transformers. To use one, add it "
        "to EMBEDDING_MODELS in backend/src/settings.py (Hugging Face id, vector size, query and "
        "passage prefixes from its model card), then calibrate its min_score with "
        'evals/search_relevance.py (backend/README.md, "Evaluating search and sources").',
        soft_wrap=False,
    )


def main() -> None:
    from exceptions import AppError

    console = Console()
    if len(sys.argv) != 2:
        show_models(console)
        raise SystemExit(2)
    model = sys.argv[1]
    if model not in EMBEDDING_MODELS:
        console.print(f"[red]Unknown embedding model {model!r}.[/]\n")
        show_models(console)
        raise SystemExit(2)
    load_dotenv(ENV_PATH)
    try:
        if production_running():
            switch_production(console, model)
        else:
            switch_development(console, model)
    except AppError as exc:
        raise SystemExit(f"Stopped: {exc.message}") from None
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Stopped: {' '.join(exc.cmd[:6])}... failed (exit {exc.returncode}).") from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    console.print(
        f"[green]Switched to {model}.[/] Documents are embedded again in the background; "
        "the Documents page shows the progress, and search finds each one once it is done."
    )
