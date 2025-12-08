# [Migration processes](https://github.com/solidify-internal/github-migrations/edit/main/GHES2GHEC/migration-guide.md) 
## Scope
GHES to GHEC
GHES to GHEC-DR
GHEC to GHEC

## Pre-requisites:

- GH CLI installed https://github.com/cli/cli
- GH CLI GEI xtension installed https://github.com/github/gh-gei
- Export two PATs (source org and dest org). GH_SOUCE_PAT and GH_PAT.
- API URL for the source org. GH_API_URL.
- (ONLY FOR GHES) Cloud provider: AZ (or AWS) for a storage account.

## What is not migrated?
Secrets, environments, and workflow history.
https://docs.github.com/en/migrations/using-github-enterprise-importer/migrating-between-github-products/about-migrations-between-github-products

## Steps GHEC to GHEC-DR
1. Set up the environment variables which will be used to **authenticate** towards GHEC and GHEC-DR, and to **define** the source and target organizations and repositories. 
```bash
# Authentication
export GH_PAT=your-gh-pat
export GH_SOUCE_PAT=your-gh-source-pat

# Organization names
export SOURCE_ORG=renan-org
export TARGET_ORG=ProximaEvaluation

# Repo names
export SOURCE_REPO=python-lessons
# export TARGET_REPO=python-lessons

# APIs
export TARGET_API_URL="https://api.solidifyeur.ghe.com"
# export TARGET_API_URL="https://api.github.com/"
```

2. Run the CLI command to run the migration of a repo itself.
```bash
gh gei migrate-repo --github-source-org $SOURCE_ORG --source-repo $SOURCE_REPO --github-target-org $TARGET_ORG --target-api-url $TARGET_API_URL
```

**Recommendation**: Verify the remaining rate limit on the source org before proceeding with a next migration. If/when running in parallel, increase the amount of threads gradually. 
https://api.github.com/rate_limit

`curl --location 'https://api.solidifyeur.ghe.com/rate_limit' --header 'Accept: application/vnd.github.v3+json' --header 'Authorization: Bearer ghp_ABCD' | jq .rate`

Note: An Issue will be created at the target repository with the logs of the migration process. 
