# Publish to the confirmed public repository

Target: https://github.com/himanshu051116/Himanshu-DigitalTwin

**At last check GitHub confirmed the repo was public but empty.** The user must authenticate with a GitHub account authorized to push. This release bundle is prepared locally; producing it does **not** mean the repository has been populated.

1. Extract `Himanshu_DigitalTwin_GitHub_Ready.zip` and open a terminal inside the extracted folder (where `README.md` is visible).
2. Sign in to GitHub using Git Credential Manager or GitHub CLI (`gh auth login`).
3. Run the supplied `PUBLISH_TO_GITHUB.ps1` on Windows PowerShell or use the git commands below. Do not force-push.
4. Visit the repository in a private browser window; confirm `README.md`, `backend/app/main.py` and the PDF/presentation links all load.
5. Add and verify the actual demo-video link in the competition form. Publication to GitHub alone is **not** an Unstop submission.

```bash
git init -b main
git add .
git commit -m "Submit HimanshuDigitalTwin research prototype"
git remote add origin https://github.com/himanshu051116/Himanshu-DigitalTwin.git
git push -u origin main
```

If the repository has gained commits since this package was made, **stop** and reconcile instead of overwriting existing work.
