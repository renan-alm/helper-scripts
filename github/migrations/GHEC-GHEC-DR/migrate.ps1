#!/usr/bin/env pwsh

# =========== Created with CLI version 1.15.0 ===========

function ExecAndGetMigrationID {
    param (
        [scriptblock]$ScriptBlock
    )
    $MigrationID = & @ScriptBlock | ForEach-Object {
        Write-Host $_
        $_
    } | Select-String -Pattern "\(ID: (.+)\)" | ForEach-Object { $_.matches.groups[1] }
    return $MigrationID
}

if (-not $env:GH_PAT) {
    Write-Error "GH_PAT environment variable must be set to a valid GitHub Personal Access Token with the appropriate scopes. For more information see https://docs.github.com/en/migrations/using-github-enterprise-importer/preparing-to-migrate-with-github-enterprise-importer/managing-access-for-github-enterprise-importer#creating-a-personal-access-token-for-github-enterprise-importer"
    exit 1
} else {
    Write-Host "GH_PAT environment variable is set and will be used to authenticate to GitHub."
}

$Succeeded = 0
$Failed = 0
$RepoMigrations = [ordered]@{}

# =========== Organization: renan-org ===========

# === Queuing repo migrations ===
$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "repo-name-test" --github-target-org "ProximaEvaluation" --target-repo "repo-name-test" --queue-only --target-repo-visibility private }
$RepoMigrations["repo-name-test"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "repo-sample" --github-target-org "ProximaEvaluation" --target-repo "repo-sample" --queue-only --target-repo-visibility public }
$RepoMigrations["repo-sample"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "new-azureai-samples" --github-target-org "ProximaEvaluation" --target-repo "new-azureai-samples" --queue-only --target-repo-visibility private }
$RepoMigrations["new-azureai-samples"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "rename-my-other-repo" --github-target-org "ProximaEvaluation" --target-repo "rename-my-other-repo" --queue-only --target-repo-visibility private }
$RepoMigrations["rename-my-other-repo"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "my-repo-project-2" --github-target-org "ProximaEvaluation" --target-repo "my-repo-project-2" --queue-only --target-repo-visibility private }
$RepoMigrations["my-repo-project-2"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "IssueMaker" --github-target-org "ProximaEvaluation" --target-repo "IssueMaker" --queue-only --target-repo-visibility private }
$RepoMigrations["IssueMaker"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "python-lessons" --github-target-org "ProximaEvaluation" --target-repo "python-lessons" --queue-only --target-repo-visibility private }
$RepoMigrations["python-lessons"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "swb-repo-list" --github-target-org "ProximaEvaluation" --target-repo "swb-repo-list" --queue-only --target-repo-visibility private }
$RepoMigrations["swb-repo-list"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "demo-repository" --github-target-org "ProximaEvaluation" --target-repo "demo-repository" --queue-only --target-repo-visibility private }
$RepoMigrations["demo-repository"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo ".github" --github-target-org "ProximaEvaluation" --target-repo ".github" --queue-only --target-repo-visibility public }
$RepoMigrations[".github"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "dependabot-demo" --github-target-org "ProximaEvaluation" --target-repo "dependabot-demo" --queue-only --target-repo-visibility public }
$RepoMigrations["dependabot-demo"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "js-action-demo" --github-target-org "ProximaEvaluation" --target-repo "js-action-demo" --queue-only --target-repo-visibility public }
$RepoMigrations["js-action-demo"] = $MigrationID

$MigrationID = ExecAndGetMigrationID { gh gei migrate-repo --github-source-org "renan-org" --source-repo "required-workflows" --github-target-org "ProximaEvaluation" --target-repo "required-workflows" --queue-only --target-repo-visibility public }
$RepoMigrations["required-workflows"] = $MigrationID


# =========== Waiting for all migrations to finish for Organization: renan-org ===========

if ($RepoMigrations["repo-name-test"]) { gh gei wait-for-migration --migration-id $RepoMigrations["repo-name-test"] }
if ($RepoMigrations["repo-name-test"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["repo-sample"]) { gh gei wait-for-migration --migration-id $RepoMigrations["repo-sample"] }
if ($RepoMigrations["repo-sample"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["new-azureai-samples"]) { gh gei wait-for-migration --migration-id $RepoMigrations["new-azureai-samples"] }
if ($RepoMigrations["new-azureai-samples"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["rename-my-other-repo"]) { gh gei wait-for-migration --migration-id $RepoMigrations["rename-my-other-repo"] }
if ($RepoMigrations["rename-my-other-repo"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["my-repo-project-2"]) { gh gei wait-for-migration --migration-id $RepoMigrations["my-repo-project-2"] }
if ($RepoMigrations["my-repo-project-2"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["IssueMaker"]) { gh gei wait-for-migration --migration-id $RepoMigrations["IssueMaker"] }
if ($RepoMigrations["IssueMaker"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["python-lessons"]) { gh gei wait-for-migration --migration-id $RepoMigrations["python-lessons"] }
if ($RepoMigrations["python-lessons"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["swb-repo-list"]) { gh gei wait-for-migration --migration-id $RepoMigrations["swb-repo-list"] }
if ($RepoMigrations["swb-repo-list"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["demo-repository"]) { gh gei wait-for-migration --migration-id $RepoMigrations["demo-repository"] }
if ($RepoMigrations["demo-repository"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations[".github"]) { gh gei wait-for-migration --migration-id $RepoMigrations[".github"] }
if ($RepoMigrations[".github"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["dependabot-demo"]) { gh gei wait-for-migration --migration-id $RepoMigrations["dependabot-demo"] }
if ($RepoMigrations["dependabot-demo"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["js-action-demo"]) { gh gei wait-for-migration --migration-id $RepoMigrations["js-action-demo"] }
if ($RepoMigrations["js-action-demo"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }

if ($RepoMigrations["required-workflows"]) { gh gei wait-for-migration --migration-id $RepoMigrations["required-workflows"] }
if ($RepoMigrations["required-workflows"] -and $lastexitcode -eq 0) { $Succeeded++ } else { $Failed++ }


Write-Host =============== Summary ===============
Write-Host Total number of successful migrations: $Succeeded
Write-Host Total number of failed migrations: $Failed

if ($Failed -ne 0) {
    exit 1
}


