#!/usr/bin/env python3
"""
GitHub Teams Importer

A script to recreate GitHub teams from a JSON export file and add members to those teams.
"""

import argparse
import json
import os
import sys
import requests
from typing import List, Dict, Any, Set, Tuple


class GitHubClient:
    """GitHub API client for team operations."""
    
    def __init__(self, token: str):
        """Initialize GitHub client with authentication token."""
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "gh-teams-importer/1.0"
        }
        self.org_members_cache = {}  # Cache for organization members
    
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
    
    def get_org_members(self, org: str, force_refresh: bool = False) -> Set[str]:
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
        
        url = f"{self.base_url}/orgs/{org}/members"
        
        try:
            all_members = []
            page = 1
            
            while True:
                params = {"per_page": 100, "page": page}
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                members_page = response.json()
                if not members_page:
                    break
                    
                all_members.extend(members_page)
                page += 1
            
            # Extract usernames and convert to a set for O(1) lookups
            member_usernames = {member["login"] for member in all_members}
            
            # Cache the results
            self.org_members_cache[org] = member_usernames
            
            return member_usernames
            
        except requests.RequestException as e:
            raise requests.RequestException(f"Failed to get organization members: {e}")


def validate_token() -> str:
    """
    Validate GitHub token from environment variable.
    
    Returns:
        The GitHub token
        
    Raises:
        ValueError: If token is not set
    """
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        raise ValueError("GITHUB_TOKEN environment variable is not set. Please set it before running this script.")
    
    return token


def load_teams_from_json(filename: str) -> Dict[str, Any]:
    """
    Load teams data from a JSON file.
    
    Args:
        filename: Path to the JSON file
        
    Returns:
        Dictionary containing teams data
        
    Raises:
        Exception: If file can't be read or doesn't contain valid teams data
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Validate that this is a teams export file
        if not isinstance(data, dict) or "teams" not in data or "organization" not in data:
            raise ValueError("Invalid JSON format: Expected an object with 'teams' and 'organization' keys")
            
        return data
            
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON file: {filename}")
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {filename}")
    except Exception as e:
        raise Exception(f"Error loading JSON file: {e}")


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
        org_members = client.get_org_members(org)
    except Exception as e:
        print(f"❌ Error getting organization members: {e}")
        return 0, 0, 0
    
    success_count = 0
    not_org_member_count = 0
    failure_count = 0
    
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
    
    return success_count, not_org_member_count, failure_count


def main() -> None:
    """Main function to execute the script."""
    parser = argparse.ArgumentParser(
        description="GitHub Teams Importer - Recreate teams from a JSON export file",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "json_file",
        help="Path to the JSON file containing teams data (exported from gh-management.py)"
    )
    
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Run in dry-run mode without creating teams or adding members"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "-o", "--org",
        help="Target GitHub organization (overrides the one in the JSON file)"
    )
    
    args = parser.parse_args()
    
    try:
        # Load teams data from JSON
        if args.verbose:
            print(f"📄 Loading teams data from: {args.json_file}")
            
        teams_data = load_teams_from_json(args.json_file)
        
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
            
        # Validate GitHub token
        token = validate_token()
        
        # Create GitHub client
        client = GitHubClient(token)
        
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
        print(f"📊 Team Import Summary for '{org_name}' organization:")
        print(f"   ✅ Successfully {'would add' if args.dry_run else 'added'}: {success_count} members")
        print(f"   ⚠️ Not organization members: {not_org_member_count}")
        print(f"   ❌ Failed to add: {failure_count}")
        print(f"   📈 Total teams processed: {len(teams)}")
        
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


if __name__ == "__main__":
    main()
