"""Resume behavior and end-to-end archive integrity for real-data acquisition."""
import hashlib
from pathlib import Path
import pytest
from scripts import download_real_data as dl


class Response:
    def __init__(self, code, payload, headers=None):
        self.status_code=code; self.payload=payload; self.headers=headers or {}
    def __enter__(self): return self
    def __exit__(self,*exc): return False
    def raise_for_status(self):
        if self.status_code>=400: raise RuntimeError(f'HTTP {self.status_code}')
    def iter_content(self,chunk_size):
        yield self.payload


def test_partial_file_is_resumed_without_discarding_bytes(monkeypatch,tmp_path:Path):
    calls=[]
    def request(*args,**kwargs):
        calls.append(kwargs['headers'].copy())
        if len(calls)==1:return Response(200,b'abcde')
        assert kwargs['headers']['Range']=='bytes=5-'
        return Response(206,b'fghij',{'Content-Range':'bytes 5-9/10'})
    monkeypatch.setattr(dl.requests,'get',request)
    monkeypatch.setattr(dl.time,'sleep',lambda *a:None)
    out=tmp_path/'real_data.zip'
    assert dl.download('https://example.test/download',out,10,hashlib.sha256(b'abcdefghij').hexdigest())==out
    assert out.read_bytes()==b'abcdefghij'
    assert not out.with_suffix('.zip.part').exists()
    assert len(calls)==2


def test_unrelated_content_range_cannot_be_silently_appended(monkeypatch,tmp_path:Path):
    calls=[]
    def request(*args,**kwargs):
        calls.append(kwargs['headers'].copy())
        return Response(206,b'fghij',{'Content-Range':'bytes 0-4/10'})
    monkeypatch.setattr(dl.requests,'get',request)
    out=tmp_path/'real_data.zip'
    (tmp_path/'real_data.zip.part').write_bytes(b'abcde')
    with pytest.raises(RuntimeError,match='Unexpected Content-Range'):
        dl.download('https://example.test/download',out,10,retries=1)
    assert (tmp_path/'real_data.zip.part').read_bytes()==b'abcde'
    assert not out.exists()


def test_bad_digest_never_promotes_partial_or_clobbers_good_output(monkeypatch,tmp_path:Path):
    monkeypatch.setattr(dl.requests,'get',lambda *a,**k:Response(200,b'abcdefghij'))
    out=tmp_path/'real_data.zip';out.write_bytes(b'old valid archive')
    with pytest.raises(RuntimeError,match='SHA256 mismatch'):
        dl.download('https://example.test/download',out,10,'0'*64,retries=1)
    assert out.read_bytes()==b'old valid archive'
    assert not out.with_suffix('.zip.part').exists()


def test_http_200_to_resume_restarts_without_duplicate_bytes(monkeypatch,tmp_path:Path):
    out=tmp_path/'real_data.zip';(tmp_path/'real_data.zip.part').write_bytes(b'abcde')
    monkeypatch.setattr(dl.requests,'get',lambda *a,**k:Response(200,b'abcdefghij'))
    assert dl.download('https://example.test/download',out,10)==out
    assert out.read_bytes()==b'abcdefghij'


def test_complete_partial_verified_without_redownload(monkeypatch,tmp_path:Path):
    out=tmp_path/'real_data.zip';(tmp_path/'real_data.zip.part').write_bytes(b'abcdefghij')
    monkeypatch.setattr(dl.requests,'get',lambda *a,**k:pytest.fail('must not fetch complete partial'))
    assert dl.download('https://example.test/download',out,10,hashlib.sha256(b'abcdefghij').hexdigest())==out
    assert out.read_bytes()==b'abcdefghij'


def test_failed_training_preflight_removes_stale_evidence_files(tmp_path:Path):
    from scripts.train_submission import run
    r=tmp_path/'reports';r.mkdir()
    (r/'evidence_manifest.json').write_text('{"status":"FAKE_OLD_PASS"}')
    (r/'submission_gate.json').write_text('{"status":"PASS"}')
    with pytest.raises(ValueError,match='preflight failed'):
        run(tmp_path/'missing',tmp_path/'models',r/'evidence_manifest.json')
    assert not (r/'evidence_manifest.json').exists()
    assert not (r/'submission_gate.json').exists()
    import json
    assert json.loads((tmp_path/'models'/'promotion.json').read_text())['runtime_promotion_allowed'] is False
