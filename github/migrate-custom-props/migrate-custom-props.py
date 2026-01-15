#!/usr/bin/env python3
"""
Migrate GitHub Organization Custom Properties from source to target organization.

This script reads custom properties from a source GitHub organization
and can create them in a target organization.

Usage:
    python migrate-custom-props.py --source-org SOURCE --target-org TARGET [--dry-run]

Requirements:
    - PyGithub
    - python-dotenv (optional, for .env file support)

Configuration (in order of precedence):
    1. CLI arguments
    2. .env.local file (in script directory)
    3. Environment variables
"""

import argparse
import os
import sys
import warnings
from pathlib import Path
from typing import Optional, List

# Suppress urllib3 SSL warnings on some systems
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from github import Github
from github.GithubException import GithubException
from github.OrganizationCustomProperty import OrganizationCustomProperty

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


def load_env_file() -> None:
    """
    Load environment variables from .env.local file if python-dotenv is available.
    The .env.local file is expected to be in the same directory as this script.
    """
    env_file = Path(__file__).parent / ".env.local"
    
    if not env_file.exists():
        return
    
    if DOTENV_AVAILABLE:
        load_dotenv(env_file, override=False)  # Don't override existing env vars
    else:
        # Manual .env parsing as fallback
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    # Only set if not already in environment
                    if key and value and key not in os.environ:
                        os.environ[key] = value


def get_token(token_arg: Optional[str], env_var: str = "GITHUB_TOKEN") -> str:
    """
    Get GitHub token from argument or environment variable.
    
    Args:
        token_arg: Token passed via command line argument (takes precedence)
        env_var: Environment variable name to use as fallback
        
    Returns:
        GitHub token string
    """
    if token_arg:
        return token_arg
    
    token = os.environ.get(env_var)
    if not token:
        print(f"❌ Error: No token provided and {env_var} environment variable is not set", file=sys.stderr)
        sys.exit(1)
    return token


def get_github_client(token: str) -> Github:
    """
    Create a GitHub client instance.
    
    Args:
        token: GitHub API token
        
    Returns:
        Github client instance
    """
    return Github(token)


def get_custom_properties(org: str, token: str) -> List[OrganizationCustomProperty]:
    """
    Fetch all custom properties from a GitHub organization.
    
    Args:
        org: GitHub organization name
        token: GitHub API token
        
    Returns:
        List of OrganizationCustomProperty objects
    """
    try:
        g = get_github_client(token)
        organization = g.get_organization(org)
        properties = list(organization.get_custom_properties())
        return properties
    except GithubException as e:
        if e.status == 404:
            print(f"❌ Error: Organization '{org}' not found or no access", file=sys.stderr)
        elif e.status == 403:
            print(f"🔒 Error: Insufficient permissions to read custom properties from '{org}'", file=sys.stderr)
        else:
            print(f"❌ Error: Failed to fetch custom properties. Status: {e.status}", file=sys.stderr)
            print(f"Response: {e.data}", file=sys.stderr)
        sys.exit(1)


def print_properties(properties: List[OrganizationCustomProperty], org: str, dry_run: bool = False) -> None:
    """
    Print custom properties in a readable format.
    
    Args:
        properties: List of OrganizationCustomProperty objects
        org: Organization name (for display)
        dry_run: Whether this is a dry-run
    """
    mode = "🔍 [DRY-RUN] " if dry_run else ""
    
    print(f"\n{mode}📋 Custom Properties from '{org}':")
    print("=" * 60)
    
    if not properties:
        print("📭 No custom properties found.")
        return
    
    for prop in properties:
        print(f"\n🏷️  Property: {prop.property_name}")
        print(f"   ├─ Type: {prop.value_type}")
        print(f"   ├─ Required: {prop.required}")
        print(f"   ├─ Default Value: {prop.default_value if prop.default_value else 'None'}")
        print(f"   └─ Description: {prop.description if prop.description else 'N/A'}")
        
        if prop.allowed_values:
            print(f"      Allowed Values: {', '.join(prop.allowed_values)}")
    
    print("\n" + "=" * 60)
    print(f"📊 Total: {len(properties)} custom property(ies)")


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Values can come from (in order of precedence):
    1. CLI arguments
    2. .env.local file
    3. Environment variables
    """
    # Load .env file first so env vars are available for defaults
    load_env_file()
    
    parser = argparse.ArgumentParser(
        description="Migrate GitHub Organization Custom Properties",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Dry-run to see what properties would be migrated (uses GITHUB_TOKEN)
    python migrate-custom-props.py --source-org my-source-org --target-org my-target-org --dry-run
    
    # Use different PATs for source and target organizations
    python migrate-custom-props.py --source-org src-org --target-org tgt-org --source-pat ghp_xxx --target-pat ghp_yyy
    
    # Use values from .env.local file (copy .env.example to .env.local)
    python migrate-custom-props.py --dry-run

Configuration (in order of precedence):
    1. CLI arguments
    2. .env.local file (in script directory)
    3. Environment variables (GITHUB_TOKEN, SOURCE_ORG, TARGET_ORG, SOURCE_PAT, TARGET_PAT)
        """
    )
    
    parser.add_argument(
        "--source-org", "-s",
        required=False,
        default=os.environ.get("SOURCE_ORG"),
        help="Source GitHub organization to read custom properties from"
    )
    
    parser.add_argument(
        "--target-org", "-t",
        required=False,
        default=os.environ.get("TARGET_ORG"),
        help="Target GitHub organization to create custom properties in"
    )
    
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        default=False,
        help="Only read and display properties without making changes"
    )
    
    parser.add_argument(
        "--source-pat",
        required=False,
        default=os.environ.get("SOURCE_PAT"),
        help="GitHub PAT for source organization (falls back to GITHUB_TOKEN)"
    )
    
    parser.add_argument(
        "--target-pat",
        required=False,
        default=os.environ.get("TARGET_PAT"),
        help="GitHub PAT for target organization (falls back to GITHUB_TOKEN)"
    )
    
    args = parser.parse_args()
    
    # Validate required arguments
    if not args.source_org:
        parser.error("--source-org is required (or set SOURCE_ORG in .env.local/environment)")
    if not args.target_org:
        parser.error("--target-org is required (or set TARGET_ORG in .env.local/environment)")
    
    return args


def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    source_token = get_token(args.source_pat)
    target_token = get_token(args.target_pat)
    
    print(f"\n🚀 GitHub Custom Properties Migration")
    print("=" * 60)
    print(f"📤 Source Organization: {args.source_org}")
    print(f"📥 Target Organization: {args.target_org}")
    print(f"🔍 Dry Run: {args.dry_run}")
    print(f"🔑 Source PAT: {'provided' if args.source_pat else 'using GITHUB_TOKEN'}")
    print(f"🔑 Target PAT: {'provided' if args.target_pat else 'using GITHUB_TOKEN'}")
    
    # Read custom properties from source organization
    print(f"\n⏳ Fetching custom properties from '{args.source_org}'...")
    properties = get_custom_properties(args.source_org, source_token)
    
    # Print properties
    print_properties(properties, args.source_org, args.dry_run)
    
    if args.dry_run:
        print("\n✅ [DRY-RUN] No changes were made to the target organization.")
    else:
        # TODO: Implement creating properties in target org
        # TODO: Implement reading repos and populating values
        print("\nℹ️  [INFO] Property creation not implemented yet. Use --dry-run to preview.")


if __name__ == "__main__":
    main()
