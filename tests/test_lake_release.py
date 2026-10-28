"""Tests for pushing the lake to a release and pulling it back (a folder stands in for GitHub)."""

import hashlib
import shutil
import tarfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from ingestion.common.lake_release import BRONZE_ASSET, pack, pull, push, sha256_of, unpack
from ingestion.common.manifest import MANIFEST_PATH

OCT = "bronze/files/da/price_monitoring/year=2026/month=10"
SEP = "bronze/files/da/price_monitoring/year=2026/month=09"


class FolderRelease:
    """Assets kept as files in a folder; counts uploads."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        folder.mkdir()
        self.uploads: list[str] = []

    def assets(self) -> dict[str, str]:
        return {p.name: sha256_of(p) for p in self.folder.iterdir()}

    def download(self, name: str, dest: Path) -> Path:
        return Path(shutil.copy(self.folder / name, dest / name))

    def upload(self, path: Path) -> None:
        shutil.copy(path, self.folder / path.name)
        self.uploads.append(path.name)


def write_lake(root: Path, pdfs: dict[str, bytes], *, write_files: bool = True) -> None:
    """A lake with one bronze table, a manifest listing ``pdfs``, and (optionally) the PDFs."""
    for path, data in pdfs.items():
        if write_files:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(data)
    manifest = pa.table(
        {
            "lake_path": list(pdfs) + [None],  # a discovered, not downloaded report
            "sha256": [hashlib.sha256(d).hexdigest() for d in pdfs.values()] + [None],
        }
    )
    (root / MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(manifest, root / MANIFEST_PATH)
    table = root / "bronze/tables/da_prices/year=2026/month=10/part.parquet"
    table.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"price_raw": [str(len(pdfs))]}), table)


def tar_names(path: Path) -> list[str]:
    with tarfile.open(path) as tar:
        return tar.getnames()


@pytest.fixture
def release(tmp_path: Path) -> FolderRelease:
    return FolderRelease(tmp_path / "release")


def test_pack_is_deterministic(tmp_path: Path) -> None:
    write_lake(tmp_path / "lake", {f"{OCT}/a.pdf": b"a"})
    first = pack(tmp_path / "lake", [f"{OCT}/a.pdf", MANIFEST_PATH], tmp_path / "1.tar")
    (tmp_path / "lake" / OCT / "a.pdf").touch()  # new mtime, same content
    second = pack(tmp_path / "lake", [MANIFEST_PATH, f"{OCT}/a.pdf"], tmp_path / "2.tar")
    assert sha256_of(first) == sha256_of(second)


def test_push_then_pull_round_trip(tmp_path: Path, release: FolderRelease) -> None:
    lake = tmp_path / "lake"
    write_lake(lake, {f"{OCT}/a.pdf": b"a", f"{SEP}/b.pdf": b"b"})
    assert push(lake, release) == 3
    assert sorted(release.uploads) == [BRONZE_ASSET, "pdfs-2026-09.tar", "pdfs-2026-10.tar"]
    assert push(lake, release) == 0  # nothing changed, nothing re-uploaded

    fresh = tmp_path / "fresh"
    pull(fresh, release)
    assert (fresh / MANIFEST_PATH).is_file()
    assert not (fresh / "bronze/files").exists()  # PDFs only on request
    pull(fresh, release, pdfs=True)
    assert (fresh / OCT / "a.pdf").read_bytes() == b"a"
    assert (fresh / SEP / "b.pdf").read_bytes() == b"b"


def test_ci_push_completes_a_month_from_the_release(tmp_path: Path, release: FolderRelease) -> None:
    write_lake(tmp_path / "laptop", {f"{OCT}/a.pdf": b"a", f"{SEP}/b.pdf": b"b"})
    push(tmp_path / "laptop", release)

    ci = tmp_path / "ci"  # pulled bronze only, then downloaded one new October report
    pull(ci, release)
    write_lake(
        ci, {f"{OCT}/a.pdf": b"a", f"{SEP}/b.pdf": b"b", f"{OCT}/c.pdf": b"c"}, write_files=False
    )
    (ci / OCT / "c.pdf").parent.mkdir(parents=True)
    (ci / OCT / "c.pdf").write_bytes(b"c")
    release.uploads.clear()

    push(ci, release)
    assert sorted(release.uploads) == [BRONZE_ASSET, "pdfs-2026-10.tar"]  # September untouched
    assert tar_names(release.folder / "pdfs-2026-10.tar") == [f"{OCT}/a.pdf", f"{OCT}/c.pdf"]


def test_push_refuses_a_pdf_that_does_not_match_the_manifest(
    tmp_path: Path, release: FolderRelease
) -> None:
    lake = tmp_path / "lake"
    write_lake(lake, {f"{OCT}/a.pdf": b"a"})
    (lake / OCT / "a.pdf").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="sha256"):
        push(lake, release)
    assert release.uploads == []


def test_push_refuses_pdfs_missing_everywhere(tmp_path: Path, release: FolderRelease) -> None:
    lake = tmp_path / "lake"
    write_lake(lake, {f"{OCT}/a.pdf": b"a", f"{OCT}/b.pdf": b"b"})
    (lake / OCT / "b.pdf").unlink()
    with pytest.raises(FileNotFoundError, match="2026-10"):
        push(lake, release)


def test_pull_needs_a_pushed_lake(tmp_path: Path, release: FolderRelease) -> None:
    with pytest.raises(FileNotFoundError, match=BRONZE_ASSET):
        pull(tmp_path / "lake", release)


def test_unpack_rejects_members_outside_the_lake_folders(tmp_path: Path) -> None:
    (tmp_path / "evil.txt").write_text("x")
    with tarfile.open(tmp_path / "bad.tar", "w") as tar:
        tar.add(tmp_path / "evil.txt", arcname="../evil.txt")
    with pytest.raises(ValueError, match="Unexpected member"):
        unpack(tmp_path / "bad.tar", tmp_path / "lake", ("bronze/files",))
