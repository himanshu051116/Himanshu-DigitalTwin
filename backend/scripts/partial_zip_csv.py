"""Read selected CSV members from a remote ZIP using byte-range requests.

Only Zip members matching CGMacros-XXX.csv and bio.csv are fetched; photos,
images and microbiome data are deliberately excluded. No full-archive checksum
can be claimed with this mode, but each extracted member's ZIP CRC32 is checked.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import time
import zipfile
import zlib
from collections import OrderedDict
from pathlib import Path, PurePosixPath

import requests

PHYSIONET = "https://physionet.org/files/cgmacros/1.0.0/CGMacros_dateshifted365.zip"
S3_MIRROR = "https://physionet-open.s3.amazonaws.com/cgmacros/1.0.0/CGMacros_dateshifted365.zip"
PATTERN = re.compile(r"CGMacros-\d{3}\.csv", re.I)
CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class RangeNotSupported(RuntimeError):
    """The source cannot safely serve ZIP members using HTTP Range."""


class RemoteRangeFile(io.RawIOBase):
    def __init__(self, url: str, *, session=None, block_size=2*1024*1024, cache_blocks=4,
                 retries=3, timeout=(15, 90)):
        super().__init__()
        self.url = url
        self.session = session or requests.Session()
        self.block_size = block_size
        self.cache_blocks = cache_blocks
        self.retries = retries
        self.timeout = timeout
        self.blocks = OrderedDict()
        self.pos = 0
        headers = {"Range": "bytes=0-0", "Accept-Encoding": "identity",
                   "User-Agent": "HimanshuDigitalTwin-SelectiveCSV/1.0"}
        response = self.session.get(url, headers=headers, timeout=timeout)
        if response.status_code != 206:
            response.close()
            raise RangeNotSupported(f"Server returned {response.status_code}, not 206 Partial Content: {url}")
        cr = CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", ""))
        if cr is None or int(cr[1]) != 0 or int(cr[2]) != 0:
            response.close()
            raise RangeNotSupported("Invalid range response from archive source")
        self.size = int(cr[3])
        self.etag = response.headers.get("ETag")
        self.last_modified = response.headers.get("Last-Modified")
        if len(response.content) != 1:
            raise RangeNotSupported("Initial probe returned wrong number of bytes")
        response.close()

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            p = offset
        elif whence == io.SEEK_CUR:
            p = self.pos + offset
        elif whence == io.SEEK_END:
            p = self.size + offset
        else:
            raise ValueError("Unsupported seek mode")
        if p < 0:
            raise ValueError("Negative ZIP offset")
        self.pos = p
        return p

    def _block(self, block):
        if block in self.blocks:
            self.blocks.move_to_end(block)
            return self.blocks[block]
        start = block * self.block_size
        stop = min(self.size - 1, start + self.block_size - 1)
        if start >= self.size:
            return b""
        headers = {"Range": f"bytes={start}-{stop}", "Accept-Encoding": "identity",
                   "User-Agent": "HimanshuDigitalTwin-SelectiveCSV/1.0"}
        if self.etag:
            headers["If-Range"] = self.etag
        elif self.last_modified:
            headers["If-Range"] = self.last_modified
        error = None
        for attempt in range(self.retries):
            try:
                response = self.session.get(self.url, headers=headers, timeout=self.timeout)
                if response.status_code != 206:
                    status = response.status_code
                    response.close()
                    raise RangeNotSupported(f"Range request returned HTTP {status} instead of 206")
                cr = CONTENT_RANGE.fullmatch(response.headers.get("Content-Range", ""))
                if not cr or (int(cr[1]), int(cr[2]), int(cr[3])) != (start, stop, self.size):
                    response.close()
                    raise RangeNotSupported("Remote ZIP changed or Content-Range is invalid")
                data = response.content
                response.close()
                if len(data) != stop - start + 1:
                    raise OSError(f"Short byte-range response: {len(data)} bytes")
                self.blocks[block] = data
                self.blocks.move_to_end(block)
                while len(self.blocks) > self.cache_blocks:
                    self.blocks.popitem(last=False)
                return data
            except RangeNotSupported:
                raise
            except (requests.RequestException, OSError) as ex:
                error = ex
                if attempt + 1 < self.retries:
                    time.sleep((attempt + 1) * 0.5)
        raise OSError(f"Could not read block {block} of {self.url}: {error}")

    def read(self, size=-1):
        if size is None or size < 0:
            size = max(0, self.size - self.pos)
        size = min(size, max(0, self.size - self.pos))
        chunks = []
        while size:
            block = self.pos // self.block_size
            off = self.pos % self.block_size
            data = self._block(block)
            piece = data[off:off + size]
            if not piece:
                raise OSError("Premature EOF from remote archive")
            chunks.append(piece)
            self.pos += len(piece)
            size -= len(piece)
        return b"".join(chunks)


def wanted(name: str) -> bool:
    basename = PurePosixPath(name).name
    return bool(PATTERN.fullmatch(basename) or basename.lower() == "bio.csv")


def crc32_file(path: Path) -> int:
    acc = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            acc = zlib.crc32(chunk, acc)
    return acc & 0xffffffff


def extract_csv_only(url: str, destination: Path, *, expected_subjects=45, session=None):
    """Extract 45 official subject CSVs and bio.csv without fetching photos."""
    destination = Path(destination)
    with RemoteRangeFile(url, session=session) as rr:
        with zipfile.ZipFile(rr) as zf:
            members = [z for z in zf.infolist() if not z.is_dir() and wanted(z.filename)]
            subjects = [m for m in members if PATTERN.fullmatch(PurePosixPath(m.filename).name)]
            bios = [m for m in members if PurePosixPath(m.filename).name.lower() == "bio.csv"]
            subject_ids = {PurePosixPath(z.filename).name.lower() for z in subjects}
            if len(subjects) != expected_subjects or len(subject_ids) != expected_subjects or len(bios) != 1:
                raise ValueError(f"Official CSV cohort incomplete: {len(subjects)} subject files, {len(bios)} bio.csv")
            if sum(m.file_size for m in members) > 700*1024*1024:
                raise ValueError("Selected CSV files exceed safe extracted-size limit")
            # Confirm all members safe and unique before any write.
            paths = []
            for info in members:
                norm = info.filename.replace("\\", "/")
                pure = PurePosixPath(norm)
                if pure.is_absolute() or ".." in pure.parts or info.file_size > 80*1024*1024:
                    raise ValueError(f"Unsafe ZIP member: {info.filename}")
                paths.append(destination.joinpath(*pure.parts))
            if len(set(paths)) != len(paths):
                raise ValueError("ZIP contains duplicate extraction paths")
            downloaded = 0
            fingerprints=[]
            for info, target in zip(members, paths):
                cached=(target.exists() and target.stat().st_size == info.file_size
                        and crc32_file(target) == info.CRC)
                if not cached:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    part = target.with_suffix(target.suffix + ".part")
                    with zf.open(info) as src, part.open("wb") as dst:
                        shutil.copyfileobj(src, dst, 1024*1024)
                    if part.stat().st_size != info.file_size or crc32_file(part) != info.CRC:
                        part.unlink(missing_ok=True)
                        raise IOError(f"CRC/size validation failed for {info.filename}")
                    part.replace(target)
                    downloaded += 1
                digest=hashlib.sha256()
                with target.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):
                        digest.update(chunk)
                fingerprints.append({'relative_path':target.relative_to(destination).as_posix(),
                                     'bytes':info.file_size,'zip_crc32':f'{info.CRC:08x}',
                                     'sha256':digest.hexdigest()})
            manifest = {
                "method": "HTTP ZIP byte ranges; original compressed archive not downloaded",
                "source_url": url,
                "archive_size_bytes": rr.size,
                "subject_csvs": len(subjects),
                "phenotype_csvs": len(bios),
                "selected_files": len(members),
                "extracted_files_this_run": downloaded,
                "per_member_integrity": "ZIP CRC32 verified and SHA-256 recorded per CSV",
                "file_sha256": fingerprints,
                "full_archive_sha256_verified": False,
                "excluded": "food photographs, microbiome CSVs, notebooks and other non-model data",
                "note": "CSV contains reported meals/macronutrients and sensors; image file paths are not downloadable in this mode",
            }
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "csv_only_manifest.json").write_text(json.dumps(manifest, indent=2))
            return manifest


def main():
    ap = argparse.ArgumentParser(description="Fast CGMacros CSV-only remote ZIP fetch")
    ap.add_argument("--url", default=PHYSIONET)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    print(json.dumps(extract_csv_only(args.url, args.out), indent=2))


if __name__ == "__main__":
    main()
