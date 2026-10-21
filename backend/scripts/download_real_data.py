"""Reproducible public-data acquisition for HimanshuDigitalTwin.

Examples:
  python scripts/download_real_data.py shanghai
  python scripts/download_real_data.py shanghai --harmonized
  python scripts/download_real_data.py cgmacros
  python scripts/download_real_data.py bigideas --participant 012

Datasets remain isolated by source; subjects are never stitched across cohorts.
"""
from __future__ import annotations
import argparse, hashlib, shutil, time, zipfile, re, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.partial_zip_csv import extract_csv_only, PHYSIONET, S3_MIRROR, RangeNotSupported
from scripts.preflight_data import audit_cgmacros

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'raw'
SOURCES = {
    'shanghai_original': {
        'url':'https://ndownloader.figshare.com/files/42966622',
    },
    'shanghai_harmonized': {
        'url':'https://raw.githubusercontent.com/Augmented-Health-Lab/Glucose-ML-Project/decf266461dd125ead7715bf524e5ffb9b9469c4/3_Glucose-ML-collection/ShanghaiT2DM/ShanghaiT2DM-from-Glucose-ML.zip',
    },
    'cgmacros': {
        'url':'https://physionet.org/files/cgmacros/1.0.0/CGMacros_dateshifted365.zip',
        'size':657187340,
        'sha256':'05c8b0e6f1a2757050aced55ce4bf6ab2ac9b30f2fd8ca193056812d9c621d4d',
    },
}


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def download(url: str, out: Path, expected_size: int|None=None, expected_sha256: str|None=None, retries=4):
    """Resume a verified .part file; promote it only after full-size/hash checks.

    Failed transfers never clobber a previously verified destination, and
    short transfers retain their partial bytes so the next attempt can resume.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    partial=out.with_suffix(out.suffix+'.part')
    for attempt in range(1,retries+1):
        existing=partial.stat().st_size if partial.exists() else 0
        if expected_size is not None and existing>expected_size:
            partial.unlink(); existing=0
        headers={'User-Agent':'HimanshuDigitalTwin/0.18','Accept':'*/*'}
        if existing:
            headers['Range']=f'bytes={existing}-'
        try:
            if expected_size is None or existing!=expected_size:
                with requests.get(url,stream=True,timeout=(20,180),headers=headers,allow_redirects=True) as r:
                    # If server ignores a Range request, restart from zero;
                    # if it responds with an unrelated byte range, reject it.
                    if existing and r.status_code==200:
                        existing=0; partial.unlink(missing_ok=True)
                    elif existing and r.status_code==206:
                        content_range=r.headers.get('Content-Range','')
                        if not re.match(rf'^bytes\s+{existing}-\d+/\d+$',content_range):
                            raise RuntimeError('Unexpected Content-Range: '+content_range)
                    elif existing:
                        r.raise_for_status()
                        raise RuntimeError('Resume request did not return HTTP 200 or 206')
                    r.raise_for_status()
                    mode='ab' if existing else 'wb'
                    with partial.open(mode) as f:
                        for chunk in r.iter_content(chunk_size=4*1024*1024):
                            if chunk: f.write(chunk)
            if expected_size is not None and partial.stat().st_size != expected_size:
                size=partial.stat().st_size
                if size>expected_size: partial.unlink()
                raise RuntimeError(f'Size mismatch: got {size}, expected {expected_size}')
            if expected_sha256 is not None:
                digest=sha256(partial)
                if digest.lower()!=expected_sha256.lower():
                    partial.unlink(missing_ok=True)
                    raise RuntimeError(f'SHA256 mismatch: {digest} != {expected_sha256}')
            # Atomic replace only after a complete verified archive exists.
            partial.replace(out)
            return out
        except Exception:
            if attempt>=retries: raise
            time.sleep(min(2*attempt,12))
    raise RuntimeError(f'Download failed: {url}')


def unpack_if_zip(path: Path, dest: Path):
    if not zipfile.is_zipfile(path):
        raise RuntimeError(f'Downloaded file is not a valid ZIP: {path}')
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        z.extractall(dest)
    return True


def bigideas_files(pid: str):
    pid=f'{int(pid):03d}'
    base=f'https://physionet.org/files/big-ideas-glycemic-wearable/1.1.3/{pid}'
    return {f'Dexcom_{pid}.csv':f'{base}/Dexcom_{pid}.csv?download=',f'Food_Log_{pid}.csv':f'{base}/Food_Log_{pid}.csv?download='}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('dataset',choices=['shanghai','cgmacros','bigideas'])
    ap.add_argument('--harmonized',action='store_true')
    ap.add_argument('--participant',default='012')
    ap.add_argument('--keep-archive',action='store_true')
    ap.add_argument('--csv-only', action='store_true', help='Fast acquisition of the 45 multimodal CSVs + bio.csv via ZIP HTTP byte ranges; excludes photographs')
    args=ap.parse_args(); ROOT.mkdir(parents=True,exist_ok=True)
    if args.dataset=='shanghai':
        key='shanghai_harmonized' if args.harmonized else 'shanghai_original'; spec=SOURCES[key]
        dest=ROOT/'shanghai'/('ShanghaiT2DM_harmonized.zip' if args.harmonized else 'Shanghai_original.zip')
        download(spec['url'],dest); unpack_if_zip(dest,dest.with_suffix(''))
        print(f'Downloaded Shanghai data to {dest.parent}')
    elif args.dataset=='cgmacros':
        spec=SOURCES['cgmacros']; dest=ROOT/'cgmacros'/'CGMacros_dateshifted365.zip'
        extract_dir=ROOT/'cgmacros'/'CGMacros_dateshifted365'
        existing_subjects=list(extract_dir.rglob('CGMacros-*.csv')) if extract_dir.exists() else []
        existing_bio=list(extract_dir.rglob('bio.csv')) if extract_dir.exists() else []
        if len(existing_subjects)>=45 and existing_bio:
            audit=audit_cgmacros(extract_dir)
            legacy_csv_manifest=((extract_dir/'csv_only_manifest.json').exists()
                                 and audit.get('csv_only_manifest_integrity')!='VERIFIED')
            if audit['ready_for_final_primary_training'] and not legacy_csv_manifest:
                print(f'CGMacros complete cohort preflight passed; skipping download: {extract_dir}')
                return
            if legacy_csv_manifest:
                print('Older selective-download manifest lacks per-file SHA-256; revalidating official ZIP members.')
            print('Existing CGMacros extraction failed structural/observation preflight; attempting repair.')
        if args.csv_only:
            errors=[]
            for url in (S3_MIRROR, PHYSIONET):
                try:
                    report=extract_csv_only(url, extract_dir)
                    print('Official CGMacros CSV-only extraction completed. ZIP CRC32 checked for every member.')
                    print('IMPORTANT: Full archive SHA256 is NOT validated in CSV-only mode.')
                    print(f'CSV members: {report["selected_files"]}, source: {url}')
                    return
                except (requests.RequestException, OSError, RangeNotSupported) as ex:
                    errors.append(f'{url}: {type(ex).__name__}: {ex}')
            raise RuntimeError('Selective download failed; source must support byte-range requests.\n' + '\n'.join(errors) + '\nUse the full-download mode or run this script on a network with HTTP Range support.')
        print('Downloading official CGMacros archive (~657 MB) with resume + SHA256 verification...')
        download(spec['url'],dest,spec['size'],spec['sha256'])
        unpack_if_zip(dest,extract_dir)
        if not args.keep_archive: dest.unlink(missing_ok=True)
        print(f'CGMacros verified and extracted to {extract_dir}')
    else:
        pid=f'{int(args.participant):03d}'; base=ROOT/'bigideas'/pid
        for name,url in bigideas_files(pid).items(): download(url,base/name)
        print(f'Downloaded BIG IDEAs CGM + food log for participant {pid} to {base}')

if __name__=='__main__': main()
