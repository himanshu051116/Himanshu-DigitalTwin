$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is not installed. Install Git for Windows." }
if (Test-Path '.git') { throw "Already a Git repository. Review existing history and publish manually to avoid overwriting work." }
& git init -b main
if ($LASTEXITCODE -ne 0) { throw "git init failed" }
& git add .
if ($LASTEXITCODE -ne 0) { throw "git add failed" }
& git commit -m "Submit HimanshuDigitalTwin research prototype"
if ($LASTEXITCODE -ne 0) { throw "git commit failed; configure your Git identity and retry manually" }
& git remote add origin 'https://github.com/himanshu051116/Himanshu-DigitalTwin.git'
if ($LASTEXITCODE -ne 0) { throw "git remote add failed" }
& git push -u origin main
if ($LASTEXITCODE -ne 0) { throw "Push failed. Confirm GitHub authentication and that the remote branch is still empty. Do not force push." }
Write-Host 'Upload complete. Open the public GitHub repository to inspect the files.'
