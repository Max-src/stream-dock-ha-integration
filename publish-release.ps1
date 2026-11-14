# Puts the latest work on GitHub: checks the versions agree, pushes the
# commits, then publishes a release for the manifest's version with
# docs/release-notes.md as its notes. The Marketplace and HACS take the latest
# release as the version to install, so a tag alone isn't enough.
#
#   powershell -ExecutionPolicy Bypass -File .\publish-release.ps1
Set-Location $PSScriptRoot

function Stop-With($message) {
  Write-Host $message -ForegroundColor Red
  exit 1
}

$manifest = Get-Content custom_components\stream_dock_ha\manifest.json -Raw | ConvertFrom-Json
$version = $manifest.version
$tag = "v$version"

# The card tells the integration which version it is; they must be the same.
$card = Select-String -Path custom_components\stream_dock_ha\frontend\stream-dock-card.js -Pattern "^const CARD_VERSION = '(.+)';"
if (-not $card -or $card.Matches[0].Groups[1].Value -ne $version) {
  Stop-With "The card's CARD_VERSION doesn't match the manifest's $version. Nothing was published."
}
if (git status --porcelain) { Stop-With 'There are changes not yet committed. Commit them first; nothing was published.' }

Write-Host 'Pushing the commits...'
git push origin main
if ($LASTEXITCODE -ne 0) { Stop-With 'Pushing failed, so nothing was published.' }

$ErrorActionPreference = 'SilentlyContinue'
gh release view $tag *> $null
$exists = $LASTEXITCODE -eq 0
$ErrorActionPreference = 'Continue'

if ($exists) {
  Write-Host "Release $tag already exists: updating its notes."
  gh release edit $tag --notes-file docs\release-notes.md
} else {
  Write-Host "Publishing release $tag..."
  gh release create $tag --target main --title "Stream Dock HA integration $version" --notes-file docs\release-notes.md
}
if ($LASTEXITCODE -ne 0) { Stop-With 'Publishing the release failed.' }

Write-Host 'Done: https://github.com/Max-src/stream-dock-ha-integration/releases/latest' -ForegroundColor Green
