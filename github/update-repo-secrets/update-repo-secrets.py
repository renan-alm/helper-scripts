#!/usr/bin/env python3

import requests
import argparse
import json
import sys
from base64 import b64encode
from nacl import encoding, public

requests.packages.urllib3.disable_warnings() # Disable SSL warnings


ORG_OWNER = "icagruppen"
ORGS_API_URL = f"https://api.github.com/orgs/{ORG_OWNER}"
REPOS_API_URL = f"https://api.github.com/repos/{ORG_OWNER}"

## YOU NEED TO EDIT THE FOLLOWING INPUT
LIST_OF_REPOS = ['cdc-scripts', 'cdc-techradar']


def add_secret(repo: str, secret_name:str, secret_value:str, token: str) -> None:
        headers = {
            "accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        key, key_id = get_repo_public_key(repo, token)
        encrypted_secret = encrypt_secret(key, secret_value)
        body = {
                "encrypted_value": str(encrypted_secret),
                "key_id": str(key_id),
            }
        response = requests.put(f"{REPOS_API_URL}/{repo}/actions/secrets/{secret_name}", headers=headers, data=body, verify=False)
        print(response.json())
        if response.status_code == 201:
            print(f"Creating secret for repository {repo}")
        elif response.status_code == 204:
            print(f"Updating secrets for repository {repo}")
        elif response.status_code != 201:
            print(f"Failed to ADD secret for repository {repo}. Error:", response.json()["message"])
            sys.exit(1)

def get_repo_public_key(repo_name: str, token: str) -> tuple:
    headers = {
        "accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    response = requests.get(f"{REPOS_API_URL}/{repo_name}/actions/secrets/public-key", headers=headers, verify=False)
    if response.status_code == 200:
        return response.json()["key"], response.json()["key_id"]
    else:
        print(f"Failed to get public key for repository {repo_name}. Error:", response.json()["message"])
        sys.exit(1)

def encrypt_secret(public_key: str, secret_value: str) -> str:
  """Encrypt a Unicode string using the public key."""
  public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
  sealed_box = public.SealedBox(public_key)
  encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))

  return b64encode(encrypted).decode("utf-8")

def main():
    parser = argparse.ArgumentParser(description='Create or Update Secrets in GitHub Repositories.')
    parser.add_argument('--token', required=True, type=str, help='GitHub token')
    parser.add_argument('--name', required=True, type=str, help='Secret Name on Repository')
    parser.add_argument('--value', required=True, type=str, help='Secret Name on Repository')
    args = parser.parse_args()
    
    for repo in LIST_OF_REPOS:
        add_secret(repo, args.name, args.value, args.token)

    print(f"Script complete!")


if __name__ == '__main__':
    main()
