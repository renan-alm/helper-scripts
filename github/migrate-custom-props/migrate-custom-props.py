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
import time
import warnings
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

import requests

# Suppress urllib3 SSL warnings on some systems
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from github import Github
from github.GithubException import GithubException
from github.OrganizationCustomProperty import OrganizationCustomProperty, CustomProperty

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
        source_icon = "🏢" if prop.source_type == "enterprise" else "🏛️"
        print(f"\n🏷️  Property: {prop.property_name}")
        print(f"   ├─ Type: {prop.value_type}")
        print(f"   ├─ Required: {prop.required}")
        print(f"   ├─ Default Value: {prop.default_value if prop.default_value else 'None'}")
        print(f"   ├─ Description: {prop.description if prop.description else 'N/A'}")
        print(f"   └─ Source: {source_icon} {prop.source_type}")
        
        if prop.allowed_values:
            print(f"      Allowed Values: {', '.join(prop.allowed_values)}")
    
    print("\n" + "=" * 60)
    print(f"📊 Total: {len(properties)} custom property(ies)")


def create_custom_properties(
    properties: List[OrganizationCustomProperty],
    target_org: str,
    token: str
) -> int:
    """
    Create custom properties in the target organization.
    
    Args:
        properties: List of OrganizationCustomProperty objects from source org
        target_org: Target GitHub organization name
        token: GitHub API token for target organization
        
    Returns:
        Number of properties created/updated
    """
    if not properties:
        print("📭 No org-level properties to create.")
        return 0
    
    try:
        g = get_github_client(token)
        organization = g.get_organization(target_org)
        
        # Convert OrganizationCustomProperty objects to CustomProperty objects
        custom_props = []
        for prop in properties:
            cp = CustomProperty(
                property_name=prop.property_name,
                value_type=prop.value_type,
                required=prop.required if prop.required is not None else False,
                default_value=prop.default_value if prop.default_value else None,
                description=prop.description if prop.description else None,
                allowed_values=prop.allowed_values if prop.allowed_values else None,
                values_editable_by=prop.values_editable_by if prop.values_editable_by else None,
            )
            custom_props.append(cp)
        
        print(f"\n⏳ Creating {len(custom_props)} custom property(ies) in '{target_org}'...")
        
        # Use batch creation for efficiency
        created_properties = organization.create_custom_properties(custom_props)
        
        print(f"\n✅ Successfully created/updated {len(created_properties)} custom property(ies):")
        for prop in created_properties:
            print(f"   ✓ {prop.property_name}")
        
        return len(created_properties)
        
    except GithubException as e:
        if e.status == 404:
            print(f"❌ Error: Organization '{target_org}' not found or no access", file=sys.stderr)
        elif e.status == 403:
            print(f"🔒 Error: Insufficient permissions to create custom properties in '{target_org}'", file=sys.stderr)
            print("   Required permission: organization_custom_properties=admin", file=sys.stderr)
        elif e.status == 422:
            print(f"⚠️  Error: Invalid property configuration", file=sys.stderr)
            print(f"   Response: {e.data}", file=sys.stderr)
        else:
            print(f"❌ Error: Failed to create custom properties. Status: {e.status}", file=sys.stderr)
            print(f"   Response: {e.data}", file=sys.stderr)
        sys.exit(1)


def create_enterprise_custom_properties(
    properties: List[OrganizationCustomProperty],
    enterprise_slug: str,
    token: str
) -> int:
    """
    Create custom properties at the enterprise level via REST API.
    
    PyGithub doesn't have enterprise custom property methods, so we use REST directly.
    
    Args:
        properties: List of OrganizationCustomProperty objects
        enterprise_slug: Target enterprise slug
        token: GitHub API token with enterprise admin access
        
    Returns:
        Number of properties created/updated
    """
    if not properties:
        print("📭 No enterprise properties to create.")
        return 0
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    # Build properties list for batch creation
    props_payload = []
    for prop in properties:
        prop_dict = {
            "property_name": prop.property_name,
            "value_type": prop.value_type,
        }
        if prop.required is not None:
            prop_dict["required"] = prop.required
        if prop.default_value:
            prop_dict["default_value"] = prop.default_value
        if prop.description:
            prop_dict["description"] = prop.description
        if prop.allowed_values:
            prop_dict["allowed_values"] = prop.allowed_values
        if prop.values_editable_by:
            prop_dict["values_editable_by"] = prop.values_editable_by
        props_payload.append(prop_dict)
    
    url = f"https://api.github.com/enterprises/{enterprise_slug}/properties/schema"
    payload = {"properties": props_payload}
    
    print(f"\n⏳ Creating {len(props_payload)} enterprise property(ies) in '{enterprise_slug}'...")
    
    try:
        response = requests.patch(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            created = response.json()
            print(f"\n✅ Successfully created/updated {len(created)} enterprise property(ies):")
            for prop in created:
                print(f"   ✓ {prop['property_name']}")
            return len(created)
        elif response.status_code == 404:
            print(f"❌ Error: Enterprise '{enterprise_slug}' not found or no access", file=sys.stderr)
            sys.exit(1)
        elif response.status_code == 403:
            print(f"🔒 Error: Insufficient permissions to create enterprise properties", file=sys.stderr)
            print("   Required: Enterprise admin access", file=sys.stderr)
            sys.exit(1)
        elif response.status_code == 422:
            print(f"⚠️  Error: Invalid property configuration", file=sys.stderr)
            print(f"   Response: {response.json()}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"❌ Error: Failed to create enterprise properties. Status: {response.status_code}", file=sys.stderr)
            print(f"   Response: {response.text}", file=sys.stderr)
            sys.exit(1)
            
    except requests.RequestException as e:
        print(f"❌ Error: Request failed: {e}", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# Rate Limit Handling
# =============================================================================

class RateLimitHandler:
    """
    Handles GitHub API rate limiting by tracking remaining requests
    and waiting when limits are reached.
    """
    
    def __init__(self, token: str):
        self.token = token
        self.remaining: int = 5000  # Default assumption
        self.reset_time: int = 0
        self.limit: int = 5000
    
    def update_from_headers(self, headers: Dict[str, str]) -> None:
        """Update rate limit info from response headers."""
        if 'X-RateLimit-Remaining' in headers:
            self.remaining = int(headers['X-RateLimit-Remaining'])
        if 'X-RateLimit-Reset' in headers:
            self.reset_time = int(headers['X-RateLimit-Reset'])
        if 'X-RateLimit-Limit' in headers:
            self.limit = int(headers['X-RateLimit-Limit'])
    
    def update_from_github(self, github_client: Github) -> None:
        """Update rate limit info from PyGithub client."""
        rate_limit = github_client.get_rate_limit()
        self.remaining = rate_limit.core.remaining
        self.reset_time = int(rate_limit.core.reset.timestamp())
        self.limit = rate_limit.core.limit
    
    def check_and_wait(self, min_remaining: int = 10) -> None:
        """
        Check if rate limit is approaching and wait if necessary.
        
        Args:
            min_remaining: Minimum requests to keep before waiting
        """
        if self.remaining <= min_remaining:
            wait_time = max(0, self.reset_time - int(time.time())) + 5  # Add 5s buffer
            if wait_time > 0:
                print(f"\n⏳ Rate limit reached ({self.remaining} remaining). Waiting {wait_time}s until reset...")
                time.sleep(wait_time)
                self.remaining = self.limit  # Assume reset happened
    
    def get_status(self) -> str:
        """Get a status string for the rate limit."""
        return f"{self.remaining}/{self.limit}"


def make_api_request(
    url: str,
    token: str,
    rate_handler: RateLimitHandler,
    method: str = "GET",
    payload: Optional[Dict] = None
) -> Tuple[int, Any, Dict[str, str]]:
    """
    Make an API request with rate limit handling.
    
    Args:
        url: API URL
        token: GitHub token
        rate_handler: RateLimitHandler instance
        method: HTTP method
        payload: Request payload for POST/PATCH
        
    Returns:
        Tuple of (status_code, response_data, headers)
    """
    rate_handler.check_and_wait()
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    if method == "GET":
        response = requests.get(url, headers=headers)
    elif method == "PATCH":
        response = requests.patch(url, headers=headers, json=payload)
    elif method == "POST":
        response = requests.post(url, headers=headers, json=payload)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")
    
    rate_handler.update_from_headers(dict(response.headers))
    
    try:
        data = response.json() if response.text else None
    except ValueError:
        data = response.text
    
    return response.status_code, data, dict(response.headers)


# =============================================================================
# Repository Property Sync Functions
# =============================================================================

class RepoPropertySync:
    """
    Handles synchronization of custom property values between repositories
    in source and target organizations.
    """
    
    def __init__(
        self,
        source_org: str,
        target_org: str,
        source_token: str,
        target_token: str,
        dry_run: bool = False
    ):
        self.source_org = source_org
        self.target_org = target_org
        self.source_token = source_token
        self.target_token = target_token
        self.dry_run = dry_run
        
        self.source_rate_handler = RateLimitHandler(source_token)
        self.target_rate_handler = RateLimitHandler(target_token)
        
        # Stats
        self.repos_processed = 0
        self.repos_synced = 0
        self.repos_skipped = 0
        self.repos_not_found = 0
    
    def get_source_repos_with_properties(self) -> List[Dict[str, Any]]:
        """
        Fetch all repositories from source org with their custom property values.
        
        Returns:
            List of dicts with repository_name and properties
        """
        print(f"\n⏳ Fetching repositories with property values from '{self.source_org}'...")
        
        all_repos = []
        page = 1
        per_page = 100
        
        while True:
            self.source_rate_handler.check_and_wait()
            
            url = f"https://api.github.com/orgs/{self.source_org}/properties/values"
            params = f"?per_page={per_page}&page={page}"
            
            status, data, headers = make_api_request(
                url + params,
                self.source_token,
                self.source_rate_handler
            )
            
            if status == 200:
                if not data:
                    break
                all_repos.extend(data)
                print(f"   📦 Fetched page {page} ({len(data)} repos, rate limit: {self.source_rate_handler.get_status()})")
                if len(data) < per_page:
                    break
                page += 1
            elif status == 404:
                print(f"❌ Error: Organization '{self.source_org}' not found or no access", file=sys.stderr)
                sys.exit(1)
            elif status == 403:
                print(f"🔒 Error: Insufficient permissions to read property values from '{self.source_org}'", file=sys.stderr)
                sys.exit(1)
            else:
                print(f"❌ Error: Failed to fetch repositories. Status: {status}", file=sys.stderr)
                print(f"   Response: {data}", file=sys.stderr)
                sys.exit(1)
        
        print(f"   ✅ Total: {len(all_repos)} repositories with property values")
        return all_repos
    
    def check_repo_exists_in_target(self, repo_name: str) -> bool:
        """
        Check if a repository exists in the target organization.
        
        Args:
            repo_name: Repository name
            
        Returns:
            True if exists, False otherwise
        """
        self.target_rate_handler.check_and_wait()
        
        url = f"https://api.github.com/repos/{self.target_org}/{repo_name}"
        status, _, headers = make_api_request(url, self.target_token, self.target_rate_handler)
        
        return status == 200
    
    def update_repo_properties(
        self,
        repo_name: str,
        properties: Dict[str, Any]
    ) -> bool:
        """
        Update custom property values for a repository in target org.
        
        Args:
            repo_name: Repository name
            properties: Dict of property_name -> value
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            return True
        
        self.target_rate_handler.check_and_wait()
        
        url = f"https://api.github.com/repos/{self.target_org}/{repo_name}/properties/values"
        payload = {
            "properties": [
                {"property_name": k, "value": v}
                for k, v in properties.items()
            ]
        }
        
        status, data, headers = make_api_request(
            url, self.target_token, self.target_rate_handler,
            method="PATCH", payload=payload
        )
        
        if status in [200, 204]:
            return True
        elif status == 404:
            # Property might not exist in target
            return False
        elif status == 422:
            print(f"      ⚠️  Invalid property value for {repo_name}: {data}")
            return False
        else:
            print(f"      ❌ Failed to update {repo_name}: {status} - {data}")
            return False
    
    def sync_repositories(self) -> Dict[str, int]:
        """
        Synchronize repository property values from source to target org.
        
        Returns:
            Dict with sync statistics
        """
        source_repos = self.get_source_repos_with_properties()
        
        if not source_repos:
            print("📭 No repositories with property values found in source org.")
            return self._get_stats()
        
        mode = "🔍 [DRY-RUN] " if self.dry_run else ""
        print(f"\n{mode}🔄 Syncing repository property values to '{self.target_org}'...")
        print("=" * 60)
        
        total_repos = len(source_repos)
        check_count = 0  # Track all repos checked (including skipped)
        
        for repo_data in source_repos:
            repo_name = repo_data.get("repository_name")
            properties_list = repo_data.get("properties", [])
            
            # Convert list of {property_name, value} to dict
            properties = {
                p["property_name"]: p["value"]
                for p in properties_list
                if p.get("value") is not None
            }
            
            check_count += 1
            
            # Show progress every 25 repos (inline, overwriting previous)
            if check_count % 25 == 0:
                pct = int((check_count / total_repos) * 100)
                print(f"\r   ⏳ Checking repos... {check_count}/{total_repos} ({pct}%) ", end="", flush=True)
            
            if not properties:
                self.repos_skipped += 1
                continue
            
            self.repos_processed += 1
            
            # Check if repo exists in target
            if not self.check_repo_exists_in_target(repo_name):
                self.repos_not_found += 1
                if self.repos_not_found <= 5:  # Only show first 5
                    print(f"\r   ⏭️  {repo_name} (not found in target)                    ")
                elif self.repos_not_found == 6:
                    print(f"\r   ... (hiding remaining 'not found' messages)              ")
                continue
            
            # Clear the progress line before showing match
            print("\r" + " " * 60 + "\r", end="")
            
            # Update properties
            if self.dry_run:
                print(f"   → {repo_name}: {len(properties)} property(ies)")
                self.repos_synced += 1
            else:
                if self.update_repo_properties(repo_name, properties):
                    print(f"   ✓ {repo_name}: {len(properties)} property(ies)")
                    self.repos_synced += 1
                else:
                    print(f"   ✗ {repo_name}: sync failed")
            
            # Detailed progress indicator every 50 processed repos
            if self.repos_processed % 50 == 0:
                print(f"\n   📊 Progress: {check_count}/{total_repos} checked, {self.repos_synced} synced " +
                      f"(rate limit: src={self.source_rate_handler.get_status()}, " +
                      f"tgt={self.target_rate_handler.get_status()})\n")
        
        # Clear any remaining progress indicator
        print("\r" + " " * 60 + "\r", end="")
        
        return self._get_stats()
    
    def _get_stats(self) -> Dict[str, int]:
        """Get sync statistics."""
        return {
            "processed": self.repos_processed,
            "synced": self.repos_synced,
            "skipped": self.repos_skipped,
            "not_found": self.repos_not_found,
        }
    
    def print_summary(self) -> None:
        """Print sync summary."""
        mode = "🔍 [DRY-RUN] " if self.dry_run else ""
        print(f"\n{mode}📊 Repository Sync Summary:")
        print("=" * 60)
        print(f"   📦 Repositories processed: {self.repos_processed}")
        print(f"   ✅ Repositories synced: {self.repos_synced}")
        print(f"   ⏭️  Repositories skipped (no properties): {self.repos_skipped}")
        print(f"   ❓ Repositories not found in target: {self.repos_not_found}")


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
    
    # Include enterprise-level properties (requires enterprise admin access)
    python migrate-custom-props.py --source-org src-org --target-org tgt-org --target-enterprise my-enterprise
    
    # Sync repository property values (only repos that exist in both orgs)
    python migrate-custom-props.py --source-org src-org --target-org tgt-org --sync-repos
    
    # Full migration: properties + repository values
    python migrate-custom-props.py --source-org src-org --target-org tgt-org --sync-repos --target-enterprise my-enterprise
    
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
    
    parser.add_argument(
        "--target-enterprise",
        required=False,
        default=os.environ.get("TARGET_ENTERPRISE"),
        help="Target enterprise slug for migrating enterprise-level properties"
    )
    
    parser.add_argument(
        "--sync-repos",
        action="store_true",
        default=False,
        help="Sync repository property values from source to target org (only for repos that exist in both)"
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
    if args.target_enterprise:
        print(f"🏢 Target Enterprise: {args.target_enterprise}")
    print(f"🔍 Dry Run: {args.dry_run}")
    print(f"🔄 Sync Repos: {args.sync_repos}")
    print(f"🔑 Source PAT: {'provided' if args.source_pat else 'using GITHUB_TOKEN'}")
    print(f"🔑 Target PAT: {'provided' if args.target_pat else 'using GITHUB_TOKEN'}")
    
    # Read custom properties from source organization
    print(f"\n⏳ Fetching custom properties from '{args.source_org}'...")
    properties = get_custom_properties(args.source_org, source_token)
    
    # Print properties
    print_properties(properties, args.source_org, args.dry_run)
    
    if args.dry_run:
        if properties:
            org_properties = [p for p in properties if p.source_type != "enterprise"]
            enterprise_properties = [p for p in properties if p.source_type == "enterprise"]
            
            if enterprise_properties:
                if args.target_enterprise:
                    print(f"\n🏢 [DRY-RUN] Would create {len(enterprise_properties)} enterprise property(ies) in '{args.target_enterprise}':")
                    for prop in enterprise_properties:
                        print(f"   → {prop.property_name} ({prop.value_type})")
                else:
                    print(f"\n⚠️  [DRY-RUN] Would skip {len(enterprise_properties)} enterprise-level property(ies):")
                    for prop in enterprise_properties:
                        print(f"   ⏭️  {prop.property_name}")
                    print(f"\n💡 Tip: Use --target-enterprise <slug> to migrate these")
            
            if org_properties:
                print(f"\n🔮 [DRY-RUN] Would create {len(org_properties)} org-level property(ies) in '{args.target_org}':")
                for prop in org_properties:
                    print(f"   → {prop.property_name} ({prop.value_type})")
            else:
                print(f"\n📭 [DRY-RUN] No organization-level properties to create.")
        
        # Dry-run repo sync
        if args.sync_repos:
            repo_sync = RepoPropertySync(
                args.source_org, args.target_org,
                source_token, target_token,
                dry_run=True
            )
            repo_sync.sync_repositories()
            repo_sync.print_summary()
        
        print("\n✅ [DRY-RUN] No changes were made.")
    else:
        org_properties = [p for p in properties if p.source_type != "enterprise"]
        enterprise_properties = [p for p in properties if p.source_type == "enterprise"]
        
        total_created = 0
        
        # Handle enterprise properties
        if enterprise_properties:
            if args.target_enterprise:
                enterprise_count = create_enterprise_custom_properties(
                    enterprise_properties, args.target_enterprise, target_token
                )
                total_created += enterprise_count
            else:
                print(f"\n⚠️  Skipping {len(enterprise_properties)} enterprise-level property(ies):")
                for prop in enterprise_properties:
                    print(f"   ⏭️  {prop.property_name}")
                print(f"\n💡 Tip: Use --target-enterprise <slug> to migrate these")
        
        # Handle organization properties
        if org_properties:
            org_count = create_custom_properties(org_properties, args.target_org, target_token)
            total_created += org_count
        
        print(f"\n✅ Property schema migration complete! {total_created} property(ies) migrated.")
        
        # Sync repository property values
        if args.sync_repos:
            repo_sync = RepoPropertySync(
                args.source_org, args.target_org,
                source_token, target_token,
                dry_run=False
            )
            repo_sync.sync_repositories()
            repo_sync.print_summary()
        
        print(f"\n🎉 Migration complete!")


if __name__ == "__main__":
    main()
