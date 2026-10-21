"""Verify byte-range ZIP extraction without downloading large image members."""
import io
import re
import zipfile

import pytest

from scripts.partial_zip_csv import extract_csv_only, RangeNotSupported, RemoteRangeFile


class FakeResponse:
    def __init__(self, code, payload, hdr):
        self.status_code = code
        self.content = payload
        self.headers = hdr

    def close(self):
        pass


class FakeRangeSession:
    def __init__(self, payload, support=True):
        self.payload = payload
        self.support = support
        self.transferred = 0

    def get(self, url, headers, timeout):
        if not self.support:
            return FakeResponse(200, b'ignore', {'Content-Length': str(len(self.payload))})
        m = re.fullmatch(r'bytes=(\d+)-(\d+)', headers['Range'])
        assert m
        start, stop = map(int, m.groups())
        piece = self.payload[start:stop+1]
        self.transferred += len(piece)
        return FakeResponse(206, piece, {'Content-Range': f'bytes {start}-{stop}/{len(self.payload)}', 'ETag': '"stable-blob"'})


def fixture_zip():
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, 'w', compression=zipfile.ZIP_STORED) as archive:
        # Intentionally large, incompressible photos ensure extraction never touches the image ranges.
        # Use deterministic bytes that are distinct across slices.
        archive.writestr('CGMacros_dateshifted365/CGMacros/CGMacros-001/photos/big.jpg',
                         bytes(range(256)) * (10*1024*1024//256))
        archive.writestr('CGMacros_dateshifted365/CGMacros/bio.csv', 'Subject,A1c PDL (Lab)\n001,7.1\n')
        for i in range(1, 46):
            archive.writestr(f'CGMacros_dateshifted365/CGMacros/CGMacros-{i:03d}/CGMacros-{i:03d}.csv',
                             f'Timestamp,Dexcom GL,HR,Mets,Carbs\n2024-01-01 00:00:00,{i+90},74,10,0\n')
    return mem.getvalue()


def test_extract_45_csvs_and_bio_without_photo_transfer(tmp_path):
    payload = fixture_zip()
    fake = FakeRangeSession(payload)
    output = tmp_path / 'data'
    result = extract_csv_only('https://example.test/archive.zip', output, session=fake)
    assert result['subject_csvs'] == 45
    assert result['phenotype_csvs'] == 1
    assert result['full_archive_sha256_verified'] is False
    assert len(list(output.rglob('CGMacros-*.csv'))) == 45
    assert len(list(output.rglob('bio.csv'))) == 1
    assert not list(output.rglob('*.jpg'))
    # The 10 MB leading photo is skipped; some archive blocks still overlap it.
    assert fake.transferred < len(payload) / 2
    # Repeat call is idempotent and requires no re-extraction.
    again = extract_csv_only('https://example.test/archive.zip', output, session=FakeRangeSession(payload))
    assert again['extracted_files_this_run'] == 0


def test_reject_non_range_server():
    with pytest.raises(RangeNotSupported):
        RemoteRangeFile('https://example.test/archive.zip', session=FakeRangeSession(b'abcd', support=False))


def test_reject_incomplete_subject_cohort(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:
        z.writestr('bio.csv', 'Subject\n1')
        z.writestr('CGMacros-001.csv', 'Timestamp\n2020')
    with pytest.raises(ValueError, match='incomplete'):
        extract_csv_only('https://example.test/archive.zip', tmp_path, session=FakeRangeSession(buffer.getvalue()))
