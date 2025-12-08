#!/usr/bin/env python3
"""
This script generates a GitHub User Access Token using a GitHub App and handles token refresh.

Usage:
    python create-oauth-token.py --client-id <client_id> --client-secret <client_secret> [--code <authorization_code>] [--refresh-token <refresh_token>] [--revoke <token>]

Arguments:
    --client-id: GitHub App Client ID.
    --client-secret: GitHub App Client Secret.
    --code: (Optional) Authorization code from GitHub OAuth flow.
    --refresh-token: (Optional) Refresh token to get a new access token.
    --revoke: (Optional) Token to revoke (access token or refresh token).

Reference:
    https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens

Example:
    python create-oauth-token.py --client-id Iv23lit9DQwWYFRwetEk --client-secret <secret> --code gho_xxxxx
    python create-oauth-token.py --client-id Iv23lit9DQwWYFRwetEk --client-secret <secret> --refresh-token ghr_xxxxx
    python create-oauth-token.py --client-id Iv23lit9DQwWYFRwetEk --client-secret <secret> --revoke ghr_xxxxx
"""

import argparse
import json
import warnings

warnings.filterwarnings("ignore", category=Warning)

import requests


def exchange_code_for_token(client_id: str, client_secret: str, code: str) -> dict:
    """Exchange authorization code for access token and refresh token."""
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }
    
    headers = {
        "Accept": "application/json",
    }
    
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        json=payload,
        headers=headers,
    )
    
    if response.status_code == 200:
        response_json = response.json()
        if "error" in response_json:
            print(f"Error: {response_json.get('error_description', response_json['error'])}")
            return None
        print("Authorization code exchanged for tokens")
        return response_json
    else:
        print(f"Failed to exchange code. Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    """Refresh an expired access token using refresh token."""
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    
    headers = {
        "Accept": "application/json",
    }
    
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        json=payload,
        headers=headers,
    )
    
    if response.status_code == 200:
        response_json = response.json()
        if "error" in response_json:
            print(f"Error: {response_json.get('error_description', response_json['error'])}")
            return None
        print("Access token refreshed")
        return response_json
    else:
        print(f"Failed to refresh token. Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def revoke_token(client_id: str, client_secret: str, token: str) -> bool:
    """Revoke a GitHub OAuth token."""
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "token": token,
    }
    
    headers = {
        "Accept": "application/json",
    }
    
    response = requests.post(
        "https://github.com/login/oauth/revoke",
        json=payload,
        headers=headers,
    )
    
    if response.status_code == 204:
        print("Token revoked")
        return True
    else:
        print(f"Failed to revoke token. Status code: {response.status_code}")
        if response.text:
            print(f"Response: {response.text}")
        return False


def print_token_info(token_data: dict) -> None:
    """Print token information."""
    if not token_data:
        return
    
    print("\nToken Information:")
    print(f"Access Token: {token_data.get('access_token')}")
    print(f"Token Type: {token_data.get('token_type', 'bearer')}")
    print(f"Scope: {token_data.get('scope', 'N/A')}")
    print(f"Expires In: {token_data.get('expires_in', 'N/A')} seconds")
    if token_data.get('refresh_token'):
        print(f"Refresh Token: {token_data.get('refresh_token')}")
    if token_data.get('refresh_token_expires_in'):
        print(f"Refresh Token Expires In: {token_data.get('refresh_token_expires_in')} seconds")


def generate_auth_url(client_id: str, redirect_uri: str = "http://localhost:3000/callback", scope: str = "repo,user") -> str:
    """Generate GitHub OAuth authorization URL."""
    return f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope={scope}"


def main():
    parser = argparse.ArgumentParser(description="Create or refresh GitHub User Access Token")
    parser.add_argument(
        "--client-id",
        required=True,
        type=str,
        help="GitHub App Client ID",
    )
    parser.add_argument(
        "--client-secret",
        required=True,
        type=str,
        help="GitHub App Client Secret",
    )
    parser.add_argument(
        "--code",
        required=False,
        type=str,
        help="Authorization code from OAuth flow",
    )
    parser.add_argument(
        "--refresh-token",
        required=False,
        type=str,
        help="Refresh token to get new access token",
    )
    parser.add_argument(
        "--revoke",
        required=False,
        type=str,
        help="Token to revoke (access token or refresh token)",
    )
    parser.add_argument(
        "--ngrok-url",
        required=False,
        default="http://localhost:3000",
        type=str,
        help="ngrok public URL (e.g., https://abc123.ngrok.io) or localhost:3000",
    )
    parser.add_argument(
        "--scope",
        required=False,
        default="repo,user",
        type=str,
        help="OAuth scopes",
    )
    args = parser.parse_args()
    
    if args.revoke:
        success = revoke_token(args.client_id, args.client_secret, args.revoke)
        if not success:
            exit(1)
        return
    
    if not args.code and not args.refresh_token:
        redirect_uri = f"{args.ngrok_url}/callback"
        auth_url = generate_auth_url(args.client_id, redirect_uri, args.scope)
        print("No authorization code or refresh token provided.")
        print("\nVisit this URL to authorize:")
        print(auth_url)
        print(f"\nAfter clicking 'Authorize', copy the code from the redirect URL:")
        print(f"  {redirect_uri}?code=gho_xxxxx&state=...")
        print(f"\nThen run:")
        print(f"python create-oauth-token.py --client-id {args.client_id} --client-secret <secret> --code <code>")
        exit(1)
    
    if args.code:
        token_data = exchange_code_for_token(args.client_id, args.client_secret, args.code)
    else:
        token_data = refresh_access_token(args.client_id, args.client_secret, args.refresh_token)
    
    if token_data:
        print_token_info(token_data)
        print(f"\nJSON Output: {json.dumps(token_data, indent=2)}")
    else:
        print("Failed to obtain token")
        exit(1)


if __name__ == "__main__":
    main()
