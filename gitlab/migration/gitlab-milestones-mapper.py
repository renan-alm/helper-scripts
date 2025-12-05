#!/usr/bin/env python3
"""
GitLab Milestones and Issues Mapper

This script helps with managing milestones and issues between GitLab and GitHub.

Usage:
    python gitlab-milestones-mapper.py create-map [--verbose] [--output FILE]
    python gitlab-milestones-mapper.py create-milestones [--input FILE] [--verbose]
    python gitlab-milestones-mapper.py apply-milestones [--verbose] [--diagnostic]

Environment Variables Required:
    GITLAB_API_PRIVATE_TOKEN - GitLab API Private Token
    GITLAB_API_ENDPOINT - GitLab API Endpoint URL (e.g., https://gitlab.com/api/v4)
    GITLAB_REPO_URL - GitLab repository URL (e.g., https://gitlab.com/namespace/project)
    
For create-milestones mode, also required:
    GITHUB_TOKEN - GitHub API Token
    GITHUB_REPO_URL - GitHub repository URL (e.g., https://github.com/user/repo)
    
For apply-milestones mode, all variables are required:
    GITLAB_API_PRIVATE_TOKEN - GitLab API Private Token
    GITLAB_API_ENDPOINT - GitLab API Endpoint URL
    GITLAB_REPO_URL - GitLab repository URL
    GITHUB_TOKEN - GitHub API Token
    GITHUB_REPO_URL - GitHub repository URL

Commands:
    create-map          - Read milestones from GitLab and create a mapping file
    create-milestones   - Create milestones in GitHub from the mapping file
    apply-milestones    - Find GitLab issues with milestones, create GitHub milestones, and apply them to corresponding GitHub issues

Options:
    --verbose           - Show more detailed information about each milestone/issue
    --output FILE       - Specify output file for the milestone map (default: milestones-map.csv)
    --input FILE        - Specify input file for the milestone map (for create-milestones command, default: milestones-map.csv)
    --diagnostic        - Run in diagnostic mode without making any changes (for apply-milestones command)
"""

import os
import json
import argparse
import requests
import time
import csv
from urllib.parse import urlparse, quote
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def validate_env_vars(mode='create'):
    """
    Validate required environment variables are set.
    
    Args:
        mode: 'create' for GitLab validation, 'create-milestones' for GitHub validation,
              'apply-milestones' for both GitLab and GitHub validation
    """
    if mode == 'create':
        required_vars = ['GITLAB_API_PRIVATE_TOKEN', 'GITLAB_API_ENDPOINT', 'GITLAB_REPO_URL']
    elif mode == 'create-milestones':
        required_vars = ['GITHUB_TOKEN', 'GITHUB_REPO_URL']
    elif mode == 'apply-milestones':
        required_vars = ['GITLAB_API_PRIVATE_TOKEN', 'GITLAB_API_ENDPOINT', 'GITLAB_REPO_URL',
                         'GITHUB_TOKEN', 'GITHUB_REPO_URL']
    else:
        required_vars = []
        
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

def get_gitlab_project_info(gitlab_repo_url):
    """
    Extract namespace, project and group information from GitLab repository URL.
    
    Args:
        gitlab_repo_url: GitLab repository URL
        
    Returns:
        Dictionary with project_id, group_id, namespace, and project
    """
    gitlab_repo_url = gitlab_repo_url.rstrip('/')
    gitlab_parsed = urlparse(gitlab_repo_url)
    gitlab_path_parts = gitlab_parsed.path.strip('/').split('/')
    
    if len(gitlab_path_parts) < 2:
        raise ValueError(f"Invalid GitLab repository URL: {gitlab_repo_url}")
        
    gitlab_namespace = '/'.join(gitlab_path_parts[:-1])
    gitlab_project = gitlab_path_parts[-1]
    
    # For groups, we need just the first level for API calls
    gitlab_group = gitlab_path_parts[0]
    if len(gitlab_path_parts) > 2:  # Handle subgroups
        gitlab_group = gitlab_path_parts[0]
    
    print(f"GitLab repository: {gitlab_repo_url}")
    print(f"GitLab namespace: {gitlab_namespace}")
    print(f"GitLab project: {gitlab_project}")
    print(f"GitLab group: {gitlab_group}")
    
    return {
        'project_id': quote(f"{gitlab_namespace}/{gitlab_project}", safe=''),
        'group_id': quote(gitlab_group, safe=''),
        'namespace': gitlab_namespace,
        'project': gitlab_project,
        'group': gitlab_group
    }

def get_github_repo_info(github_repo_url):
    """
    Extract owner and repository name from GitHub repository URL.
    
    Args:
        github_repo_url: GitHub repository URL
        
    Returns:
        Dictionary with owner and repo
    """
    github_repo_url = github_repo_url.rstrip('/')
    github_parsed = urlparse(github_repo_url)
    github_path_parts = github_parsed.path.strip('/').split('/')
    
    if len(github_path_parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {github_repo_url}")
        
    owner = github_path_parts[0]
    repo = github_path_parts[1]
    
    print(f"GitHub repository: {github_repo_url}")
    print(f"GitHub owner: {owner}")
    print(f"GitHub repo: {repo}")
    
    return {
        'owner': owner,
        'repo': repo
    }

def paginated_api_call(url, headers, params, error_prefix="API call", verbose=False):
    """
    Helper function for making paginated API calls.
    
    Args:
        url: API endpoint URL
        headers: Request headers
        params: Request parameters
        error_prefix: Prefix for error messages
        verbose: Whether to print verbose output
        
    Returns:
        List of results from all pages
    """
    results = []
    page = params.get('page', 1)
    per_page = params.get('per_page', 100)
    
    if verbose:
        print(f"Making paginated API call to {url}")
        print(f"Parameters: {params}")
    
    while True:
        params['page'] = page
        
        try:
            if verbose:
                print(f"Fetching page {page}...")
                
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            # Check for rate limiting (GitLab uses 429, GitHub uses 403 with rate limit message)
            if response.status_code == 429 or (response.status_code == 403 and 'rate limit' in response.text.lower()):
                reset_time = int(response.headers.get('RateLimit-Reset', 0) or response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(reset_time - time.time(), 60)
                print(f"Rate limited by API. Waiting for {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                continue
            
            # Handle other errors
            if response.status_code != 200:
                print(f"Error in {error_prefix}: {response.status_code} - {response.text}")
                if verbose:
                    print(f"URL: {url}")
                    print(f"Headers: {headers}")
                    print(f"Params: {params}")
                break
            
            # Parse response
            page_results = response.json()
            
            if not page_results:
                if verbose:
                    print(f"No results on page {page}, stopping pagination")
                break
                
            results.extend(page_results)
            
            # Check if we've reached the last page
            if len(page_results) < per_page:
                if verbose:
                    print(f"Got {len(page_results)} items (less than {per_page}), assuming last page")
                break
                
            # Check for next page using Link header (GitLab API provides this)
            link_header = response.headers.get('Link', '')
            if 'rel="next"' not in link_header and verbose:
                print("No 'next' link in headers, this might be the last page")
            
            # Go to next page
            page += 1
            
            # Gentle rate limiting
            time.sleep(0.2)
            
        except Exception as e:
            print(f"Error in {error_prefix}: {str(e)}")
            if verbose:
                import traceback
                traceback.print_exc()
            break
    
    if verbose:
        print(f"Total results fetched: {len(results)}")
        
    return results

def fetch_milestones_from_endpoint(api_endpoint, endpoint_path, api_token, verbose=False):
    """
    Helper function to fetch milestones from a specific GitLab API endpoint.
    
    Args:
        api_endpoint: Base GitLab API endpoint URL
        endpoint_path: Specific API endpoint path for milestones
        api_token: GitLab API private token
        verbose: Whether to print verbose output
        
    Returns:
        List of milestones
    """
    url = f"{api_endpoint}{endpoint_path}"
    headers = {
        'PRIVATE-TOKEN': api_token
    }
    params = {
        'state': 'all',
        'per_page': 100,
        'page': 1
    }
    
    return paginated_api_call(url, headers, params, "fetching GitLab milestones", verbose)

def fetch_gitlab_issues(api_endpoint, project_id, api_token, verbose=False):
    """
    Fetch all issues from a GitLab project, including those with milestones.
    
    Args:
        api_endpoint: GitLab API endpoint URL
        project_id: URL-encoded project ID
        api_token: GitLab API private token
        verbose: Whether to print verbose output
        
    Returns:
        List of issues with milestone information
    """
    print(f"\nFetching issues from GitLab project {project_id}...")
    
    # We'll fetch both opened and closed issues to make sure we get everything
    all_issues = []
    
    # Fetch all issues with state 'opened'
    url = f"{api_endpoint}/projects/{project_id}/issues"
    headers = {
        'PRIVATE-TOKEN': api_token
    }
    
    # First, get all opened issues
    params = {
        'per_page': 100,
        'page': 1,
        'scope': 'all',
        'state': 'opened'
    }
    
    if verbose:
        print("Fetching opened issues...")
        
    opened_issues = paginated_api_call(url, headers, params, "fetching opened GitLab issues", verbose)
    all_issues.extend(opened_issues)
    
    if verbose:
        print(f"Found {len(opened_issues)} opened issues")
    
    # Then, get all closed issues
    params = {
        'per_page': 100,
        'page': 1,
        'scope': 'all',
        'state': 'closed'
    }
    
    if verbose:
        print("Fetching closed issues...")
        
    closed_issues = paginated_api_call(url, headers, params, "fetching closed GitLab issues", verbose)
    all_issues.extend(closed_issues)
    
    if verbose:
        print(f"Found {len(closed_issues)} closed issues")
    
    # Filter issues with milestones
    issues_with_milestones = [issue for issue in all_issues if issue.get('milestone') is not None]
    
    print(f"Found {len(all_issues)} issues in total")
    print(f"Found {len(issues_with_milestones)} issues with milestones")
    
    if verbose:
        print("Sample of milestone IDs in issues:", [issue.get('milestone', {}).get('id') for issue in issues_with_milestones[:5]])
    
    return issues_with_milestones

def get_gitlab_milestones(api_endpoint, project_info, api_token, verbose=False):
    """
    Get all milestones from a GitLab project and its group.
    
    Args:
        api_endpoint: GitLab API endpoint URL
        project_info: Dictionary with project and group information
        api_token: GitLab API private token
        verbose: Whether to print verbose output
        
    Returns:
        List of milestones with source information
    """
    all_milestones = []
    
    # Fetch project milestones
    print("Fetching project milestones...")
    project_endpoint = f"/projects/{project_info['project_id']}/milestones"
    project_milestones = fetch_milestones_from_endpoint(api_endpoint, project_endpoint, api_token, verbose)
    
    # Add source information to each milestone
    for milestone in project_milestones:
        milestone['source'] = 'project'
        milestone['source_name'] = f"{project_info['namespace']}/{project_info['project']}"
    
    all_milestones.extend(project_milestones)
    print(f"Found {len(project_milestones)} project milestones")
    
    # Fetch group milestones
    print("\nFetching group milestones...")
    group_endpoint = f"/groups/{project_info['group_id']}/milestones"
    group_milestones = fetch_milestones_from_endpoint(api_endpoint, group_endpoint, api_token, verbose)
    
    # Add source information to each milestone
    for milestone in group_milestones:
        milestone['source'] = 'group'
        milestone['source_name'] = project_info['group']
    
    all_milestones.extend(group_milestones)
    print(f"Found {len(group_milestones)} group milestones")
    
    print(f"\nTotal: {len(all_milestones)} milestones")
    return all_milestones

def print_milestones(milestones, verbose=False):
    """
    Print milestone information in a readable format.
    
    Args:
        milestones: List of milestone dictionaries
        verbose: Whether to print verbose information
    """
    print(f"\nFound {len(milestones)} milestones:\n")
    print("=" * 80)
    
    for i, milestone in enumerate(milestones, 1):
        title = milestone.get('title', 'Untitled')
        state = milestone.get('state', 'unknown')
        due_date = milestone.get('due_date', 'No due date')
        description = milestone.get('description', 'No description')
        
        # Get source information
        source = milestone.get('source', 'unknown')
        source_name = milestone.get('source_name', 'unknown')
        
        # Get issue statistics
        statistics = milestone.get('stats', {})
        total_issues = statistics.get('total_issues', 0)
        open_issues = statistics.get('open_issues', 0)
        closed_issues = statistics.get('closed_issues', 0)
        
        print(f"{i}. {title} ({state}) - Source: {source.upper()} ({source_name})")
        print(f"   ID: {milestone.get('id', 'N/A')}")
        print(f"   IID: {milestone.get('iid', 'N/A')}")
        print(f"   Due date: {due_date}")
        print(f"   Issues: {total_issues} ({open_issues} open, {closed_issues} closed)")
        
        if verbose:
            # Truncate long descriptions
            if len(description) > 200:
                description = description[:200] + "..."
            print(f"   Description: {description}")
            print(f"   Web URL: {milestone.get('web_url', 'N/A')}")
            print(f"   Created: {milestone.get('created_at', 'N/A')}")
            print(f"   Updated: {milestone.get('updated_at', 'N/A')}")
        
        print("-" * 80)

def save_milestones_to_map(milestones, output_file="milestones-map.csv"):
    """
    Save milestones to a CSV map file for later processing.
    
    Args:
        milestones: List of milestone dictionaries
        output_file: Path to the output file
        
    Returns:
        Number of milestones saved
    """
    # Define CSV header
    headers = [
        "gitlab_id", "gitlab_iid", "gitlab_title", "gitlab_description",
        "gitlab_state", "gitlab_due_date", "github_number", "github_title",
        "github_state", "github_due_on", "status", "gitlab_source",
        "gitlab_source_name", "gitlab_web_url"
    ]
    
    print(f"\nSaving milestone map to {output_file}...")
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for milestone in milestones:
                writer.writerow({
                    "gitlab_id": milestone.get("id", ""),
                    "gitlab_iid": milestone.get("iid", ""),
                    "gitlab_title": milestone.get("title", ""),
                    "gitlab_description": milestone.get("description", ""),
                    "gitlab_state": milestone.get("state", ""),
                    "gitlab_due_date": milestone.get("due_date", ""),
                    "github_number": "",  # To be filled when applying the map
                    "github_title": "",   # To be filled when applying the map
                    "github_state": "",   # To be filled when applying the map
                    "github_due_on": "",  # To be filled when applying the map
                    "status": "not_created",
                    "gitlab_source": milestone.get("source", ""),
                    "gitlab_source_name": milestone.get("source_name", ""),
                    "gitlab_web_url": milestone.get("web_url", "")
                })
                
        print(f"Successfully saved {len(milestones)} milestones to {output_file}")
        return len(milestones)
        
    except Exception as e:
        print(f"Error saving milestones to file: {str(e)}")
        return 0

def create_github_milestone(owner, repo, github_token, milestone_data, verbose=False):
    """
    Create a milestone in GitHub.
    
    Args:
        owner: GitHub repository owner
        repo: GitHub repository name
        github_token: GitHub API token
        milestone_data: Dictionary containing milestone data
        verbose: Whether to print verbose output
        
    Returns:
        Dictionary with created milestone data or None if creation failed
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/milestones"
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Prepare request payload
    payload = {
        'title': milestone_data.get('gitlab_title', ''),
        'description': milestone_data.get('gitlab_description', ''),
        'state': 'open' if milestone_data.get('gitlab_state') == 'active' else 'closed'
    }
    
    # Add due date if present
    due_date = milestone_data.get('gitlab_due_date')
    if due_date:
        # GitHub requires due_on to be in ISO 8601 format with time
        if 'T' not in due_date:
            due_date = f"{due_date}T23:59:59Z"
        payload['due_on'] = due_date
    
    if verbose:
        print(f"Creating GitHub milestone with payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        # Check for rate limiting
        if response.status_code == 403 and 'rate limit' in response.text.lower():
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            wait_time = max(reset_time - time.time(), 60)
            print(f"Rate limited by GitHub API. Waiting for {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            return create_github_milestone(owner, repo, github_token, milestone_data, verbose)
        
        # Handle other response codes
        if response.status_code == 201:
            return response.json()
        else:
            print(f"Error creating GitHub milestone: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        print(f"Error creating GitHub milestone: {str(e)}")
        return None

def get_github_issue(owner, repo, issue_number, github_token, verbose=False):
    """
    Get a GitHub issue by its number.
    
    Args:
        owner: GitHub repository owner
        repo: GitHub repository name
        issue_number: Issue number
        github_token: GitHub API token
        verbose: Whether to print verbose output
        
    Returns:
        Dictionary with issue data or None if issue not found
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        # Check for rate limiting
        if response.status_code == 403 and 'rate limit' in response.text.lower():
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            wait_time = max(reset_time - time.time(), 60)
            print(f"Rate limited by GitHub API. Waiting for {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            return get_github_issue(owner, repo, issue_number, github_token, verbose)
        
        # Handle other response codes
        if response.status_code == 200:
            return response.json()
        else:
            if verbose:
                print(f"GitHub issue #{issue_number} not found: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        print(f"Error getting GitHub issue: {str(e)}")
        return None

def update_github_issue_milestone(owner, repo, issue_number, milestone_number, github_token, verbose=False):
    """
    Update a GitHub issue to assign a milestone.
    
    Args:
        owner: GitHub repository owner
        repo: GitHub repository name
        issue_number: Issue number
        milestone_number: Milestone number
        github_token: GitHub API token
        verbose: Whether to print verbose output
        
    Returns:
        Dictionary with updated issue data or None if update failed
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # Prepare request payload
    payload = {
        'milestone': milestone_number
    }
    
    if verbose:
        print(f"Updating GitHub issue #{issue_number} with milestone #{milestone_number}")
    
    try:
        response = requests.patch(url, headers=headers, json=payload)
        
        # Check for rate limiting
        if response.status_code == 403 and 'rate limit' in response.text.lower():
            reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
            wait_time = max(reset_time - time.time(), 60)
            print(f"Rate limited by GitHub API. Waiting for {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            return update_github_issue_milestone(owner, repo, issue_number, milestone_number, github_token, verbose)
        
        # Handle other response codes
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error updating GitHub issue: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        print(f"Error updating GitHub issue: {str(e)}")
        return None

def map_gitlab_to_github_issues(gitlab_issues, milestone_map, github_repo_info, gitlab_repo_url, github_token, verbose=False, diagnostic=False):
    """
    Map GitLab issues with milestones to GitHub issues.
    
    Args:
        gitlab_issues: List of GitLab issues with milestones
        milestone_map: Dictionary mapping GitLab milestone IDs to GitHub milestone numbers
        github_repo_info: Dictionary with GitHub repo owner and name
        gitlab_repo_url: GitLab repository URL
        github_token: GitHub API token
        verbose: Whether to print verbose output
        diagnostic: If True, run in diagnostic mode without making any changes
        
    Returns:
        Tuple of (success_count, error_count, not_found_count)
    """
    print(f"\nMapping GitLab issues to GitHub issues...")
    
    owner = github_repo_info['owner']
    repo = github_repo_info['repo']
    
    success_count = 0
    error_count = 0
    not_found_count = 0
    
    github_base_url = f"https://github.com/{owner}/{repo}/issues"
    
    print("=" * 80)
    print(f"{'GitLab Issue':<30} {'GitHub Issue':<30} {'Milestone':<20}")
    print("-" * 80)
    
    for issue in gitlab_issues:
        # Extract GitLab issue information
        gitlab_issue_iid = issue.get('iid')
        gitlab_issue_title = issue.get('title')
        gitlab_milestone_id = issue.get('milestone', {}).get('id')
        gitlab_milestone_title = issue.get('milestone', {}).get('title', 'Unknown')
        
        # Construct issue URLs
        gitlab_issue_url = f"{gitlab_repo_url}/issues/{gitlab_issue_iid}"
        github_issue_url = f"{github_base_url}/{gitlab_issue_iid}"
        
        # Skip if no milestone or no mapping
        if not gitlab_milestone_id:
            if verbose:
                print(f"GitLab issue #{gitlab_issue_iid} has no milestone")
            not_found_count += 1
            continue
        elif gitlab_milestone_id not in milestone_map:
            if verbose:
                print(f"No GitHub milestone mapping for GitLab issue #{gitlab_issue_iid} with milestone '{gitlab_milestone_title}'")
            not_found_count += 1
            continue
        
        github_milestone_number = milestone_map[gitlab_milestone_id]
        
        # Check if GitHub issue exists
        github_issue = get_github_issue(owner, repo, gitlab_issue_iid, github_token, verbose)
        
        if not github_issue:
            print(f"{gitlab_issue_url:<30} {f'Not found (#{gitlab_issue_iid})':<30} {gitlab_milestone_title:<20}")
            not_found_count += 1
            if diagnostic:
                print(f"  → GitLab issue #{gitlab_issue_iid}: '{gitlab_issue_title}' - no corresponding GitHub issue found")
            continue
        
        # Update GitHub issue with milestone (or simulate in diagnostic mode)
        if diagnostic:
            print(f"{gitlab_issue_url:<30} {github_issue_url:<30} {gitlab_milestone_title:<20} (WOULD UPDATE)")
            success_count += 1
        else:
            result = update_github_issue_milestone(owner, repo, gitlab_issue_iid, github_milestone_number, github_token, verbose)
            
            if result:
                print(f"{gitlab_issue_url:<30} {github_issue_url:<30} {gitlab_milestone_title:<20}")
                success_count += 1
            else:
                print(f"{gitlab_issue_url:<30} {f'Error updating (#{gitlab_issue_iid})':<30} {gitlab_milestone_title:<20}")
                error_count += 1
        
        # Gentle rate limiting
        time.sleep(0.5)
    
    print("=" * 80)
    print(f"\nIssue milestone mapping summary:")
    if diagnostic:
        print(f"  DIAGNOSTIC MODE: No changes were made")
        print(f"  Would have updated: {success_count}")
    else:
        print(f"  Successfully updated: {success_count}")
    print(f"  Failed to update: {error_count}")
    print(f"  Not found or no milestone mapping: {not_found_count}")
    print(f"  Total issues processed: {len(gitlab_issues)}")
    
    return (success_count, error_count, not_found_count)

def apply_milestones_to_issues(input_file=None, verbose=False, diagnostic=False):
    """
    Apply milestones to GitHub issues based on GitLab issues.
    Finds GitLab issues with milestones, looks for equivalent GitHub milestones,
    and applies them to the corresponding GitHub issues.
    
    Args:
        input_file: Not used, kept for backward compatibility
        verbose: Whether to print verbose output
        diagnostic: If True, run in diagnostic mode without making any changes
        
    Returns:
        Tuple of (success_count, error_count, not_found_count)
    """
    
    if diagnostic:
        print("\n===== RUNNING IN DIAGNOSTIC MODE - NO CHANGES WILL BE MADE =====\n")
        # In diagnostic mode, we'll be more verbose
        verbose = True
    print("\nFinding GitLab issues with milestones and applying to GitHub issues...")
    
    # Validate environment variables
    validate_env_vars('apply-milestones')
    
    # Get environment variables
    github_token = os.environ.get('GITHUB_TOKEN')
    github_repo_url = os.environ.get('GITHUB_REPO_URL')
    gitlab_api_token = os.environ.get('GITLAB_API_PRIVATE_TOKEN')
    gitlab_api_endpoint = os.environ.get('GITLAB_API_ENDPOINT')
    gitlab_repo_url = os.environ.get('GITLAB_REPO_URL')
    
    # Get GitHub repository information
    github_repo_info = get_github_repo_info(github_repo_url)
    owner = github_repo_info['owner']
    repo = github_repo_info['repo']
    
    # Get GitLab project info
    project_info = get_gitlab_project_info(gitlab_repo_url)
    
    milestone_map = {}  # Map GitLab milestone IDs to GitHub milestone numbers
    
    try:
        # Fetch GitLab issues with milestones
        gitlab_issues = fetch_gitlab_issues(gitlab_api_endpoint, project_info['project_id'], 
                                          gitlab_api_token, verbose)
        
        if not gitlab_issues:
            print("No GitLab issues with milestones found")
            return (0, 0, 0)
        
        # Extract unique milestones from GitLab issues
        gitlab_milestones = {}
        for issue in gitlab_issues:
            if issue.get('milestone'):
                milestone_id = issue['milestone']['id']
                if milestone_id not in gitlab_milestones:
                    gitlab_milestones[milestone_id] = issue['milestone']
        
        print(f"\nFound {len(gitlab_milestones)} unique milestones in GitLab issues")
        
        # Fetch all existing GitHub milestones
        url = f"https://api.github.com/repos/{owner}/{repo}/milestones"
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Get all milestones (both open and closed)
        response = requests.get(url, headers=headers, params={'state': 'all', 'per_page': 100})
        existing_milestones = []
        
        if response.status_code == 200:
            existing_milestones = response.json()
            print(f"Found {len(existing_milestones)} existing GitHub milestones")
        else:
            print(f"Error fetching GitHub milestones: {response.status_code} - {response.text}")
            return (0, 0, 0)
        
        # Build mapping between GitLab milestone IDs and GitHub milestone numbers
        gitlab_milestone_titles = {milestone_id: milestone.get('title') for milestone_id, milestone in gitlab_milestones.items()}
        if verbose:
            print(f"\nGitLab milestone titles: {gitlab_milestone_titles}")
            print(f"\nGitHub milestone titles: {[m.get('title') for m in existing_milestones]}")
        
        # First pass: exact matches
        for milestone_id, milestone in gitlab_milestones.items():
            title = milestone.get('title')
            
            # Look for matching milestone in GitHub by title
            github_milestone = None
            for existing in existing_milestones:
                if existing.get('title') == title:
                    github_milestone = existing
                    print(f"Found matching GitHub milestone: {title} (#{existing.get('number')})")
                    milestone_map[milestone_id] = existing.get('number')
                    break
        
        # Second pass: case-insensitive matches
        for milestone_id, milestone in gitlab_milestones.items():
            if milestone_id in milestone_map:
                continue  # Already mapped
                
            title = milestone.get('title')
            
            for existing in existing_milestones:
                if existing.get('title').lower() == title.lower():
                    github_milestone = existing
                    print(f"Found matching GitHub milestone (case-insensitive): {title} (#{existing.get('number')})")
                    milestone_map[milestone_id] = existing.get('number')
                    break
        
        # Third pass: fuzzy matching as last resort
        not_found_milestones = []
        for milestone_id, milestone in gitlab_milestones.items():
            if milestone_id in milestone_map:
                continue  # Already mapped
                
            title = milestone.get('title')
            not_found_milestones.append(title)
            print(f"No matching GitHub milestone found for GitLab milestone: {title}")
            
        print(f"\nFound {len(milestone_map)} GitHub milestones matching GitLab milestones")
        print(f"Missing {len(gitlab_milestones) - len(milestone_map)} milestone matches")
        
        if not_found_milestones:
            print("\nThe following GitLab milestones were not found in GitHub:")
            for title in not_found_milestones:
                print(f" - {title}")
                
        if not milestone_map:
            print("\nNo milestone matches found. Please create milestones in GitHub first.")
            return (0, 0, 0)
            milestone_map[milestone_id] = github_milestone.get('number')
        
        # Print warning if some milestones weren't found
        not_found_milestones = [m.get('title') for m_id, m in gitlab_milestones.items() if m_id not in milestone_map]
        if not_found_milestones:
            print("\nWARNING: The following GitLab milestones were not found in GitHub:")
            for title in not_found_milestones:
                print(f" - {title}")
            print("Issues with these milestones will be skipped.")
            
        # Apply milestones to GitHub issues
        if gitlab_issues and milestone_map:
            if diagnostic:
                print(f"\nDIAGNOSTIC MODE: Analyzing milestones to apply using {len(milestone_map)} mapped milestones...")
            else:
                print(f"\nApplying milestones to GitHub issues using {len(milestone_map)} mapped milestones...")
            return map_gitlab_to_github_issues(gitlab_issues, milestone_map, github_repo_info, 
                                            gitlab_repo_url, github_token, verbose, diagnostic)
        else:
            print("No milestones to apply to GitHub issues. Make sure to create milestones in GitHub first.")
            return (0, 0, 0)
        
    except Exception as e:
        print(f"Error applying milestones to issues: {str(e)}")
        import traceback
        traceback.print_exc()
        return (0, 0, 0)

def create_github_milestones(input_file="milestones-map.csv", verbose=False, apply_issues=False):
    """
    Create milestones in GitHub from the milestone map and optionally map issues.
    
    Args:
        input_file: Path to the input map file
        verbose: Whether to print verbose output
        apply_issues: Whether to also apply milestones to GitHub issues (deprecated)
        
    Returns:
        Number of milestones successfully created
    """
    print(f"\nReading milestone map from {input_file}...")
    
    # Validate environment variables
    if apply_issues:
        validate_env_vars('apply-milestones')
    else:
        validate_env_vars('create-milestones')
    
    # Get environment variables
    github_token = os.environ.get('GITHUB_TOKEN')
    github_repo_url = os.environ.get('GITHUB_REPO_URL')
    
    # Get GitHub repository information
    github_repo_info = get_github_repo_info(github_repo_url)
    owner = github_repo_info['owner']
    repo = github_repo_info['repo']
    
    success_count = 0
    error_count = 0
    skipped_count = 0
    milestone_map = {}  # Map GitLab milestone IDs to GitHub milestone numbers
    
    try:
        # Read the milestone map
        with open(input_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            
            print(f"Found {len(rows)} milestones in map file")
            print(f"Creating milestones in GitHub repository: {github_repo_url}")
            
            # Process each milestone
            for i, row in enumerate(rows):
                # Skip already created milestones
                if row.get('status') == 'created':
                    print(f"Skipping already created milestone: {row.get('gitlab_title')}")
                    skipped_count += 1
                    # Still add to our mapping for issue processing
                    if row.get('gitlab_id') and row.get('github_number'):
                        milestone_map[int(row.get('gitlab_id'))] = int(row.get('github_number'))
                    continue
                
                print(f"Processing milestone {i+1}/{len(rows)}: {row.get('gitlab_title')}")
                
                # Create the milestone in GitHub
                github_milestone = create_github_milestone(owner, repo, github_token, row, verbose)
                
                if github_milestone:
                    # Update the row with GitHub milestone information
                    row['github_number'] = github_milestone.get('number', '')
                    row['github_title'] = github_milestone.get('title', '')
                    row['github_state'] = github_milestone.get('state', '')
                    row['github_due_on'] = github_milestone.get('due_on', '')
                    row['status'] = 'created'
                    
                    # Add to our mapping for issue processing
                    if row.get('gitlab_id'):
                        milestone_map[int(row.get('gitlab_id'))] = github_milestone.get('number')
                    
                    print(f"Successfully created GitHub milestone: {row['github_title']} (#{row['github_number']})")
                    success_count += 1
                else:
                    print(f"Failed to create GitHub milestone: {row.get('gitlab_title')}")
                    error_count += 1
                
                # Avoid hitting rate limits
                time.sleep(1)
            
            # Write the updated milestone map
            with open(input_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=reader.fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            print(f"\nMilestone creation summary:")
            print(f"  Successfully created: {success_count}")
            print(f"  Failed to create: {error_count}")
            print(f"  Already created (skipped): {skipped_count}")
            print(f"  Total milestones: {len(rows)}")
            print(f"\nUpdated milestone map saved to {input_file}")
            
            # Process GitLab issues with milestones if requested (deprecated)
            if apply_issues and milestone_map:
                print("Note: The --apply-issues flag is deprecated. Please use the 'apply-milestones' command instead.")
                # Call the dedicated function for applying milestones to issues
                apply_milestones_to_issues(input_file, verbose)
            
        return success_count
        
    except Exception as e:
        print(f"Error applying milestone map: {str(e)}")
        return 0

def main():
    parser = argparse.ArgumentParser(
        description='GitLab/GitHub Milestones Tool')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Create map command
    create_parser = subparsers.add_parser('create-map', 
                                         help='Read milestones from GitLab and create a mapping file')
    create_parser.add_argument('--verbose', action='store_true',
                            help='Show more detailed information about each milestone')
    create_parser.add_argument('--output', type=str, default='milestones-map.csv',
                            help='Specify output file for the milestone map')
    
    # Create milestones command
    create_milestones_parser = subparsers.add_parser('create-milestones',
                                        help='Create milestones in GitHub from the milestone mapping')
    create_milestones_parser.add_argument('--verbose', action='store_true',
                           help='Show more detailed information during the process')
    create_milestones_parser.add_argument('--input', type=str, default='milestones-map.csv',
                           help='Specify input file for the milestone map')
    
    # Apply milestones to issues command
    apply_milestones_parser = subparsers.add_parser('apply-milestones',
                                     help='Apply milestones to GitHub issues based on GitLab issues')
    apply_milestones_parser.add_argument('--verbose', action='store_true',
                           help='Show more detailed information during the process')
    apply_milestones_parser.add_argument('--diagnostic', action='store_true',
                           help='Run in diagnostic mode without making any changes')
    
    args = parser.parse_args()
    
    # If no command is provided, show help
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == 'create-map':
            # Validate environment variables
            validate_env_vars('create')
            
            # Get environment variables
            gitlab_api_token = os.environ.get('GITLAB_API_PRIVATE_TOKEN')
            gitlab_api_endpoint = os.environ.get('GITLAB_API_ENDPOINT')
            gitlab_repo_url = os.environ.get('GITLAB_REPO_URL')
            
            # Get GitLab project and group info
            project_info = get_gitlab_project_info(gitlab_repo_url)
            
            # Get milestones
            milestones = get_gitlab_milestones(gitlab_api_endpoint, project_info, gitlab_api_token, args.verbose)
            
            # Print milestones
            print_milestones(milestones, args.verbose)
            
            # Save milestones to map file
            save_milestones_to_map(milestones, args.output)
            
        elif args.command == 'create-milestones':
            # Create GitHub milestones from the milestone map
            create_github_milestones(args.input, args.verbose, False)
            
        elif args.command == 'apply-milestones':
            # Apply milestones to GitHub issues
            apply_milestones_to_issues(verbose=args.verbose, diagnostic=args.diagnostic)
            
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
        
    return 0

if __name__ == '__main__':
    exit(main())
