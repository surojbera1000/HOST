"""Minimal GitHub client for public repositories (no auth token).

Only two calls hit the GitHub REST API (repo metadata + file tree), which keeps
us well under the 60 requests/hour unauthenticated limit. Individual file
contents are fetched from raw.githubusercontent.com, which does not count
against the API rate limit.
"""
import re

import httpx

GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"

_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
)


class GitHubError(Exception):
    """Raised for any user-facing GitHub problem (bad URL, 404, rate limit)."""


def parse_repo_url(url: str) -> tuple[str, str] | None:
    """Extract (owner, repo) from many GitHub URL forms, or ``owner/repo``."""
    url = url.strip()
    m = _URL_RE.search(url)
    if m:
        owner, repo = m.group("owner"), m.group("repo")
    elif re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", url):
        owner, repo = url.split("/", 1)
    else:
        return None
    repo = repo.removesuffix(".git")
    return owner, repo


class GitHubClient:
    def __init__(self, token: str | None = None, timeout: float = 20.0) -> None:
        self._headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-bot-hosting-platform",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._timeout = timeout

    async def get_repo(self, owner: str, repo: str) -> dict:
        url = f"{GITHUB_API}/repos/{owner}/{repo}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url, headers=self._headers)
        if r.status_code == 404:
            raise GitHubError("Repository not found. Check the URL and that it is public.")
        if r.status_code == 403 and "rate limit" in r.text.lower():
            raise GitHubError("GitHub rate limit reached. Please try again in a while.")
        if r.status_code != 200:
            raise GitHubError(f"GitHub returned an error (HTTP {r.status_code}).")
        return r.json()

    async def get_tree(self, owner: str, repo: str, branch: str) -> list[str]:
        """Return a flat list of all file paths in the repo (recursive)."""
        url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url, headers=self._headers)
        if r.status_code != 200:
            raise GitHubError("Could not read the repository file tree.")
        data = r.json()
        return [item["path"] for item in data.get("tree", []) if item.get("type") == "blob"]

    async def get_file(self, owner: str, repo: str, branch: str, path: str) -> str | None:
        """Fetch a single file's text from raw.githubusercontent.com."""
        url = f"{RAW_BASE}/{owner}/{repo}/{branch}/{path}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(url)
        except httpx.HTTPError:
            return None
        if r.status_code == 200:
            return r.text
        return None
