#!/usr/bin/env bash

# Set your GitHub Personal Access Token (repo, admin:org, workflow)
GITHUB_PAT="<your_github_pat>"
# Name of the migration destination organization on GitHub 
DESTINATION_ORG_NAME="<destination_org_name>"
# Use https://gitlab.com or the server URL e.g https://gitlab.example.com
MIGRATION_SOURCE_URL="<migration_source_url>"
# Name of the repository on GitHub
REPOSITORY_NAME_ON_GITHUB="<repository_name_on_github>"
# Visibility of the repository on github
TARGET_REPO_VISIBILITY="<target_repo_visibility>"
# URL of the source repository (e.g. https://gitlab.com/owner/repo) url has to match with the data in the export archive
GITLAB_SOURCE_REPOSITORY_URL="<gitlab_source_repository_url>"
# The SAS URL to the storage containing the migration archive
GIT_ARCHIVE_URL="<git_archive_url>"
# The SAS URL to the storage containing the migration archive, should be the same as "GIT_ARCHIVE_URL"
METADATA_ARCHIVE_URL="<metadata_archive_url>"


echo "[Step 1] Querying organization info for: $DESTINATION_ORG_NAME"
ORG_RESPONSE=$(curl -s -X POST https://api.github.com/graphql \
  -H "Authorization: bearer $GITHUB_PAT" \
  -H "content-type: application/json" \
  -H "GraphQL-Features: octoshift_gl_exporter" \
  -d '{
    "query": "query ($login: String!) { organization(login: $login) { login id name databaseId } }",
    "variables": { "login": "'$DESTINATION_ORG_NAME'" }
  }')
OWNER_ID=$(echo "$ORG_RESPONSE" | jq -r '.data.organization.id')
if [[ "$OWNER_ID" == "null" || -z "$OWNER_ID" ]]; then
  echo "[ERROR] Failed to get organization ID. Response: $ORG_RESPONSE"
  exit 1
fi
echo "[Step 1] Organization ID: $OWNER_ID"

echo "[Step 2] Creating migration source: $DESTINATION_ORG_NAME"
MIGRATION_SOURCE_RESPONSE=$(curl -s -X POST https://api.github.com/graphql \
  -H "Authorization: bearer $GITHUB_PAT" \
  -H "content-type: application/json" \
  -H "GraphQL-Features: octoshift_gl_exporter" \
  -d '{
    "query": "mutation createMigrationSource($name: String!, $ownerId: ID!, $url: String!) { createMigrationSource(input: { name: $name url: $url ownerId: $ownerId type: GL_EXPORTER_ARCHIVE }) { migrationSource { id name url type }} }",
    "variables": {
      "ownerId": "'$OWNER_ID'",
      "name": "'$DESTINATION_ORG_NAME'",
      "url": "'$MIGRATION_SOURCE_URL'",
      "type": "GL_EXPORTER_ARCHIVE"
    }
  }')
SOURCE_ID=$(echo "$MIGRATION_SOURCE_RESPONSE" | jq -r '.data.createMigrationSource.migrationSource.id')
if [[ "$SOURCE_ID" == "null" || -z "$SOURCE_ID" ]]; then
  echo "[ERROR] Failed to create migration source. Response: $MIGRATION_SOURCE_RESPONSE"
  exit 1
fi
echo "[Step 2] Migration Source ID: $SOURCE_ID"



echo "[Step 3] Starting repository migration for: $REPOSITORY_NAME_ON_GITHUB"
REPO_MIGRATION_RESPONSE=$(curl -s -X POST https://api.github.com/graphql \
  -H "Authorization: bearer $GITHUB_PAT" \
  -H "content-type: application/json" \
  -H "GraphQL-Features: octoshift_gl_exporter" \
  -d '{
        "query": "mutation startRepositoryMigration($sourceId: ID!, $ownerId: ID!, $sourceRepositoryUrl: URI!, $repositoryName: String!, $continueOnError: Boolean!, $accessToken: String!, $githubPat: String!, $targetRepoVisibility: String!, $gitArchiveUrl: String!, $metadataArchiveUrl: String!) { startRepositoryMigration(input: { sourceId: $sourceId ownerId: $ownerId repositoryName: $repositoryName continueOnError: $continueOnError accessToken: $accessToken githubPat: $githubPat targetRepoVisibility: $targetRepoVisibility sourceRepositoryUrl: $sourceRepositoryUrl gitArchiveUrl: $gitArchiveUrl metadataArchiveUrl: $metadataArchiveUrl }) { repositoryMigration { id migrationSource { id name type } sourceUrl } } }",
        "variables": {
            "sourceId": "'$SOURCE_ID'",
            "ownerId": "'$OWNER_ID'",
            "sourceRepositoryUrl": "'$GITLAB_SOURCE_REPOSITORY_URL'",
            "repositoryName": "'$REPOSITORY_NAME_ON_GITHUB'",
            "continueOnError": true,
            "accessToken": "",
            "githubPat": "'$GITHUB_PAT'",
            "targetRepoVisibility": "'$TARGET_REPO_VISIBILITY'",
            "gitArchiveUrl": "'$GIT_ARCHIVE_URL'",
            "metadataArchiveUrl": "'$METADATA_ARCHIVE_URL'"
      }
    }')
MIGRATION_ID=$(echo "$REPO_MIGRATION_RESPONSE" | jq -r '.data.startRepositoryMigration.repositoryMigration.id')
if [[ "$MIGRATION_ID" == "null" || -z "$MIGRATION_ID" ]]; then
  echo "[ERROR] Failed to start repository migration. Response: $REPO_MIGRATION_RESPONSE"
  exit 1
fi
echo "[Step 3] Migration ID: $MIGRATION_ID"



echo "[Step 4] Polling migration status every 10 seconds..."
while true; do
  MIGRATION_STATUS_RESPONSE=$(curl -s -X POST https://api.github.com/graphql \
    -H "Authorization: bearer $GITHUB_PAT" \
    -H "content-type: application/json" \
    -H "GraphQL-Features: octoshift_gl_exporter" \
    -d '{
      "query": "query ($id: ID!) { node(id: $id) { ... on Migration { id sourceUrl migrationSource { name } state failureReason } } }",
      "variables": {
        "id": "'$MIGRATION_ID'"
      }
    }')
  STATE=$(echo "$MIGRATION_STATUS_RESPONSE" | jq -r '.data.node.state')
  FAILURE_REASON=$(echo "$MIGRATION_STATUS_RESPONSE" | jq -r '.data.node.failureReason')
  echo "[Step 4] Migration state: $STATE"
  if [[ "$STATE" == "FAILED" || "$STATE" == "FAILED_VALIDATION" ]]; then
    echo "[ERROR] Migration failed. Reason: $FAILURE_REASON"
    break
  elif [[ "$STATE" == "SUCCEEDED" ]]; then
    echo "[SUCCESS] Migration succeeded."
    break
  fi
  sleep 10
done
