"""Keep the lake in a GitHub Release, so a fresh machine or a CI run can restore it.

The pipeline always works on a local lake. ``push`` packs it into release assets and
``pull`` unpacks them:

- ``bronze.tar``: bronze tables and the manifest (all a daily run needs, ~30 MB).
- ``pdfs-YYYY-MM.tar``: the original DA PDFs of one report month.

Tars are deterministic (sorted, fixed metadata), so an unchanged month has the same
sha256 as the asset GitHub already holds and is not uploaded again. A month whose PDFs
are only partly on this machine (a CI run that downloaded today's report) is completed
from its asset first. Every PDF is checked against its manifest hash before upload, so
a push can never replace an archive with a smaller or corrupted one.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Protocol

import pyarrow.parquet as pq

from ingestion.common.manifest import MANIFEST_PATH

logger = logging.getLogger(__name__)

TAG = "lake"  # one release holds every asset; never marked "latest" (that is the open data)
BRONZE_ASSET = "bronze.tar"
BRONZE_DIRS = ("bronze/tables", "bronze/manifest")
_MONTH = re.compile(r"/year=(\d{4})/month=(\d{2})/")


class Release(Protocol):
    """The release operations push and pull need (GitHub via ``gh``; a folder in tests)."""

    def assets(self) -> dict[str, str]:
        """Asset name -> sha256 hex digest; empty if the release does not exist."""
        ...

    def download(self, name: str, dest: Path) -> Path: ...

    def upload(self, path: Path) -> None: ...


class GhRelease:
    """The ``lake`` release of the current repo, through the GitHub CLI.

    The repo comes from the git remote, or from ``GH_REPO`` where there is no checkout.
    shortcut: needs the ``gh`` binary (preinstalled on GitHub runners, not in the image);
    switch to the REST API if the container must push itself.
    """

    def __init__(self, tag: str = TAG) -> None:
        if shutil.which("gh") is None:
            raise RuntimeError("The GitHub CLI 'gh' is not installed or not on PATH")
        self.tag = tag

    def _gh(self, *args: str) -> str:
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout

    def assets(self) -> dict[str, str]:
        try:
            out = self._gh("api", f"repos/{{owner}}/{{repo}}/releases/tags/{self.tag}")
        except subprocess.CalledProcessError as exc:
            if "404" in exc.stderr:
                return {}
            raise
        return {
            a["name"]: (a.get("digest") or "").removeprefix("sha256:")
            for a in json.loads(out)["assets"]
        }

    def download(self, name: str, dest: Path) -> Path:
        self._gh("release", "download", self.tag, "--pattern", name, "--dir", str(dest))
        return dest / name

    def upload(self, path: Path) -> None:
        if not self.assets():
            self._gh(
                "release", "create", self.tag, "--latest=false",
                "--title", "Lake state (pipeline input, not the open data)",
                "--notes", "Bronze tables, manifest and original DA PDFs, restored by "
                "`tawad lake-pull`. For the cleaned data, use the latest release.",
            )  # fmt: skip
        # --clobber deletes the old asset before uploading; a failed upload is fixed by
        # pushing again, since the local lake still holds everything.
        self._gh("release", "upload", self.tag, str(path), "--clobber")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pack(root: Path, paths: list[str], out: Path) -> Path:
    """Tar lake-relative paths with fixed metadata, so equal content gives equal bytes."""
    with tarfile.open(out, "w", format=tarfile.GNU_FORMAT) as tar:
        for path in sorted(paths):
            info = tar.gettarinfo(root / path, arcname=path)
            info.mtime, info.mode, info.uid, info.gid, info.uname, info.gname = (
                0,
                0o644,
                0,
                0,
                "",
                "",
            )
            with (root / path).open("rb") as f:
                tar.addfile(info, f)
    return out


def unpack(
    tar_path: Path, root: Path, prefixes: tuple[str, ...], only: set[str] | None = None
) -> None:
    """Extract a lake tar, refusing members outside the expected lake folders."""
    with tarfile.open(tar_path) as tar:
        members = tar.getmembers()
        for m in members:
            if not m.isfile() or not m.name.startswith(tuple(p + "/" for p in prefixes)):
                raise ValueError(f"Unexpected member {m.name!r} in {tar_path.name}")
        if only is not None:
            members = [m for m in members if m.name in only]
        tar.extractall(root, members=members, filter="data")


def _files_under(root: Path, dirs: tuple[str, ...]) -> list[str]:
    return [
        p.relative_to(root).as_posix() for d in dirs if (root / d).is_dir()
        for p in (root / d).rglob("*") if p.is_file()
    ]  # fmt: skip


def pdf_months(root: Path) -> dict[str, dict[str, str]]:
    """Report month (YYYY-MM) -> {lake path: sha256} for every PDF the manifest holds."""
    rows = pq.read_table(root / MANIFEST_PATH, columns=["lake_path", "sha256"]).to_pylist()
    months: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        if row["lake_path"] and row["sha256"]:
            m = _MONTH.search(row["lake_path"])
            if m is None:
                raise ValueError(f"Manifest path has no year=/month= folder: {row['lake_path']!r}")
            months[f"{m[1]}-{m[2]}"][row["lake_path"]] = row["sha256"]
    return dict(months)


def push(root: Path, release: Release) -> int:
    """Upload every asset whose content changed; return how many were uploaded."""
    remote = release.assets()
    uploaded = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        def send(name: str, paths: list[str]) -> None:
            nonlocal uploaded
            tar = pack(root, paths, tmp_dir / name)
            if remote.get(name) == sha256_of(tar):
                logger.debug("%s unchanged", name)
            else:
                logger.info(
                    "Uploading %s (%d files, %.1f MB)", name, len(paths), tar.stat().st_size / 1e6
                )
                release.upload(tar)
                uploaded += 1
            tar.unlink()

        for month, files in sorted(pdf_months(root).items()):
            name = f"pdfs-{month}.tar"
            missing = {p for p in files if not (root / p).is_file()}
            if len(missing) == len(files):
                continue  # nothing of this month here, so nothing changed
            if missing:
                if name not in remote:
                    raise FileNotFoundError(
                        f"{len(missing)} PDFs of {month} are neither here nor in the release"
                    )
                unpack(release.download(name, tmp_dir), root, ("bronze/files",), only=missing)
            for path, sha in files.items():
                if sha256_of(root / path) != sha:
                    raise ValueError(
                        f"{path} does not match its manifest sha256; not pushing {month}"
                    )
            send(name, list(files))
        send(BRONZE_ASSET, _files_under(root, BRONZE_DIRS))  # last: it lists the PDFs above
    logger.info("Lake pushed: %d assets uploaded", uploaded)
    return uploaded


def pull(root: Path, release: Release, *, pdfs: bool = False) -> None:
    """Restore bronze tables and manifest (and, with ``pdfs``, every PDF) into the lake."""
    remote = release.assets()
    if BRONZE_ASSET not in remote:
        raise FileNotFoundError(f"The release has no {BRONZE_ASSET}; push a lake first")
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        unpack(release.download(BRONZE_ASSET, Path(tmp)), root, BRONZE_DIRS)
        for name in sorted(remote) if pdfs else []:
            if name.startswith("pdfs-"):
                unpack(release.download(name, Path(tmp)), root, ("bronze/files",))
                (Path(tmp) / name).unlink()
    logger.info("Lake pulled into %s%s", root, " with PDFs" if pdfs else "")
