from scripts.submission_readiness import evaluate, _remote_url, REQUIRED_FILES


def test_blank_metadata_is_not_ready(tmp_path):
    r=evaluate(tmp_path,{})
    assert r['gate']=='NOT_READY'
    assert r['passed']==0


def test_a_real_local_deck_is_not_a_public_submission(tmp_path):
    for f in REQUIRED_FILES.values():
        p=tmp_path/f
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('contents')
    r=evaluate(tmp_path,{'college_name':'Gwalior'})
    assert r['gate']=='NOT_READY'
    assert r['passed']<r['total']


def test_complete_manual_acknowledgements_are_required(tmp_path):
    for f in REQUIRED_FILES.values():
        p=tmp_path/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('content')
    m=dict(team_name='Twin Team',college_name='MITS',team_leader_name='Lead',team_members=['Lead'],
           registration_confirmed=True,public_github_repo_url='https://github.com/example/HimanshuDigitalTwin',
           public_repository_confirmed=True,demo_video_url='https://www.youtube.com/watch?v=abcdefghijk',
           demo_video_duration_minutes=20,video_link_access_confirmed=True,submission_platform_entry_confirmed=True)
    # Only a syntactically plausible 11-character video ID is accepted, and
    # it must appear verbatim in the README. This is an offline fixture,
    # not evidence of a playable uploaded demonstration.
    (tmp_path/'README.md').write_text('Demo: '+m['demo_video_url'])
    assert evaluate(tmp_path,m)['gate']=='READY'
    m['video_link_access_confirmed']=False
    assert evaluate(tmp_path,m)['gate']=='NOT_READY'


def test_url_check_never_accepts_attacker_host():
    assert not _remote_url('https://github.com.evil.test/repo','github.com')
    assert not _remote_url('javascript:alert(1)','github.com')
    assert not _remote_url('http://github.com/owner/repo','github.com')
    assert _remote_url('https://github.com/owner/repo','github.com')
