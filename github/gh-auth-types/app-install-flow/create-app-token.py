#!/usr/bin/env python3
"""
This script generates a GitHub App token using a provided private key, app ID, and installation ID.

Usage:
    python create-app-token.py --key-path <path_to_private_key> --client-id <client_id> --installation-id <installation_id> [--encryption-alg <algorithm>]

Arguments:
    --key-path: Path to the GitHub App Private key file.
    --client-id: GitHub App Client ID.
    --installation-id: GitHub App Installation ID.
    --encryption-alg: (Optional) Encryption algorithm for JWT. Default is "RS256".

Example:
    python create-app-token.py --key-path ~/.renan/github_app_pem --client-id Iv23lit9DQwWYFRwetEk --installation-id 56035202
"""

import argparse
import time
import jwt      # PyJWT library - pip install pyjwt
import warnings

warnings.filterwarnings("ignore", category=Warning)

import requests


## Function provided by GitHub 
#  https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app#example-using-python-to-generate-a-jwt
def generate_jwt(client_id: str, key_path: str, algorithm: str) -> str:

    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,  # Setting expiry to 5 min
        "iss": str(client_id)
    }

    with open(key_path, "rb") as key_file:
        signing_key = key_file.read()
        print(f"Private key loaded from {key_path}")

    encoded_jwt = jwt.encode(payload, signing_key, algorithm=algorithm)
    print(f"JWT generated: {encoded_jwt}")

    return encoded_jwt

def call_gh_api(encoded_jwt: str, installation_id: str) -> str:
    headers = {
        "Authorization": f"Bearer {encoded_jwt}",
        "Accept": "application/vnd.github.v3+json",
    }

    tries = 0
    while tries < 3:
        response = requests.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=headers,
        )
        
        if response.status_code == 201:
            response_json = response.json()
            if "token" in response_json:
                access_token = response_json["token"]
                print(f"GitHub App token created successfully")
                return access_token
        
        print(f"Attempt {tries + 1} failed. Status code: {response.status_code}")
        if response.status_code != 201:
            print(f"Error response: {response.text}")
        
        tries += 1
        if tries < 3:
            time.sleep(2)
    
    return "TOKEN_NOT_ACQUIRED"

def main():
    parser = argparse.ArgumentParser(description="Create a JWT")
    parser.add_argument(
        "--key-path",
        required=True,
        type=str,
        help="Path to the GitHub App Private key file",
    )
    parser.add_argument("--client-id", required=True, type=str, help="GitHub App Id")
    parser.add_argument(
        "--installation-id", required=True, type=str, help="GitHub App Installation Id"
    )
    parser.add_argument(
        "--encryption-alg",
        required=False,
        default="RS256",
        type=str,
        help="Encryption algorithm for jwt",
    )
    args = parser.parse_args()

    encoded_jwt = generate_jwt(args.client_id, args.key_path, args.encryption_alg)

    token = call_gh_api(encoded_jwt, args.installation_id)
    
    if token != "TOKEN_NOT_ACQUIRED":
        print(f"Access Token: {token}")
    else:
        print("Failed to acquire access token after 3 attempts")


if __name__ == "__main__":
    main()
