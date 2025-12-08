#!/usr/bin/env python3
"""
GitHub Management CLI

A command-line tool to interact with GitHub organizations and extract user information.
"""

import argparse
from datetime import datetime
import json
import os
import sys
import requests
from typing import List, Dict, Any, Optional, Set, Tuple


class GitHubClient:
    """GitHub API client for organization operations."""
    
    def __init__(self, token: str):
        """Initialize GitHub client with authentication token."""
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "gh-management-cli/1.0"
        }
        self.rate_limit_remaining = None
        self.org_members_cache = {}  # Cache for organization members
    
    def _paginated_request(self, url: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Make a paginated request to the GitHub API.
        
        Args:
            url: API endpoint URL
            params: Additional query parameters
            
        Returns:
            List of result items
            
        Raises:
            requests.RequestException: If API request fails
        """
        if params is None:
            params = {}
            
        results = []
        page = params.get("page", 1)
        per_page = params.get("per_page", 100)
        
        while True:
            # Update pagination parameters
            params.update({
                "page": page,
                "per_page": per_page
            })
            
            try:
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                # Update rate limit information
                self.rate_limit_remaining = int(response.headers.get("X-RateLimit-Remaining", -1))
                
                page_items = response.json()
                
                # If no more items, break the loop
                if not page_items:
                    break
                
                results.extend(page_items)
                page += 1
                
            except requests.RequestException as e:
                status_code = getattr(response, "status_code", None)
                
                if status_code == 404:
                    raise requests.RequestException(f"Resource not found or not accessible: {url}")
                elif status_code == 401:
                    raise requests.RequestException("Authentication failed. Please check your GITHUB_TOKEN")
                elif status_code == 403:
                    if self.rate_limit_remaining == 0:
                        raise requests.RequestException("API rate limit exceeded. Please try again later.")
                    else:
                        raise requests.RequestException("Access forbidden. You may not have sufficient permissions")
                else:
                    raise requests.RequestException(f"API request failed: {e}")
        
        return results
    
    def get_org_members(self, org: str, role: str = "all") -> List[Dict[str, Any]]:
        """
        Get all members of a GitHub organization.
        
        Args:
            org: Organization name
            role: Membership role filter ('all', 'admin', 'member')
            
        Returns:
            List of member dictionaries containing user information
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/orgs/{org}/members"
        params = {"role": role}
        
        try:
            return self._paginated_request(url, params)
        except requests.RequestException as e:
            if "404" in str(e):
                raise requests.RequestException(f"Organization '{org}' not found or not accessible")
            raise e
    
    def get_org_teams(self, org: str) -> List[Dict[str, Any]]:
        """
        Get all teams of a GitHub organization.
        
        Args:
            org: Organization name
            
        Returns:
            List of team dictionaries containing team information
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/orgs/{org}/teams"
        
        try:
            return self._paginated_request(url)
        except requests.RequestException as e:
            if "404" in str(e):
                raise requests.RequestException(f"Organization '{org}' not found or not accessible")
            raise e
    
    def get_team_members(self, team_slug: str, org: str, role: str = "all") -> List[Dict[str, Any]]:
        """
        Get all members of a specific GitHub team.
        
        Args:
            team_slug: Team slug (URL-friendly name)
            org: Organization name
            role: Membership role filter ('all', 'maintainer', 'member')
            
        Returns:
            List of member dictionaries containing user information
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/orgs/{org}/teams/{team_slug}/members"
        params = {"role": role}
        
        try:
            return self._paginated_request(url, params)
        except requests.RequestException as e:
            if "404" in str(e):
                raise requests.RequestException(f"Team '{team_slug}' not found or not accessible in organization '{org}'")
            raise e
    
    def get_user_details(self, username: str) -> Dict[str, Any]:
        """
        Get detailed information about a GitHub user.
        
        Args:
            username: GitHub username
            
        Returns:
            Dictionary containing user details
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/users/{username}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            # Update rate limit information
            self.rate_limit_remaining = int(response.headers.get("X-RateLimit-Remaining", -1))
            
            return response.json()
            
        except requests.RequestException as e:
            status_code = getattr(response, "status_code", None)
            
            if status_code == 404:
                raise requests.RequestException(f"User '{username}' not found")
            elif status_code == 401:
                raise requests.RequestException("Authentication failed. Please check your GITHUB_TOKEN")
            elif status_code == 403:
                if self.rate_limit_remaining == 0:
                    raise requests.RequestException("API rate limit exceeded. Please try again later.")
                else:
                    raise requests.RequestException("Access forbidden. You may not have sufficient permissions")
            else:
                raise requests.RequestException(f"API request failed: {e}")
    
    def invite_user_to_org(self, org: str, username: str) -> Dict[str, Any]:
        """
        Invite a user to join a GitHub organization.
        
        Args:
            org: Organization name
            username: GitHub username to invite
            
        Returns:
            Response data from the GitHub API
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/orgs/{org}/memberships/{username}"
        
        try:
            response = requests.put(url, headers=self.headers, json={"role": "member"})
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if getattr(response, "status_code", None) == 404:
                raise requests.RequestException(f"Organization '{org}' or user '{username}' not found")
            elif getattr(response, "status_code", None) == 401:
                raise requests.RequestException("Authentication failed. Check your GITHUB_TOKEN")
            elif getattr(response, "status_code", None) == 403:
                raise requests.RequestException("Access forbidden. Your token may not have admin permissions")
            else:
                raise requests.RequestException(f"Failed to invite user: {e}")
    
    def extract_user_handles(self, users: List[Dict[str, Any]]) -> List[str]:
        """Extract usernames from a list of user dictionaries."""
        return [user.get("login") for user in users if user.get("login")]
    
    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Get current rate limit information.
        
        Returns:
            Dictionary with rate limit details
        
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/rate_limit"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to fetch rate limit information: {e}")
            
    def create_team(self, org: str, name: str, description: str = None, privacy: str = "closed",
                   parent_team_id: int = None) -> Dict[str, Any]:
        """
        Create a new team in the GitHub organization.
        
        Args:
            org: Organization name
            name: Team name
            description: Team description (optional)
            privacy: Team privacy setting ('secret' or 'closed')
            parent_team_id: ID of parent team (optional)
            
        Returns:
            Team data returned from GitHub API
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/orgs/{org}/teams"
        
        # Prepare request payload
        payload = {
            "name": name,
            "privacy": privacy
        }
        
        if description:
            payload["description"] = description
            
        if parent_team_id:
            payload["parent_team_id"] = parent_team_id
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            status_code = getattr(response, "status_code", None)
            
            if status_code == 422:
                # Team already exists, try to get it
                return self.get_team_by_name(org, name)
            elif status_code == 404:
                raise requests.RequestException(f"Organization '{org}' not found or not accessible")
            elif status_code == 401:
                raise requests.RequestException("Authentication failed. Please check your GITHUB_TOKEN")
            elif status_code == 403:
                raise requests.RequestException("Access forbidden. Your token may not have admin permissions")
            else:
                raise requests.RequestException(f"Failed to create team: {e}")
    
    def get_team_by_name(self, org: str, team_name: str) -> Dict[str, Any]:
        """
        Get team details by team name (finds the team by name/slug).
        
        Args:
            org: Organization name
            team_name: Team name to look for
            
        Returns:
            Team data
            
        Raises:
            requests.RequestException: If API request fails
            ValueError: If team not found
        """
        # Try with slug directly (team_name converted to slug format)
        team_slug = team_name.lower().replace(" ", "-")
        
        try:
            url = f"{self.base_url}/orgs/{org}/teams/{team_slug}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
        except:
            pass
        
        # If that didn't work, list all teams and find the right one
        url = f"{self.base_url}/orgs/{org}/teams"
        
        try:
            all_teams = []
            page = 1
            
            while True:
                params = {"per_page": 100, "page": page}
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                teams_page = response.json()
                if not teams_page:
                    break
                    
                all_teams.extend(teams_page)
                page += 1
                
            # Find the team with matching name
            for team in all_teams:
                if team["name"].lower() == team_name.lower() or team["slug"].lower() == team_slug.lower():
                    return team
                    
            raise ValueError(f"Team '{team_name}' not found in organization '{org}'")
            
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to get team: {e}")
    
    def add_team_member(self, team_id: int, org: str, username: str, role: str = "member") -> bool:
        """
        Add a member to a team.
        
        Args:
            team_id: Team ID
            org: Organization name (needed for error reporting)
            username: GitHub username to add
            role: Membership role ('member' or 'maintainer')
            
        Returns:
            True if successful, False if user is already a member
            
        Raises:
            requests.RequestException: If API request fails
        """
        url = f"{self.base_url}/teams/{team_id}/memberships/{username}"
        
        try:
            response = requests.put(url, headers=self.headers, json={"role": role})
            response.raise_for_status()
            
            state = response.json().get("state")
            return state == "active" or state == "pending"
            
        except requests.RequestException as e:
            status_code = getattr(response, "status_code", None)
            
            if status_code == 404:
                raise requests.RequestException(f"Team ID {team_id} or user '{username}' not found")
            elif status_code == 403:
                raise requests.RequestException("Access forbidden. Your token may not have admin permissions")
            else:
                raise requests.RequestException(f"Failed to add member to team: {e}")
                
    def get_org_members_set(self, org: str, force_refresh: bool = False) -> Set[str]:
        """
        Get all members of an organization as a set of usernames.
        Uses caching for efficiency.
        
        Args:
            org: Organization name
            force_refresh: Whether to force a refresh of the cache
            
        Returns:
            Set of member usernames
            
        Raises:
            requests.RequestException: If API request fails
        """
        # Use cached results if available
        if not force_refresh and org in self.org_members_cache:
            return self.org_members_cache[org]
        
        # Get all members and convert to a set of usernames
        members = self.get_org_members(org)
        member_usernames = {member["login"] for member in members if member.get("login")}
        
        # Cache the results
        self.org_members_cache[org] = member_usernames
        
        return member_usernames


def validate_token() -> str:
    """
    Validate GitHub token from environment variable.
    
    Returns:
        The GitHub token
        
    Raises:
        ValueError: If token is not set or invalid
    """
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set. Please set it before running this script.")
    
    return token


def generate_filename(prefix: str) -> str:
    """
    Generate a filename with timestamp.
    
    Args:
        prefix: Filename prefix
        
    Returns:
        Generated filename
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"{prefix}-{timestamp}.json"


def save_to_json(data: Any, filename: str) -> None:
    """
    Save data to JSON file with pretty formatting.
    
    Args:
        data: Data to save
        filename: Output filename
    """
    with open(filename, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"📄 Output saved to: {filename}")


def load_users_from_json(json_file: str) -> List[str]:
    """
    Load user handles from a JSON file.
    
    Args:
        json_file: Path to the JSON file
        
    Returns:
        List of user handles
        
    Raises:
        Exception: If file can't be read or doesn't contain expected format
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both formats: direct list or object with user_handles key
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "user_handles" in data:
            return data.get("user_handles", [])
        elif isinstance(data, dict) and "users" in data:
            # Extract login fields from users array
            users = data.get("users", [])
            return [user.get("login") for user in users if user.get("login")]
        else:
            raise ValueError("Invalid JSON format: Expected a list of users or an object with 'user_handles' or 'users' key")
            
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON file: {json_file}")
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {json_file}")
    except Exception as e:
        raise Exception(f"Error loading JSON file: {e}")


def load_teams_from_json(json_file: str) -> Dict[str, Any]:
    """
    Load teams data from a JSON file.
    
    Args:
        json_file: Path to the JSON file
        
    Returns:
        Dictionary containing teams data
        
    Raises:
        Exception: If file can't be read or doesn't contain valid teams data
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate that this is a teams export file
        if not isinstance(data, dict) or "teams" not in data or "organization" not in data:
            raise ValueError("Invalid JSON format: Expected an object with 'teams' and 'organization' keys")
            
        return data
            
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON file: {json_file}")
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {json_file}")
    except Exception as e:
        raise Exception(f"Error loading JSON file: {e}")


def display_rate_limit(client: GitHubClient, verbose: bool = False) -> None:
    """
    Display rate limit information.
    
    Args:
        client: GitHub client instance
        verbose: Whether to show detailed information
    """
    try:
        rate_info = client.get_rate_limit_info()
        core_rate = rate_info.get("resources", {}).get("core", {})
        
        remaining = core_rate.get("remaining", 0)
        limit = core_rate.get("limit", 0)
        reset_time = datetime.fromtimestamp(core_rate.get("reset", 0))
        
        print(f"📊 API Rate Limit: {remaining}/{limit} remaining")
        if verbose:
            print(f"⏰ Rate limit resets at: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"⚠️ Could not fetch rate limit information: {e}")


def create_parent_child_teams(client: GitHubClient, org: str, teams_data: List[Dict[str, Any]], 
                            verbose: bool = False) -> Dict[str, int]:
    """
    Create teams with proper parent-child relationships.
    
    Args:
        client: GitHubClient instance
        org: Organization name
        teams_data: List of teams from the JSON file
        verbose: Whether to show detailed output
        
    Returns:
        Dictionary mapping team names to their IDs
    """
    # First, create a mapping of team names to their data
    team_map = {team['name']: team for team in teams_data}
    
    # Then, create a mapping of created team names to their IDs
    team_id_map = {}
    
    # Track teams with parents to process in a second pass
    teams_with_parents = []
    
    # First pass: Create teams without parents
    if verbose:
        print(f"👥 Creating teams in organization: {org}")
        
    for team_data in teams_data:
        team_name = team_data['name']
        parent_name = team_data.get('parent')
        
        if parent_name:
            # Save for second pass
            teams_with_parents.append(team_data)
            continue
            
        # Create the team without a parent
        try:
            if verbose:
                print(f"  🛠️ Creating team: {team_name}")
                
            team = client.create_team(
                org=org,
                name=team_name,
                description=team_data.get('description', ''),
                privacy=team_data.get('privacy', 'closed')
            )
            
            team_id_map[team_name] = team['id']
            
            if verbose:
                print(f"  ✅ Team created with ID: {team['id']}")
                
        except Exception as e:
            print(f"  ❌ Error creating team '{team_name}': {e}")
    
    # Second pass: Create teams with parents
    if teams_with_parents and verbose:
        print(f"👥 Creating teams with parent relationships...")
        
    for team_data in teams_with_parents:
        team_name = team_data['name']
        parent_name = team_data.get('parent')
        
        # Skip if we already created this team somehow
        if team_name in team_id_map:
            continue
            
        # Make sure parent team exists
        if parent_name not in team_id_map:
            print(f"  ⚠️ Parent team '{parent_name}' for '{team_name}' not found or not created yet. Creating without parent.")
            parent_team_id = None
        else:
            parent_team_id = team_id_map[parent_name]
        
        # Create the team with parent relationship
        try:
            if verbose:
                if parent_team_id:
                    print(f"  🛠️ Creating team: {team_name} (parent: {parent_name})")
                else:
                    print(f"  🛠️ Creating team: {team_name}")
                
            team = client.create_team(
                org=org,
                name=team_name,
                description=team_data.get('description', ''),
                privacy=team_data.get('privacy', 'closed'),
                parent_team_id=parent_team_id
            )
            
            team_id_map[team_name] = team['id']
            
            if verbose:
                print(f"  ✅ Team created with ID: {team['id']}")
                
        except Exception as e:
            print(f"  ❌ Error creating team '{team_name}': {e}")
    
    return team_id_map


def add_members_to_teams(client: GitHubClient, org: str, teams_data: List[Dict[str, Any]], 
                       team_id_map: Dict[str, int], dry_run: bool = False, 
                       verbose: bool = False) -> Tuple[int, int, int]:
    """
    Add members to teams.
    
    Args:
        client: GitHubClient instance
        org: Organization name
        teams_data: List of teams from the JSON file
        team_id_map: Mapping of team names to their IDs
        dry_run: Whether to skip actually adding members
        verbose: Whether to show detailed output
        
    Returns:
        Tuple of (success_count, not_org_member_count, failure_count)
    """
    # Get all organization members for checking membership
    try:
        org_members = client.get_org_members_set(org)
        if verbose:
            print(f"  ℹ️ Found {len(org_members)} members in organization '{org}'")
    except Exception as e:
        print(f"❌ Error getting organization members: {e}")
        return 0, 0, 0
    
    success_count = 0
    not_org_member_count = 0
    failure_count = 0
    
    # For logging: keep track of users not in organization
    non_org_users = set()
    
    if verbose:
        print(f"👤 Adding members to teams...")
    
    # Process each team
    for team_data in teams_data:
        team_name = team_data['name']
        
        # Skip if team wasn't created successfully
        if team_name not in team_id_map:
            if verbose:
                print(f"  ⚠️ Skipping members for team '{team_name}' as it was not created successfully")
            continue
            
        team_id = team_id_map[team_name]
        members = team_data.get('members', [])
        
        if verbose:
            print(f"  👥 Adding {len(members)} members to team: {team_name}")
        
        # Add each member
        for username in members:
            # Check if user is an organization member
            if username not in org_members:
                if verbose:
                    print(f"    ⚠️ User '{username}' is not a member of organization '{org}'")
                not_org_member_count += 1
                non_org_users.add(username)
                continue
            
            # Skip actually adding in dry run mode
            if dry_run:
                if verbose:
                    print(f"    🔍 [DRY RUN] Would add user '{username}' to team '{team_name}'")
                success_count += 1
                continue
                
            # Add the member to the team
            try:
                if verbose:
                    print(f"    🛠️ Adding user '{username}' to team '{team_name}'")
                    
                client.add_team_member(team_id, org, username)
                success_count += 1
                
                if verbose:
                    print(f"    ✅ User '{username}' added to team")
                    
            except Exception as e:
                if verbose:
                    print(f"    ❌ Error adding user '{username}' to team: {e}")
                failure_count += 1
    
    # Print summary of users not in organization
    if non_org_users and verbose:
        print(f"\n⚠️ Users not in organization '{org}':")
        for username in sorted(non_org_users):
            print(f"   - {username}")
        print(f"   Total: {len(non_org_users)} users\n")
        
    return success_count, not_org_member_count, failure_count


def main() -> None:
    """Main function to execute CLI commands."""
    # Create argument parser
    parser = argparse.ArgumentParser(
        description="GitHub Management CLI - A tool to interact with GitHub organizations and extract user information",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Add subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Create 'users' command parser
    users_parser = subparsers.add_parser("users", help="Fetch and export organization users")
    users_parser.add_argument("org", help="GitHub organization name")
    users_parser.add_argument("-o", "--output", help="Output JSON file (default: users-YYYYMMDD-HHMM.json)")
    users_parser.add_argument("-f", "--full", action="store_true", help="Fetch full user details (email, name, etc.)")
    users_parser.add_argument("-r", "--role", choices=["all", "admin", "member"], default="all",
                             help="Filter users by role (default: all)")
    users_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    users_parser.add_argument("--rate-limit", action="store_true", help="Display rate limit information")
    
    # Create 'teams' command parser
    teams_parser = subparsers.add_parser("teams", help="Fetch and export organization teams")
    teams_parser.add_argument("org", help="GitHub organization name")
    teams_parser.add_argument("-o", "--output", help="Teams output JSON file (default: teams-YYYYMMDD-HHMM.json)")
    teams_parser.add_argument("-r", "--role", choices=["all", "maintainer", "member"], default="all",
                             help="Filter team members by role (default: all)")
    teams_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    teams_parser.add_argument("--rate-limit", action="store_true", help="Display rate limit information")
    
    # Create 'invite' command parser
    invite_parser = subparsers.add_parser("invite", help="Invite users to organization")
    invite_parser.add_argument("org", help="GitHub organization name")
    invite_parser.add_argument("file", help="JSON file with user handles to invite")
    invite_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    invite_parser.add_argument("--rate-limit", action="store_true", help="Display rate limit information")
    
    # Create 'recreate-teams' command parser
    recreate_teams_parser = subparsers.add_parser("recreate-teams", help="Recreate teams from a JSON export file")
    recreate_teams_parser.add_argument("file", help="Path to the JSON file containing teams data (exported from teams command)")
    recreate_teams_parser.add_argument("-o", "--org", help="Target GitHub organization (overrides the one in the JSON file)")
    recreate_teams_parser.add_argument("-d", "--dry-run", action="store_true", 
                                     help="Run in dry-run mode without creating teams or adding members")
    recreate_teams_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    recreate_teams_parser.add_argument("--rate-limit", action="store_true", help="Display rate limit information")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Check if a command was specified
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Execute requested command
    try:
        # Get GitHub token
        token = validate_token()
        
        # Create GitHub client
        client = GitHubClient(token)
        
        # Handle 'users' command
        if args.command == "users":
            # Set default output file if not specified
            output_file = args.output if args.output else generate_filename("users")
            
            if args.verbose:
                print(f"🔍 Fetching members from organization: {args.org}")
                print(f"👤 Role filter: {args.role}")
                print(f"💾 Output will be saved to: {output_file}")
            
            # Get organization members
            members = client.get_org_members(args.org, args.role)
            
            if args.verbose:
                print(f"📊 Found {len(members)} members")
            
            # Process members
            users_data = []
            
            for i, member in enumerate(members):
                username = member.get("login")
                
                # Basic user data
                user_data = {
                    "login": username,
                    "id": member.get("id"),
                    "type": member.get("type"),
                    "site_admin": member.get("site_admin"),
                    "url": member.get("html_url")
                }
                
                # If full details requested, fetch additional user information
                if args.full:
                    if args.verbose:
                        print(f"👤 Fetching details for user: {username} ({i+1}/{len(members)})")
                    
                    try:
                        user_details = client.get_user_details(username)
                        
                        # Add additional fields
                        user_data.update({
                            "name": user_details.get("name"),
                            "company": user_details.get("company"),
                            "blog": user_details.get("blog"),
                            "location": user_details.get("location"),
                            "email": user_details.get("email"),
                            "bio": user_details.get("bio"),
                            "twitter_username": user_details.get("twitter_username"),
                            "public_repos": user_details.get("public_repos"),
                            "public_gists": user_details.get("public_gists"),
                            "followers": user_details.get("followers"),
                            "following": user_details.get("following"),
                            "created_at": user_details.get("created_at"),
                            "updated_at": user_details.get("updated_at")
                        })
                        
                    except Exception as e:
                        if args.verbose:
                            print(f"  ❌ Error fetching details for user '{username}': {e}")
                
                users_data.append(user_data)
            
            # Prepare output data
            output_data = {
                "organization": args.org,
                "total_members": len(users_data),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "role_filter": args.role,
                "full_details": args.full,
                "users": sorted(users_data, key=lambda x: x["login"].lower())  # Sort users alphabetically by login (case insensitive)
            }
            
            # Save to JSON file
            save_to_json(output_data, output_file)
            
            print(f"🎉 Successfully exported {len(users_data)} users from '{args.org}' organization to file: {output_file}")
            
            # Display rate limit if requested
            if args.rate_limit or args.verbose:
                display_rate_limit(client, args.verbose)
            
        # Handle 'teams' command
        elif args.command == "teams":
            # Set default teams output file if not specified
            teams_output_file = args.output if args.output else generate_filename("teams")
            
            if args.verbose:
                print(f"🔍 Fetching teams from organization: {args.org}")
                print(f"👤 Team member role filter: {args.role}")
                print(f"💾 Output will be saved to: {teams_output_file}")
                
            # Get organization teams
            teams = client.get_org_teams(args.org)
            
            if args.verbose:
                print(f"📊 Found {len(teams)} teams")
                
            # Process teams and members
            teams_data = []
            
            for i, team in enumerate(teams):
                team_slug = team.get("slug")
                team_name = team.get("name")
                
                if args.verbose:
                    print(f"👥 Fetching members for team: {team_name} ({i+1}/{len(teams)})")
                    
                # Get team members
                try:
                    team_members = client.get_team_members(team_slug, args.org, args.role)
                    member_handles = client.extract_user_handles(team_members)
                    
                    # Add team data
                    teams_data.append({
                        "id": team.get("id"),
                        "name": team_name,
                        "slug": team_slug,
                        "description": team.get("description"),
                        "privacy": team.get("privacy"),
                        "parent": team.get("parent", {}).get("name") if team.get("parent") else None,
                        "members_count": len(member_handles),
                        "members": sorted(member_handles, key=str.lower)  # Sort alphabetically (case insensitive)
                    })
                    
                    if args.verbose:
                        print(f"  ✅ Found {len(member_handles)} members in team '{team_name}'")
                except Exception as e:
                    if args.verbose:
                        print(f"  ❌ Error fetching members for team '{team_name}': {e}")
                    continue
            
            # Prepare output data
            output_data = {
                "organization": args.org,
                "total_teams": len(teams_data),
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "role_filter": args.role,
                "teams": sorted(teams_data, key=lambda x: x["name"].lower())  # Sort teams alphabetically by name (case insensitive)
            }
            
            # Save to JSON file
            save_to_json(output_data, teams_output_file)
            
            print(f"🎉 Successfully exported {len(teams_data)} teams from '{args.org}' organization to file: {teams_output_file}")
            
            # Display rate limit if requested
            if args.rate_limit or args.verbose:
                display_rate_limit(client, args.verbose)
                
        # Handle 'invite' command
        elif args.command == "invite":
            try:
                if args.verbose:
                    print(f"📄 Loading users from: {args.file}")
                
                # Load users from JSON file
                try:
                    user_handles = load_users_from_json(args.file)
                except Exception as e:
                    print(f"❌ Error loading users from file: {e}")
                    sys.exit(1)
                
                if args.verbose:
                    print(f"👥 Loaded {len(user_handles)} users to invite")
                
                # Invite users to organization
                success_count = 0
                failure_count = 0
                already_member_count = 0
                
                for i, username in enumerate(user_handles):
                    try:
                        if args.verbose:
                            print(f"✉️ Inviting user: {username} ({i+1}/{len(user_handles)})...")
                        
                        result = client.invite_user_to_org(args.org, username)
                        
                        # Check invitation state
                        state = result.get("state", "")
                        
                        if state == "pending":
                            if args.verbose:
                                print(f"  ✅ Invitation sent to {username}")
                            success_count += 1
                        elif state == "active":
                            if args.verbose:
                                print(f"  ℹ️ User {username} is already a member")
                            already_member_count += 1
                        else:
                            if args.verbose:
                                print(f"  ℹ️ User {username} invitation state: {state}")
                            success_count += 1
                        
                    except requests.RequestException as e:
                        if args.verbose:
                            print(f"  ❌ Failed to invite {username}: {e}")
                        failure_count += 1
                        continue
                    except Exception as e:
                        if args.verbose:
                            print(f"  ❌ Error processing {username}: {e}")
                        failure_count += 1
                        continue
                
                # Print summary
                print(f"📊 Invitation Summary for '{args.org}' organization:")
                print(f"   ✅ Successfully invited: {success_count}")
                print(f"   ℹ️ Already members: {already_member_count}")
                print(f"   ❌ Failed to invite: {failure_count}")
                print(f"   📈 Total processed: {len(user_handles)}")
                
                # Display rate limit if requested
                if args.rate_limit or args.verbose:
                    display_rate_limit(client, args.verbose)
                
            except Exception as e:
                print(f"❌ Error during invitation process: {e}")
                sys.exit(1)
        
        # Handle 'recreate-teams' command
        elif args.command == "recreate-teams":
            try:
                # Load teams data from JSON
                if args.verbose:
                    print(f"📄 Loading teams data from: {args.file}")
                    
                teams_data = load_teams_from_json(args.file)
                
                # Get organization name (from command line or JSON file)
                org_name = args.org if args.org else teams_data.get("organization")
                
                if not org_name:
                    print("❌ Error: Organization name not found in JSON file and not provided with --org")
                    sys.exit(1)
                    
                # Get teams array
                teams = teams_data.get("teams", [])
                
                if not teams:
                    print("❌ Error: No teams found in the JSON file")
                    sys.exit(1)
                    
                if args.verbose:
                    print(f"📊 Found {len(teams)} teams for organization: {org_name}")
                    
                # Dry run notice
                if args.dry_run:
                    print("🔍 DRY RUN MODE: No changes will be made to GitHub")
                    
                # Create teams with proper parent-child relationships
                if not args.dry_run:
                    team_id_map = create_parent_child_teams(client, org_name, teams, args.verbose)
                else:
                    # In dry run mode, just simulate team creation
                    if args.verbose:
                        print(f"🔍 [DRY RUN] Would create {len(teams)} teams in organization: {org_name}")
                        for team in teams:
                            parent_info = f" (parent: {team['parent']})" if team.get('parent') else ""
                            print(f"  🔍 [DRY RUN] Would create team: {team['name']}{parent_info}")
                    
                    # Create a fake team_id_map for dry run
                    team_id_map = {team['name']: 1000 + i for i, team in enumerate(teams)}
                
                # Add members to teams
                success_count, not_org_member_count, failure_count = add_members_to_teams(
                    client, org_name, teams, team_id_map, args.dry_run, args.verbose
                )
                
                # Print summary
                print(f"\n📊 Team Import Summary for '{org_name}' organization:")
                print(f"   🛠️ Teams processed: {len(teams)}")
                print(f"   ✅ Successfully {'would add' if args.dry_run else 'added'}: {success_count} members")
                
                if not_org_member_count > 0:
                    print(f"   ⚠️ Users not in organization: {not_org_member_count} (these users were skipped)")
                else:
                    print(f"   ✅ All users are members of the organization")
                    
                if failure_count > 0:
                    print(f"   ❌ Failed to add: {failure_count} members (see log for details)")
                
                # Calculate total user count
                total_users = success_count + not_org_member_count + failure_count
                print(f"   📈 Total user entries: {total_users}")
                
                # Display rate limit if requested
                if args.rate_limit or args.verbose:
                    display_rate_limit(client, args.verbose)
                    
            except FileNotFoundError as e:
                print(f"❌ Error: {e}")
                sys.exit(1)
            except ValueError as e:
                print(f"❌ Error: {e}")
                sys.exit(1)
            except requests.RequestException as e:
                print(f"❌ Error: {e}")
                sys.exit(1)
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                sys.exit(1)
            
    except requests.RequestException as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
