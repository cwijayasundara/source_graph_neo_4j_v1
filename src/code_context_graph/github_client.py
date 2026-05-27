from __future__ import annotations

import re
import shutil
from pathlib import Path

from git import Repo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOS_DIR = PROJECT_ROOT / "source_code_to_analyse"

GITHUB_URL_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


def parse_github_url(url: str) -> tuple[str, str]:
    match = GITHUB_URL_RE.match(url.strip())
    if not match:
        raise ValueError(f"Not a valid GitHub URL: {url}")
    return match.group("owner"), match.group("repo")


def clone_repo(
    url: str,
    dest: Path | None = None,
    branch: str | None = None,
    shallow: bool = True,
) -> Path:
    owner, name = parse_github_url(url)
    if dest is None:
        dest = REPOS_DIR / owner / name

    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    kwargs: dict = {}
    if shallow:
        kwargs["depth"] = 1
    if branch:
        kwargs["branch"] = branch

    Repo.clone_from(url, str(dest), **kwargs)
    return dest


def repo_slug(url: str) -> str:
    owner, name = parse_github_url(url)
    return f"{owner}/{name}"


def list_cloned_repos() -> list[dict[str, str]]:
    if not REPOS_DIR.exists():
        return []
    repos = []
    for owner_dir in sorted(REPOS_DIR.iterdir()):
        if not owner_dir.is_dir():
            continue
        for repo_dir in sorted(owner_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            repos.append({
                "slug": f"{owner_dir.name}/{repo_dir.name}",
                "path": str(repo_dir),
            })
    return repos


def delete_cloned_repo(slug: str) -> bool:
    path = REPOS_DIR / slug
    if path.exists():
        shutil.rmtree(path)
        return True
    return False
