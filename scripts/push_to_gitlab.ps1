<#
.SYNOPSIS
  Pusht dieses Repo nach GitLab.

.EXAMPLE
  .\scripts\push_to_gitlab.ps1 -Token "glpat-xxxxxxxx" -RemoteUrl "https://gitlab.example.org/user/repo.git"
#>
param(
    [Parameter(Mandatory = $true)][string]$Token,
    [Parameter(Mandatory = $true)][string]$RemoteUrl,
    [string]$Branch = "main",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
Write-Host "Repo: $repo"

if (-not (Test-Path ".git")) {
    git init
    git checkout -b $Branch
}

git add -A
if (git status --porcelain) {
    git -c user.name="Bike Tracker" -c user.email="bike-tracker@local" commit -m "Bike Tracker: Home Assistant Integration"
} else {
    Write-Host "Keine Aenderungen zu committen."
}

# Token nur fuer diesen Push verwenden, nicht dauerhaft in .git/config speichern.
$uri = [System.Uri]$RemoteUrl
$authUrl = "{0}://oauth2:{1}@{2}{3}" -f $uri.Scheme, $Token, $uri.Authority, $uri.AbsolutePath

if (-not (git remote | Select-String -Quiet "^origin$")) {
    git remote add origin $RemoteUrl
} else {
    git remote set-url origin $RemoteUrl
}

$pushArgs = @("push", "-u", $authUrl, "$($Branch):$Branch")
if ($Force) { $pushArgs += "--force" }
git @pushArgs

Write-Host ""
Write-Host "Fertig. Repo: $RemoteUrl" -ForegroundColor Green
