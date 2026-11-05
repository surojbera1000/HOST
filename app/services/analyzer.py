"""Repository analysis — inspects a public GitHub repo and builds a report.

Detects: language/framework, entry-point, dependencies, required env variables,
startup command, and common deployment problems.
"""
import re
from dataclasses import dataclass, field

from app.services.github import GitHubClient, GitHubError, parse_repo_url

# Candidate entry-point files, in priority order.
ENTRYPOINT_CANDIDATES = [
    "main.py", "bot.py", "__main__.py", "app.py", "run.py", "start.py",
]

# Files that commonly declare required environment variables.
ENV_EXAMPLE_FILES = [
    ".env.example", ".env.sample", "sample.env", "example.env", ".env.dist", "config.env.sample",
]

# Extra source files worth scanning for env-var usage.
CONFIG_FILE_CANDIDATES = [
    "config.py", "vars.py", "settings.py", "config/config.py", "app/config.py",
]

# Known Telegram frameworks -> friendly label.
FRAMEWORKS = {
    "pyrogram": "Pyrogram",
    "aiogram": "Aiogram",
    "telethon": "Telethon",
    "python-telegram-bot": "python-telegram-bot",
    "telebot": "pyTelegramBotAPI",
    "pytelegrambotapi": "pyTelegramBotAPI",
}

# Patterns that reveal os.environ / getenv usage in Python source.
_ENV_PATTERNS = [
    re.compile(r'os\.environ\.get\(\s*["\']([A-Z][A-Z0-9_]*)["\']'),
    re.compile(r'os\.getenv\(\s*["\']([A-Z][A-Z0-9_]*)["\']'),
    re.compile(r'os\.environ\[\s*["\']([A-Z][A-Z0-9_]*)["\']\s*\]'),
    re.compile(r'(?<!os\.)\bgetenv\(\s*["\']([A-Z][A-Z0-9_]*)["\']'),
    re.compile(r'environ\.get\(\s*["\']([A-Z][A-Z0-9_]*)["\']'),
    re.compile(r'config\(\s*["\']([A-Z][A-Z0-9_]*)["\']'),  # python-decouple
]

_ENV_LINE_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")


@dataclass
class AnalysisResult:
    owner: str
    repo: str
    branch: str
    language: str | None = None
    framework: str | None = None
    entrypoint: str | None = None
    startup_cmd: str | None = None
    dependencies: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def repo_full(self) -> str:
        return f"{self.owner}/{self.repo}"

    def to_report(self) -> str:
        """Build the HTML deployment report shown in Telegram."""
        lines = [
            "✅ <b>All checked — here's what I found!</b>\n",
            f"📦 <b>Project:</b> <code>{self.repo_full}</code>",
            f"🌿 <b>Branch:</b> <code>{self.branch}</code>",
            f"🔤 <b>Language:</b> {self.language or 'Unknown'}",
            f"🧩 <b>Framework:</b> {self.framework or 'Not detected'}",
            f"📄 <b>Main file:</b> <code>{self.entrypoint or 'Not found'}</code>",
            f"▶️ <b>Start command:</b> <code>{self.startup_cmd or 'Not detected'}</code>",
        ]

        dep_count = len(self.dependencies)
        lines.append(f"\n📦 <b>Dependencies ({dep_count}):</b>")
        if self.dependencies:
            preview = ", ".join(self.dependencies[:12])
            if dep_count > 12:
                preview += f", … (+{dep_count - 12} more)"
            lines.append(f"<code>{preview}</code>")
        else:
            lines.append("<i>None found</i>")

        lines.append(f"\n🔑 <b>Settings it needs ({len(self.env_vars)}):</b>")
        if self.env_vars:
            for v in self.env_vars:
                lines.append(f"  • <code>{v}</code>")
            lines.append("<i>Don't worry — I'll walk you through each one.</i>")
        else:
            lines.append("<i>None — nothing extra to set up.</i>")

        if self.issues:
            lines.append("\n⚠️ <b>Heads up:</b>")
            for issue in self.issues:
                lines.append(f"  • {issue}")
        else:
            lines.append("\n✅ <b>Looks good — ready to set up!</b>")

        return "\n".join(lines)


def _parse_requirements(text: str) -> list[str]:
    deps = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "-")):
            continue
        name = re.split(r"[=<>!~ \[;]", line, maxsplit=1)[0].strip()
        if name:
            deps.append(name)
    return deps


def _detect_framework(deps: list[str], sources: list[str]) -> str | None:
    lowered = {d.lower() for d in deps}
    for key, label in FRAMEWORKS.items():
        if key in lowered:
            return label
    # Fallback: scan import statements in source files.
    blob = "\n".join(sources).lower()
    for key, label in FRAMEWORKS.items():
        mod = key.replace("-", "_")
        if re.search(rf"\b(import|from)\s+{re.escape(mod)}\b", blob):
            return label
    return None


def _extract_env_vars(sources: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in sources:
        for pattern in _ENV_PATTERNS:
            for name in pattern.findall(text):
                if name not in seen and len(name) >= 2:
                    seen.add(name)
                    found.append(name)
    return found


def _extract_env_from_example(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        m = _ENV_LINE_RE.match(line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            found.append(m.group(1))
    return found


async def analyze_repo(url: str, token: str | None = None) -> AnalysisResult:
    parsed = parse_repo_url(url)
    if not parsed:
        raise GitHubError("That doesn't look like a valid GitHub URL.")
    owner, repo = parsed

    if token is None:
        from app.config import get_settings
        token = get_settings().github_token or None

    gh = GitHubClient(token=token)
    meta = await gh.get_repo(owner, repo)
    branch = meta.get("default_branch", "main")

    result = AnalysisResult(
        owner=owner, repo=repo, branch=branch,
        language=meta.get("language"),
    )

    tree = await gh.get_tree(owner, repo, branch)
    tree_set = set(tree)
    basenames = {p.split("/")[-1]: p for p in tree}

    # --- Dependencies ---
    scanned_sources: list[str] = []
    if "requirements.txt" in tree_set:
        req = await gh.get_file(owner, repo, branch, "requirements.txt")
        if req:
            result.dependencies = _parse_requirements(req)
    elif "pyproject.toml" in tree_set:
        pyproj = await gh.get_file(owner, repo, branch, "pyproject.toml")
        if pyproj:
            result.dependencies = re.findall(r'"([A-Za-z0-9_.-]+)\s*[=<>~]', pyproj)
            scanned_sources.append(pyproj)
    else:
        result.issues.append("No <code>requirements.txt</code> or <code>pyproject.toml</code> found.")

    # --- Entry point ---
    for cand in ENTRYPOINT_CANDIDATES:
        if cand in tree_set:
            result.entrypoint = cand
            break
    if result.entrypoint is None:
        for cand in ENTRYPOINT_CANDIDATES:
            if cand in basenames:
                result.entrypoint = basenames[cand]
                break

    # --- Startup command (Procfile wins) ---
    if "Procfile" in tree_set:
        proc = await gh.get_file(owner, repo, branch, "Procfile")
        if proc:
            m = re.search(r"^\s*\w+:\s*(.+)$", proc, re.MULTILINE)
            if m:
                result.startup_cmd = m.group(1).strip()
    if not result.startup_cmd and result.entrypoint:
        result.startup_cmd = f"python {result.entrypoint}"

    # --- Collect source files to scan for env vars ---
    to_scan: list[str] = []
    if result.entrypoint:
        to_scan.append(result.entrypoint)
    for cand in CONFIG_FILE_CANDIDATES:
        if cand in tree_set:
            to_scan.append(cand)
    for name, path in basenames.items():
        if name in {"config.py", "vars.py", "settings.py"} and path not in to_scan:
            to_scan.append(path)
    # Limit to keep it fast.
    for path in to_scan[:6]:
        content = await gh.get_file(owner, repo, branch, path)
        if content:
            scanned_sources.append(content)

    result.framework = _detect_framework(result.dependencies, scanned_sources)

    # --- Env variables: prefer an example file, then source scan ---
    env_from_example: list[str] = []
    for ef in ENV_EXAMPLE_FILES:
        if ef in tree_set:
            content = await gh.get_file(owner, repo, branch, ef)
            if content:
                env_from_example = _extract_env_from_example(content)
                break

    env_from_source = _extract_env_vars(scanned_sources)
    merged: list[str] = []
    seen: set[str] = set()
    for v in env_from_example + env_from_source:
        if v not in seen:
            seen.add(v)
            merged.append(v)
    result.env_vars = merged

    # --- Issues ---
    if result.entrypoint is None:
        result.issues.append("Could not detect a main entry-point file.")
    if not result.env_vars:
        result.issues.append("No environment variables detected (may need manual setup).")
    if result.language and result.language.lower() != "python":
        result.issues.append(
            f"Primary language is <b>{result.language}</b>; only Python is supported right now."
        )

    return result
