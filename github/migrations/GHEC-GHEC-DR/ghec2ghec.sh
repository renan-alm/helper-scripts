#!/bin/bash

# This script generates a PowerShell script to migrate repositories from a GitHub Enterprise Cloud (GHEC) to a GitHub Enterprise Cloud Data Residency (GHEC-DR).

# Authentication
export GH_SOURCE_PAT=$(cat ~/.renan/github_token) # GHEC
export GH_PAT=$(cat ~/.renan/github_EMU) # Another GHEC type

# Organization names
export SOURCE_ORG=renan-org
export TARGET_ORG=EMU_Evaluation

# Repo names - Not mandatory
export SOURCE_REPO=IssueMaker
# export TARGET_REPO=python-lessons

# APIs - Only needed for Proxima
export TARGET_API_URL="https://api.solidifyeur.ghe.com"
# export TARGET_API_URL="https://api.github.com/"

# storage-connection-string: Storage Account -> Access Keys -> Connection String
# export AZURE_STORAGE_CONNECTION_STRING="......."
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=actionsfundamentalsa275;AccountKey=ABCD==;EndpointSuffix=core.windows.net"

gh gei migrate-repo --github-source-org $SOURCE_ORG --source-repo $SOURCE_REPO --github-target-org $TARGET_ORG --target-api-url $TARGET_API_URL

gh gei migrate-repo --github-source-org $SOURCE_ORG --source-repo $SOURCE_REPO --github-target-org $TARGET_ORG  --target-repo $TARGET_REPO --target-api-url $TARGET_API_URL
