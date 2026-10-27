param([Parameter(Mandatory = $true)][string]$RepositoryPath)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath($RepositoryPath)
& gh auth status
if ($LASTEXITCODE -ne 0) { throw 'Run gh auth login --hostname github.com --git-protocol https --web first.' }
$branch = & git -C $repo branch --show-current
if ($branch -ne 'codex/ghj-research-completion') { throw 'Select the reviewed ghj delivery branch before submission.' }
$dirty = & git -C $repo status --porcelain
if ($dirty) { throw 'Commit local changes before submission.' }
$remote = & git -C $repo remote get-url origin
if ($remote -notmatch 'github\.com[:/]EternalZCL/zzr-edgefl-client-selection(\.git)?$') { throw 'Unexpected Git remote.' }
Push-Location -LiteralPath $repo
try {
    & git push --set-upstream origin $branch
    if ($LASTEXITCODE -ne 0) { throw 'Push failed. Check repository write access.' }
    $existing = & gh pr list --repo EternalZCL/zzr-edgefl-client-selection --head $branch --state open --json url --jq '.[0].url'
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect existing PRs.' }
    if ($existing) { Write-Output $existing }
    else {
        & gh pr create --repo EternalZCL/zzr-edgefl-client-selection --base main --head $branch --draft --title 'ghj: complete frozen HAPT study, baselines and 175-run evaluation' --body-file docs/ghj-study/PR.md
        if ($LASTEXITCODE -ne 0) { throw 'PR creation failed; the branch push may already have succeeded.' }
    }
}
finally { Pop-Location }
