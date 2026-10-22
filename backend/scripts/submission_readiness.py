"""Strict offline submission inventory for Happiest Health 2026.

This verifies files and self-attestations, never asserts an external link was
opened or that the event portal accepted a submission. Run from any directory.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import re

BASE = Path(__file__).resolve().parents[2]
REQUIRED_FILES = {
    'source_license': 'LICENSE',
    'competition_readme': 'README.md',
    'architecture_pdf': 'submission/architecture.pdf',
    'presentation_pdf': 'submission/HimanshuDigitalTwin_Presentation.pdf',
    'presentation_editable': 'submission/HimanshuDigitalTwin_Presentation.pptx',
    'demo_runbook': 'submission/DEMO_RUNBOOK.md',
    'video_script': 'submission/VIDEO_RECORDING_PLAN.md',
}


def _remote_url(url: str, allowed_host: str) -> bool:
    """Validate only syntax/host, NOT availability, public visibility or quality."""
    try:
        p = urlparse(url)
        return p.scheme == 'https' and (p.hostname == allowed_host or
            (allowed_host == 'youtube.com' and p.hostname in ('www.youtube.com', 'youtu.be', 'youtube.com')) or
            (allowed_host == 'github.com' and p.hostname == 'www.github.com')) and bool(p.path.strip('/'))
    except (TypeError, ValueError):
        return False


def _youtube_video_url(url: str) -> bool:
    """Validate plausible YouTube watch/share URL; never assert link is playable."""
    try:
        p = urlparse(url)
        if p.scheme != 'https':
            return False
        host = (p.hostname or '').lower()
        if host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            video_id = parse_qs(p.query).get('v', [''])[0] if p.path == '/watch' else ''
        elif host == 'youtu.be':
            video_id = p.path.strip('/')
        else:
            return False
        return bool(re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id))
    except (TypeError, ValueError):
        return False


def evaluate(root: Path, metadata: dict) -> dict:
    root=Path(root)
    checks=[]
    def add(name, ok, reason, evidence='automated-local'):
        checks.append({'check':name,'passed':bool(ok),'reason':reason,'evidence_type':evidence})
    for k,relative in REQUIRED_FILES.items():
        file=root/relative
        add(k,file.is_file() and file.stat().st_size>0,f'{relative} exists and is non-empty')
    add('team_name',bool(str(metadata.get('team_name','')).strip()),'Team name confirmed',evidence='user-confirmed')
    add('college_name',bool(str(metadata.get('college_name','')).strip()),'College name confirmed',evidence='user-confirmed')
    add('team_leader',bool(str(metadata.get('team_leader_name','')).strip()),'Team leader confirmed',evidence='user-confirmed')
    members=metadata.get('team_members',[])
    add('team_size',isinstance(members,list) and 1<=len(members)<=4 and all(isinstance(m,str) and m.strip() for m in members),
        'Between one and four confirmed members',evidence='user-confirmed')
    add('registered',metadata.get('registration_confirmed') is True,'Unstop registration completed',evidence='user-confirmed')
    url=metadata.get('public_github_repo_url','')
    add('github_url_format',_remote_url(url,'github.com'),'Public GitHub repository URL formatted correctly',evidence='syntax-only')
    add('github_public_checked',metadata.get('public_repository_confirmed') is True,'Repo and all paths manually confirmed accessible to reviewers',evidence='manual-attestation')
    vid=metadata.get('demo_video_url','')
    add('video_url_format',_youtube_video_url(vid),
        'Demonstration video URL syntax valid',evidence='syntax-only')
    readme_path = root / 'README.md'
    readme = readme_path.read_text(encoding='utf-8') if readme_path.is_file() else ''
    add('video_url_in_readme', bool(vid and _youtube_video_url(vid) and vid in readme),
        'Same valid video URL is present in root README', evidence='local-file')
    duration=metadata.get('demo_video_duration_minutes')
    add('video_length',isinstance(duration,(int,float)) and not isinstance(duration,bool) and duration>=20,
        'At least 20-minute video, per official current listing; verify participant dashboard wording',evidence='user-confirmed')
    add('video_access_checked',metadata.get('video_link_access_confirmed') is True,
        'Video link personally checked in a private browser',evidence='manual-attestation')
    add('portal_submission_checked',metadata.get('submission_platform_entry_confirmed') is True,
        'Team leader submitted requested information and public repository link on Unstop',evidence='manual-attestation')
    return {'project':'HimanshuDigitalTwin','competition':'Happiest Health Digital Twin Challenge 2026',
        'gate':'READY' if all(x['passed'] for x in checks) else 'NOT_READY',
        'passed':sum(x['passed'] for x in checks),'total':len(checks),
        'checks':checks,'caveat':'This offline inventory does not verify external URLs, video contents, registration eligibility, or acceptance by Unstop.'}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,default=BASE)
    ap.add_argument('--metadata',type=Path)
    ap.add_argument('--out',type=Path)
    args=ap.parse_args()
    data_path=args.metadata or args.root/'submission'/'submission_metadata.json'
    metadata=json.loads(data_path.read_text(encoding='utf-8'))
    report=evaluate(args.root,metadata)
    print(json.dumps(report,indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if report['gate']=='READY' else 2)

if __name__=='__main__':main()
