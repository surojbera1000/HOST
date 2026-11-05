"""Docker deployment engine.

Each hosted bot runs in its own isolated container on the host Docker daemon
(reached through the mounted /var/run/docker.sock). The container clones the
repo, installs dependencies, injects the user's env vars, and runs the bot's
start command — all capped with memory/CPU limits and a restart policy.

Blocking Docker SDK calls are run in a worker thread so the async bot loop is
never blocked. (For large scale this can move to a Celery worker later.)
"""
import asyncio
import shlex
from dataclasses import dataclass

import docker
from docker.errors import APIError, DockerException, ImageNotFound, NotFound

from app.core.logging import get_logger
from app.core.security import decrypt

log = get_logger("deployer")

# Full python image (not slim) so `git` is available for cloning.
BASE_IMAGE = "python:3.11"
CONTAINER_PREFIX = "botnest_"

# Resource caps per bot (isolation + fair usage on a single VPS).
MEM_LIMIT = "512m"
NANO_CPUS = 500_000_000          # 0.5 CPU
PIDS_LIMIT = 256
STARTUP_GRACE_SECONDS = 6        # how long we watch before reporting status


@dataclass
class DeployResult:
    success: bool
    status: str                  # "running" | "failed" | "error"
    container_id: str | None = None
    logs: str = ""
    error: str | None = None


def container_name(bot_id: str) -> str:
    return f"{CONTAINER_PREFIX}{bot_id}"


def _build_script(repo_url: str, branch: str, startup_cmd: str) -> str:
    """Shell script the container runs: clone -> install -> start.

    For private repos a token is read from the _BN_TOKEN env var (injected only
    into this container). The token is used to build an auth clone URL, then:
      - the .git directory is deleted (removes the stored credential), and
      - _BN_TOKEN is unset before the bot starts,
    so the untrusted bot code never sees the token in its environment, command
    line, or git config.
    """
    repo = shlex.quote(repo_url)
    br = shlex.quote(branch or "main")
    start = startup_cmd or "python main.py"
    return (
        "set -e\n"
        f"REPO={repo}\n"
        f"BR={br}\n"
        'if [ -n "$_BN_TOKEN" ]; then\n'
        '  CLONE="https://x-access-token:${_BN_TOKEN}@${REPO#https://}"\n'
        "else\n"
        '  CLONE="$REPO"\n'
        "fi\n"
        "echo '==> Cloning repository...'\n"
        'git clone --depth 1 --branch "$BR" "$CLONE" /app || git clone --depth 1 "$CLONE" /app\n'
        "cd /app\n"
        "rm -rf .git\n"              # drop stored credentials + git metadata
        "unset _BN_TOKEN\n"           # token must not reach the bot process
        "if [ -f requirements.txt ]; then\n"
        "  echo '==> Installing requirements.txt...'\n"
        "  pip install --no-cache-dir -r requirements.txt\n"
        "elif [ -f pyproject.toml ] || [ -f setup.py ]; then\n"
        "  echo '==> Installing project...'\n"
        "  pip install --no-cache-dir .\n"
        "fi\n"
        "echo '==> Starting bot...'\n"
        f"exec {start}\n"
    )


def _deploy_sync(
    bot_id: str,
    repo_url: str,
    branch: str,
    startup_cmd: str,
    env: dict[str, str],
    token: str | None = None,
) -> DeployResult:
    try:
        client = docker.from_env()
    except DockerException as exc:
        return DeployResult(False, "error", error=f"Docker is not available: {exc}")

    # Inject the GitHub token only for the clone step; the script unsets it
    # before the bot runs so the untrusted code never sees it.
    run_env = dict(env)
    if token:
        run_env["_BN_TOKEN"] = token

    name = container_name(bot_id)

    # Remove any previous container for this bot.
    try:
        old = client.containers.get(name)
        old.remove(force=True)
    except NotFound:
        pass
    except APIError as exc:
        log.warning("remove_old_failed", bot=bot_id, error=str(exc))

    # Make sure the base image is present.
    try:
        client.images.get(BASE_IMAGE)
    except ImageNotFound:
        log.info("pulling_base_image", image=BASE_IMAGE)
        try:
            client.images.pull(BASE_IMAGE)
        except APIError as exc:
            return DeployResult(False, "error", error=f"Could not pull base image: {exc}")

    script = _build_script(repo_url, branch, startup_cmd)

    try:
        container = client.containers.run(
            BASE_IMAGE,
            command=["sh", "-c", script],
            name=name,
            detach=True,
            environment=run_env,
            mem_limit=MEM_LIMIT,
            nano_cpus=NANO_CPUS,
            pids_limit=PIDS_LIMIT,
            network_mode="bridge",
            restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
            labels={"botnest.bot_id": bot_id},
        )
    except (APIError, DockerException) as exc:
        return DeployResult(False, "error", error=f"Failed to start container: {exc}")

    # Watch briefly to catch immediate crashes (bad config, missing deps).
    import time
    time.sleep(STARTUP_GRACE_SECONDS)
    try:
        container.reload()
    except (APIError, NotFound):
        pass

    status = container.status
    try:
        logs = container.logs(tail=40).decode("utf-8", errors="replace")
    except APIError:
        logs = ""

    if status == "exited":
        exit_code = container.attrs.get("State", {}).get("ExitCode", 1)
        return DeployResult(
            False, "failed", container_id=container.id, logs=logs,
            error=f"The bot stopped right after starting (exit code {exit_code}).",
        )

    return DeployResult(True, "running", container_id=container.id, logs=logs)


async def deploy_bot(
    bot_id: str,
    repo_url: str,
    branch: str,
    startup_cmd: str,
    env_encrypted: dict[str, str],
    token: str | None = None,
) -> DeployResult:
    """Decrypt env vars and run the (blocking) deployment in a worker thread.

    ``token`` is the repo owner's GitHub token (for private repos). It's used
    only for cloning and is scrubbed before the bot process starts.
    """
    from app.config import get_settings

    env = {k: decrypt(v) for k, v in env_encrypted.items()}
    if token is None:
        token = get_settings().github_token or None
    log.info("deploy_start", bot=bot_id, repo=repo_url, env_count=len(env), private=bool(token))
    result = await asyncio.to_thread(
        _deploy_sync, bot_id, repo_url, branch, startup_cmd, env, token
    )
    log.info("deploy_done", bot=bot_id, status=result.status)
    return result


# --- Lifecycle helpers (used here and by the Phase 5 dashboard) ------------
def _simple_action(bot_id: str, action: str) -> bool:
    try:
        client = docker.from_env()
        container = client.containers.get(container_name(bot_id))
    except (DockerException, NotFound):
        return False
    try:
        getattr(container, action)()
        return True
    except APIError as exc:
        log.warning("action_failed", bot=bot_id, action=action, error=str(exc))
        return False


async def stop_bot(bot_id: str) -> bool:
    return await asyncio.to_thread(_simple_action, bot_id, "stop")


async def start_bot(bot_id: str) -> bool:
    return await asyncio.to_thread(_simple_action, bot_id, "start")


async def restart_bot(bot_id: str) -> bool:
    return await asyncio.to_thread(_simple_action, bot_id, "restart")


def _remove_sync(bot_id: str) -> bool:
    try:
        client = docker.from_env()
        container = client.containers.get(container_name(bot_id))
        container.remove(force=True)
        return True
    except (DockerException, NotFound):
        return False


async def remove_bot(bot_id: str) -> bool:
    return await asyncio.to_thread(_remove_sync, bot_id)


def _logs_sync(bot_id: str, tail: int = 40) -> str | None:
    try:
        client = docker.from_env()
        container = client.containers.get(container_name(bot_id))
        return container.logs(tail=tail).decode("utf-8", errors="replace")
    except (DockerException, NotFound):
        return None


async def get_logs(bot_id: str, tail: int = 40) -> str | None:
    return await asyncio.to_thread(_logs_sync, bot_id, tail)
