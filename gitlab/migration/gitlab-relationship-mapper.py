#!/usr/bin/env python3
"""
GitLab Issue Relationships Mapper

This script helps with managing issue relationships between GitLab and GitHub.

Usage:
    python gitlab-relationship-mapper.py create-map [--verbose] [--output FILE]
    python gitlab-relationship-mapper.py apply-relationships [--verbose] [--diagnostic] [OPTIONS]

Environment Variables Required:
    GITLAB_API_PRIVATE_TOKEN - GitLab API Private Token
    GITLAB_API_ENDPOINT - GitLab API Endpoint URL (e.g., https://gitlab.com/api/v4)
    GITLAB_REPO_URL - GitLab repository URL (e.g., https://gitlab.com/namespace/project)
    
For apply-relationships mode, also required (unless using --skip-github-validation):
    GITHUB_TOKEN - GitHub API Token
    GITHUB_REPO_URL - GitHub repository URL (e.g., https://github.com/user/repo)

Commands:
    create-map          - Read issues and their relationships from GitLab and create a mapping file
    apply-relationships - Apply issue relationships to GitHub issues based on the mapping file

Options:
    --verbose           - Show more detailed information about each issue/relationship
    --output FILE       - Specify output file for the relationship map (default: relationships-map.csv)
    --input FILE        - Specify input file for the relationship map (default: relationships-map.csv)
    
Diagnostic Mode Options:
    --diagnostic        - Run in diagnostic mode without making any changes
    --report-file FILE  - Save diagnostic report to specified file
    --skip-github-validation - Skip GitHub validation in diagnostic mode (useful for testing mapping file without GitHub credentials)
    --summary-only      - Show only summary information in diagnostic mode, not individual relationships
"""

import re
import csv
import time
import json
import argparse
import requests
import os
import sys
import concurrent.futures
from urllib.parse import urlparse, quote
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def validate_env_vars(mode='create'):
    """
    Validate required environment variables are set.
    
    Args:
        mode: 'create' for GitLab validation,
              'apply-relationships' for both GitLab and GitHub validation
    """
    if mode == 'create':
        required_vars = ['GITLAB_API_PRIVATE_TOKEN', 'GITLAB_API_ENDPOINT', 'GITLAB_REPO_URL']
    elif mode == 'apply-relationships':
        required_vars = ['GITLAB_API_PRIVATE_TOKEN', 'GITLAB_API_ENDPOINT', 'GITLAB_REPO_URL',
                         'GITHUB_TOKEN', 'GITHUB_REPO_URL']
    else:
        required_vars = []
        
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}. " +
                        f"For diagnostic mode without GitHub validation, use --skip-github-validation.")

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
    if not github_repo_url:
        return None
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

def validate_url(url, timeout=5):
    """
    Validate if a URL can be reached.
    
    Args:
        url: URL to validate
        timeout: Connection timeout in seconds
        
    Returns:
        Boolean indicating if URL is reachable
    """
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        return response.status_code < 400  # Consider any status code below 400 as success
    except requests.RequestException:
        return False

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

def fetch_gitlab_issues(api_endpoint, project_id, api_token, verbose=False):
    """
    Fetch all issues from a GitLab project, including their relationships.
    
    Args:
        api_endpoint: GitLab API endpoint URL
        project_id: URL-encoded project ID
        api_token: GitLab API private token
        verbose: Whether to print verbose output
        
    Returns:
        List of issues
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
    
    print(f"Found {len(all_issues)} issues in total")
    
    return all_issues

def get_issue_relationships(api_endpoint, project_id, issues, api_token, verbose=False):
    """
    Extract relationships between issues.
    
    Args:
        api_endpoint: GitLab API endpoint URL
        project_id: URL-encoded project ID
        issues: List of GitLab issues
        api_token: GitLab API private token
        verbose: Whether to print verbose output
        
    Returns:
        List of issue relationship dictionaries
    """
    print("\nExtracting issue relationships...")
    
    headers = {
        'PRIVATE-TOKEN': api_token
    }
    
    relationships = []
    relationship_count = 0
    processed_count = 0
    total_issues = len(issues)
    
    # Define the relationship types we're interested in
    relationship_types = {
        'relates_to': 'relates to',
        'blocks': 'blocks',
        'is_blocked_by': 'is blocked by',
        'duplicates': 'duplicates',
        'is_duplicated_by': 'is duplicated by'
    }
    
    # Also check for relationships in the issue description and comments
    # These are patterns like "Related to #123" or "Blocks #456"
    relation_patterns = {
        r'(?i)relates?\s*to\s*(?:issue)?\s*#?(\d+)': 'relates_to',
        r'(?i)blocks\s*(?:issue)?\s*#?(\d+)': 'blocks',
        r'(?i)(?:is)?\s*blocked\s*by\s*(?:issue)?\s*#?(\d+)': 'is_blocked_by',
        r'(?i)duplicates?\s*(?:issue)?\s*#?(\d+)': 'duplicates',
        r'(?i)(?:is)?\s*duplicated\s*by\s*(?:issue)?\s*#?(\d+)': 'is_duplicated_by',
        r'(?i)depends\s*on\s*(?:issue)?\s*#?(\d+)': 'depends_on',
        r'(?i)(?:is)?\s*dependency\s*(?:of|for)\s*(?:issue)?\s*#?(\d+)': 'is_dependency_for'
    }
    
    # Loop through each issue to find relationships
    for i, issue in enumerate(issues, 1):
        issue_iid = issue['iid']
        issue_title = issue['title']
        issue_description = issue.get('description', '') or ''
        
        if verbose:
            print(f"Processing issue #{issue_iid}: {issue_title}")
        elif i % 10 == 0 or i == total_issues:
            print(f"Processing issues... {i}/{total_issues} ({i/total_issues*100:.1f}%)")
        
        processed_count += 1
        
        # 1. First, check for explicit links using the GitLab API
        url = f"{api_endpoint}/projects/{project_id}/issues/{issue_iid}/links"
        links = paginated_api_call(url, headers, {}, "fetching links for issue #{issue_iid}", verbose)
        
        # Process each explicit relationship
        for link in links:
            # Extract relationship information
            relation_type = link.get('link_type', 'relates_to')  # Default to 'relates_to' if not specified
            
            # Get the related issue details
            related_issue = {
                'id': link.get('id'),
                'iid': link.get('iid'),
                'project_id': link.get('project_id'),
                'title': link.get('title', ''),
                'state': link.get('state', ''),
                'reference': link.get('reference', '')
            }
            
            # Add to our relationships list
            relationship = {
                'source_issue_iid': issue_iid,
                'source_issue_title': issue_title,
                'target_issue_iid': related_issue['iid'],
                'target_issue_title': related_issue['title'],
                'relationship_type': relation_type,
                'relationship_description': relationship_types.get(relation_type, relation_type),
                'relationship_source': 'api_link'
            }
            
            # Add project information if the related issue is from a different project
            if str(related_issue['project_id']) != project_id.split('%2F')[-1]:
                relationship['target_project_id'] = related_issue['project_id']
                
            relationships.append(relationship)
            relationship_count += 1
            
            if verbose:
                print(f"  Found API relationship: Issue #{issue_iid} {relationship_types.get(relation_type, relation_type)} Issue #{related_issue['iid']}")
        
        # 2. Check for relationships in the issue description using regex patterns
        for pattern, rel_type in relation_patterns.items():
            for match in re.finditer(pattern, issue_description):
                related_issue_iid = int(match.group(1))
                
                # Avoid self-references
                if related_issue_iid == issue_iid:
                    continue
                
                # Try to find the target issue title
                target_title = "Unknown issue title"
                target_project_id = None
                for target_issue in issues:
                    if target_issue['iid'] == related_issue_iid:
                        target_title = target_issue['title']
                        break
                
                relationship = {
                    'source_issue_iid': issue_iid,
                    'source_issue_title': issue_title,
                    'target_issue_iid': related_issue_iid,
                    'target_issue_title': target_title,
                    'relationship_type': rel_type,
                    'relationship_description': relationship_types.get(rel_type, rel_type),
                    'relationship_source': 'description_text'
                }
                
                if target_project_id:
                    relationship['target_project_id'] = target_project_id
                
                relationships.append(relationship)
                relationship_count += 1
                
                if verbose:
                    print(f"  Found text relationship: Issue #{issue_iid} {relationship_types.get(rel_type, rel_type)} Issue #{related_issue_iid}")
        
        # 3. Fetch and check issue comments for relationships
        if verbose:
            print(f"  Checking comments for issue #{issue_iid}")
            
        comments_url = f"{api_endpoint}/projects/{project_id}/issues/{issue_iid}/notes"
        comments = paginated_api_call(comments_url, headers, {}, f"fetching comments for issue #{issue_iid}", verbose)
        
        for comment in comments:
            comment_body = comment.get('body', '') or ''
            
            for pattern, rel_type in relation_patterns.items():
                for match in re.finditer(pattern, comment_body):
                    related_issue_iid = int(match.group(1))
                    
                    # Avoid self-references
                    if related_issue_iid == issue_iid:
                        continue
                    
                    # Try to find the target issue title
                    target_title = "Unknown issue title"
                    target_project_id = None
                    for target_issue in issues:
                        if target_issue['iid'] == related_issue_iid:
                            target_title = target_issue['title']
                            break
                    
                    relationship = {
                        'source_issue_iid': issue_iid,
                        'source_issue_title': issue_title,
                        'target_issue_iid': related_issue_iid,
                        'target_issue_title': target_title,
                        'relationship_type': rel_type,
                        'relationship_description': relationship_types.get(rel_type, rel_type),
                        'relationship_source': 'comment_text'
                    }
                    
                    if target_project_id:
                        relationship['target_project_id'] = target_project_id
                    
                    relationships.append(relationship)
                    relationship_count += 1
                    
                    if verbose:
                        print(f"  Found comment relationship: Issue #{issue_iid} {relationship_types.get(rel_type, rel_type)} Issue #{related_issue_iid}")
    
    # Remove duplicate relationships (same source, target and type)
    unique_relationships = {}
    for rel in relationships:
        key = (rel['source_issue_iid'], rel['target_issue_iid'], rel['relationship_type'])
        # Prefer API relationships over text relationships
        if key not in unique_relationships or rel.get('relationship_source') == 'api_link':
            unique_relationships[key] = rel
    
    unique_relationships_list = list(unique_relationships.values())
    
    print(f"Found {relationship_count} relationships across {processed_count} issues")
    print(f"After removing duplicates: {len(unique_relationships_list)} unique relationships")
    return unique_relationships_list

def save_relationships_to_map(relationships, output_file="relationships-map.csv"):
    """
    Save issue relationships to a CSV map file for later processing.
    
    Args:
        relationships: List of relationship dictionaries
        output_file: Path to the output file
        
    Returns:
        Number of relationships saved
    """
    # Get GitLab and GitHub repo information for URL construction
    gitlab_repo_url = os.environ.get('GITLAB_REPO_URL')
    github_repo_url = os.environ.get('GITHUB_REPO_URL', '')
    
    # Extract necessary info from repo URLs
    gitlab_info = None
    github_info = None
    
    try:
        gitlab_info = get_gitlab_project_info(gitlab_repo_url)
    except ValueError as e:
        print(f"Warning: {str(e)}")
        
    try:
        if github_repo_url:
            github_info = get_github_repo_info(github_repo_url)
    except ValueError as e:
        print(f"Warning: {str(e)}")
    
    # Define CSV header - including GitLab and GitHub URLs and validation
    headers = [
        "gitlab_source_issue_iid", 
        "gitlab_target_issue_iid",
        "gitlab_relationship_type",
        "github_relationship_action",
        "relationship_source", 
        "target_project_id",
        "gitlab_source_url",
        "gitlab_target_url",
        "github_source_url",
        "github_target_url",
        "target_url_valid",
        "status"
    ]
    
    print(f"\nSaving relationship map to {output_file}...")
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for rel in relationships:
                source_iid = rel['source_issue_iid']
                target_iid = rel['target_issue_iid']
                rel_type = rel['relationship_type']
                rel_source = rel.get('relationship_source', 'unknown')
                target_project_id = rel.get('target_project_id', '')
                
                gitlab_source_url = ""
                gitlab_target_url = ""
                github_source_url = ""
                github_target_url = ""
                target_url_valid = "not_checked"
                
                if gitlab_info:
                    gitlab_host = urlparse(gitlab_repo_url).hostname
                    gitlab_source_url = f"https://{gitlab_host}/{gitlab_info['namespace']}/{gitlab_info['project']}/-/issues/{source_iid}"
                    
                    # Construct target URL based on whether it's cross-project
                    if target_project_id and target_project_id != gitlab_info['project_id']:
                        gitlab_target_url = f"https://{gitlab_host}/{target_project_id}/-/issues/{target_iid}"
                    else:
                        gitlab_target_url = f"https://{gitlab_host}/{gitlab_info['namespace']}/{gitlab_info['project']}/-/issues/{target_iid}"
                
                if github_info:
                    github_host = urlparse(github_repo_url).hostname
                    github_source_url = f"https://{github_host}/{github_info['owner']}/{github_info['repo']}/issues/{source_iid}"
                    
                    # For cross-project relationships, we need to parse the target URL
                    if target_project_id and gitlab_info and target_project_id != gitlab_info['project_id']:
                        parsed_target = urlparse(gitlab_target_url)
                        target_path_parts = parsed_target.path.strip('/').split('/-/issues/')
                        if len(target_path_parts) == 2:
                            target_repo_path = target_path_parts[0]
                            target_issue_num = target_path_parts[1]
                            # This is a big assumption about the GH repo name matching the GL repo name
                            github_target_url = f"https://{github_host}/{target_repo_path}#{target_issue_num}"
                        else:
                            github_target_url = gitlab_target_url # fallback
                    else:
                        github_target_url = f"https://{github_host}/{github_info['owner']}/{github_info['repo']}/issues/{target_iid}"
                
                # Validate target URL if it's a full URL
                if github_target_url.startswith('http'):
                    target_url_valid = "valid" if validate_url(github_target_url) else "invalid"
                
                # Determine the GitHub action
                relationship_type = rel['relationship_type']
                if relationship_type == 'blocks':
                    github_action = 'Blocking'
                elif relationship_type in ['is_blocked_by', 'blocked_by', 'depends_on', 'relates_to']:
                    github_action = 'Blocked by'
                else:
                    github_action = 'Comment'
                
                row = {
                    "gitlab_source_issue_iid": source_iid,
                    "gitlab_target_issue_iid": target_iid,
                    "gitlab_relationship_type": rel_type,
                    "github_relationship_action": github_action,
                    "relationship_source": rel_source,
                    "target_project_id": target_project_id,
                    "gitlab_source_url": gitlab_source_url,
                    "gitlab_target_url": gitlab_target_url,
                    "github_source_url": github_source_url,
                    "github_target_url": github_target_url,
                    "target_url_valid": target_url_valid,
                    "status": "pending"
                }
                writer.writerow(row)
            
            print(f"Successfully saved {len(relationships)} relationships to {output_file}")
            return len(relationships)
            
    except Exception as e:
        print(f"An error occurred while saving the relationship map: {e}")
        return 0

def get_issue_details(owner, repo, issue_number, github_token, verbose=False):
    """
    Get details for a GitHub issue, including its global ID and whether it's a pull request.
    
    Args:
        owner: GitHub repository owner
        repo: GitHub repository name
        issue_number: Issue number
        github_token: GitHub API token
        verbose: Whether to print verbose output
        
    Returns:
        A dictionary {'id': int, 'is_pull_request': bool} or None if not found.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }
    
    if verbose:
        print(f"Fetching details for issue/PR #{issue_number} in {owner}/{repo}...")
        
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            details = {
                'id': data.get('id'),
                'is_pull_request': 'pull_request' in data
            }
            if verbose:
                type = "Pull Request" if details['is_pull_request'] else "Issue"
                print(f"Found #{issue_number} (Type: {type}, Global ID: {details['id']})")
            return details
        else:
            if verbose:
                print(f"Failed to fetch details for #{issue_number}. Status: {response.status_code}, Response: {response.text}")
            return None
    except Exception as e:
        if verbose:
            print(f"Exception while fetching details for #{issue_number}: {str(e)}")
        return None

def apply_issue_relationship(owner, repo, source_issue_number, target_issue_number,
                           relationship_type, github_token, verbose=False):
    """
    Apply relationship between GitHub issues by using the REST API.
    
    Returns:
        A dictionary {'success': bool, 'message': str}
    """
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
    }

    # Determine which issue is being blocked and which is the blocker
    blocked_issue_number, blocking_issue_number = None, None
    if relationship_type in ['is_blocked_by', 'blocked_by', 'depends_on', 'relates_to']:
        blocked_issue_number = source_issue_number
        blocking_issue_number = target_issue_number
    elif relationship_type == 'blocks':
        blocked_issue_number = target_issue_number
        blocking_issue_number = source_issue_number
    else:
        return {'success': False, 'message': f"Unsupported relationship type for dependency: {relationship_type}"}

    # Get details for both issues
    blocked_details = get_issue_details(owner, repo, blocked_issue_number, github_token, verbose)
    blocking_details = get_issue_details(owner, repo, blocking_issue_number, github_token, verbose)

    if not blocked_details or not blocking_details:
        return {'success': False, 'message': "Could not retrieve details for one or both issues."}

    # The API only works for issue-to-issue dependencies. If either is a PR, fail.
    if blocked_details['is_pull_request'] or blocking_details['is_pull_request']:
        return {'success': False, 'message': "Dependencies can only be created between issues, not pull requests."}

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{blocked_issue_number}/dependencies/blocked_by"
    payload = {'issue_id': blocking_details['id']}

    if verbose:
        print(f"Applying dependency: Issue #{blocked_issue_number} is blocked by Issue #{blocking_issue_number} (Global ID: {blocking_details['id']})")
        print(f"POSTing to: {url}")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        
        if response.status_code == 201:
            return {'success': True, 'message': "Applied successfully"}
        else:
            error_details = response.json()
            error_message = error_details.get('message', 'No message provided')
            error_docs = error_details.get('documentation_url', 'No documentation link')
            return {'success': False, 'message': f"API Error: {error_message} (Status: {response.status_code}). See: {error_docs}"}
            
    except Exception as e:
        return {'success': False, 'message': f"Exception: {str(e)}"}


def add_comment_fallback(owner, repo, source_issue_number, target_issue_number, 
                         relationship_type, github_token, verbose=False):
    """
    Fallback to add a comment for relationships not supported by dependency API.
    
    Returns:
        A dictionary {'success': bool, 'message': str}
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{source_issue_number}/comments"
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    relationship_text_map = {
        'relates_to': 'Related to',
        'duplicates': 'Duplicates',
        'is_duplicated_by': 'Is duplicated by',
        'duplicated_by': 'Is duplicated by',
        'child_of': 'Is a subtask of',
        'parent_of': 'Has subtask',
        'referenced': 'References',
        'referenced_by': 'Is referenced by',
        'linked': 'Is linked to'
    }
    
    relationship_text = relationship_text_map.get(relationship_type, 'Related to')
    body = f"{relationship_text} #{target_issue_number}"
    body += "\n\n> *This relationship was automatically migrated from GitLab as a comment.*"
    
    payload = {'body': body}
    
    if verbose:
        print(f"Creating comment on issue #{source_issue_number}: '{body}'")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 201:
            return {'success': True, 'message': "Comment added successfully"}
        else:
            return {'success': False, 'message': f"Failed to create comment. Status: {response.status_code}, Response: {response.text}"}
    except Exception as e:
        return {'success': False, 'message': f"Exception while creating comment: {str(e)}"}

def save_diagnostic_report(input_file, results, github_repo_info, report_file):
    """
    Save diagnostic report to a file.
    
    Args:
        input_file: Path to the input map file used for the diagnostic
        results: Results tuple from apply_relationships_from_map
        github_repo_info: Dictionary with GitHub repository information
        report_file: Path to save the report to
    """
    success_count, error_count, not_found_count, skipped_count = results
    
    # Create relationships summary by type
    relationship_counts = {}
    try:
        with open(input_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                rel_type = row.get('gitlab_relationship_type', 'unknown')
                relationship_counts[rel_type] = relationship_counts.get(rel_type, 0) + 1
    except Exception as e:
        relationship_counts = {"error": f"Could not analyze relationship types: {str(e)}"}
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# GitLab to GitHub Issue Relationships - Diagnostic Report\n\n")
        f.write(f"Report generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"- Input file: {input_file}\n")
        f.write(f"- Target GitHub repository: {github_repo_info['owner']}/{github_repo_info['repo']}\n")
        f.write(f"- Total relationships: {success_count + error_count + not_found_count + skipped_count}\n")
        f.write(f"- Would apply: {success_count}\n")
        f.write(f"- Would skip (already applied): {skipped_count}\n")
        f.write(f"- Issues not found: {not_found_count}\n")
        f.write(f"- Potential errors: {error_count}\n\n")
        
        f.write("## Relationship Types\n\n")
        for rel_type, count in relationship_counts.items():
            f.write(f"- {rel_type}: {count}\n")
        
        f.write("\n## Next Steps\n\n")
        f.write("1. Review the report and make any necessary adjustments to the mapping file.\n")
        f.write("2. Run with `--diagnostic` again to verify your changes.\n")
        f.write("3. When ready, run without `--diagnostic` to apply the relationships.\n")
        
        f.write("\n## Notes\n\n")
        if not_found_count > 0:
            f.write("- Some GitLab issues were not found in GitHub. You may need to review your issue migration process.\n")
        
        f.write("\n*Generated by gitlab-relationship-mapper.py*\n")

def apply_relationships_from_map(input_file="relationships-map.csv", github_repo_info=None, 
                               github_token=None, verbose=False, diagnostic=False, summary_only=False,
                               skip_url_validation=False, include_cross_project=True):
    """
    Apply issue relationships to GitHub issues based on the relationship map.
    
    Args:
        input_file: Path to the input map file
        github_repo_info: Dictionary with GitHub repo owner and name
        github_token: GitHub API token
        verbose: Whether to print verbose output
        diagnostic: If True, run in diagnostic mode without making any changes
        summary_only: If True, only show summary information in diagnostic mode
        skip_url_validation: If True, skip URL validation checks when applying relationships
        include_cross_project: If True (default), include cross-project relationships
        
    Returns:
        Tuple of (success_count, error_count, not_found_count, skipped_count)
    """
    if diagnostic:
        print("\n" + "=" * 80)
        print("=== RUNNING IN DIAGNOSTIC MODE - NO CHANGES WILL BE MADE ===".center(80))
        print("=" * 80 + "\n")
        # In diagnostic mode, we'll be more verbose
        verbose = True
    
    print(f"\nReading relationship map from {input_file}...")
    
    owner = github_repo_info['owner']
    repo = github_repo_info['repo']
    
    success_count = 0
    error_count = 0
    skipped_count = 0
    not_found_count = 0
    cross_project_count = 0
    
    try:
        # Read the relationship map
        with open(input_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            relationships = list(reader)
            print(f"Found {len(relationships)} relationships in map file")
            
        print(f"Applying relationships to GitHub issues in repository: {owner}/{repo}\n")
        
        # Print header for the progress table
        if not summary_only:
            print("Applying relationships...")
            print("=" * 80)
            print(f"{'GitLab Source':<20} {'GitLab Target':<20} {'Relationship':<15} {'Status'}")
            print("-" * 80)

        for rel in relationships:
            source_issue_iid = rel.get('gitlab_source_issue_iid')
            target_issue_iid = rel.get('gitlab_target_issue_iid')
            relationship_type = rel.get('gitlab_relationship_type')
            github_action = rel.get('github_relationship_action', 'Comment')
            
            target_owner, target_repo = owner, repo
            
            # Simplified logic: always assume the target is in the same repo
            # This corrects the bug where invalid cross-project URLs were being used
            target_issue_number = int(target_issue_iid)

            if verbose and not summary_only:
                print(f"Processing: Source #{source_issue_iid} -> Target #{target_issue_iid} ({relationship_type})")

            # Since we are using REST API, we don't need to pre-fetch issues or node IDs.
            # The API will tell us if an issue doesn't exist.
            status_message = ""
            if not diagnostic:
                result = None
                if github_action in ['Blocked by', 'Blocking']:
                    result = apply_issue_relationship(owner, repo, int(source_issue_iid), target_issue_number, relationship_type, github_token, verbose)
                else: # Fallback to comment
                    result = add_comment_fallback(owner, repo, int(source_issue_iid), target_issue_number, relationship_type, github_token, verbose)

                if result and result['success']:
                    success_count += 1
                    status_message = result['message']
                else:
                    error_count += 1
                    status_message = result['message'] if result else "Unknown error"
            else: # Diagnostic mode
                # In diagnostic mode, we just check if the action is valid
                if github_action in ['Blocked by', 'Blocking', 'Comment']:
                    success_count += 1
                    status_message = f"Would be applied as '{github_action}'"
                else:
                    error_count += 1
                    status_message = f"Unknown github_relationship_action: {github_action}"

            if not summary_only:
                print(f"#{source_issue_iid:<19} #{target_issue_iid:<19} {relationship_type:<15} {status_message}")

        if not summary_only:
            print("=" * 80)

        print("\nRelationship application summary:")
        print(f"  - Successfully applied: {success_count}")
        print(f"  - Errors: {error_count}")
        print(f"  - Skipped (invalid target URL): {skipped_count}")
        print(f"  - Not found in map: {not_found_count}")
        print(f"  - Cross-project relationships processed: {cross_project_count}")

        return (success_count, error_count, not_found_count, skipped_count)
            
    except FileNotFoundError:
        print(f"Error: Input file '{input_file}' not found.")
        return (0, 0, 0, 0)
    
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return (0, 0, 0, 0)

def apply_relationships(input_file="relationships-map.csv", verbose=False, diagnostic=False, 
                    report_file=None, skip_github_validation=False, summary_only=False,
                    skip_url_validation=False, exclude_cross_project=False):
    """
    Main function to apply relationships between GitHub issues.
    
    This function reads the relationship map file created by the 'create-map' command
    and applies the relationships to GitHub issues by adding comments. In diagnostic mode,
    it simulates what would happen without making any actual changes to GitHub.
    
    Args:
        input_file: Path to the input map file
        verbose: Whether to print verbose output
        diagnostic: If True, run in diagnostic mode without making any changes.
                   In diagnostic mode, the script will analyze the mapping file and report
                   what actions would be taken, but will not create any comments or modify
                   any issues in GitHub.
        report_file: If provided, save the diagnostic report to this file
        skip_github_validation: If True, skip GitHub validation in diagnostic mode
        summary_only: If True, only show summary information in diagnostic mode
        skip_url_validation: If True, skip URL validation when applying relationships
        exclude_cross_project: If True, exclude cross-project relationships (default: False)
        
    Returns:
        Tuple of (success_count, error_count, not_found_count, skipped_count)
    """
    if diagnostic:
        print("\nAnalyzing issue relationships in diagnostic mode...")
    else:
        print("\nApplying issue relationships from GitLab to GitHub...")
    
    # Validate environment variables, but skip GitHub validation if requested in diagnostic mode
    if diagnostic and skip_github_validation:
        validate_env_vars('create')  # Only validate GitLab environment variables
        github_token = "DIAGNOSTIC_MODE_NO_TOKEN"
        github_repo_info = {
            "owner": "diagnostic-owner",
            "repo": "diagnostic-repo"
        }
    else:
        # Regular validation and setup
        validate_env_vars('apply-relationships')
        
        # Get environment variables
        github_token = os.environ.get('GITHUB_TOKEN')
        github_repo_url = os.environ.get('GITHUB_REPO_URL')
        
        # Get GitHub repository information
        github_repo_info = get_github_repo_info(github_repo_url)
    
    # Apply relationships or run diagnostic
    results = apply_relationships_from_map(input_file, github_repo_info, github_token, 
                                       verbose, diagnostic, summary_only,
                                       skip_url_validation, not exclude_cross_project)
    
    # If we're in diagnostic mode and a report file is specified, save the report
    if diagnostic and report_file:
        save_diagnostic_report(input_file, results, github_repo_info, report_file)
        print(f"\nDiagnostic report saved to {report_file}")
    
    return results

def create_relationship_map(output_file="relationships-map.csv", verbose=False):
    """
    Create a map of GitLab issue relationships.
    
    Args:
        output_file: Path to the output file
        verbose: Whether to print verbose output
        
    Returns:
        Number of relationships saved
    """
    print("\nCreating GitLab issue relationship map...")
    
    # Validate environment variables
    validate_env_vars('create')
    
    # Get environment variables
    gitlab_api_token = os.environ.get('GITLAB_API_PRIVATE_TOKEN')
    gitlab_api_endpoint = os.environ.get('GITLAB_API_ENDPOINT')
    gitlab_repo_url = os.environ.get('GITLAB_REPO_URL')
    
    # Get GitLab project info
    project_info = get_gitlab_project_info(gitlab_repo_url)
    
    # Fetch issues from GitLab
    issues = fetch_gitlab_issues(gitlab_api_endpoint, project_info['project_id'], gitlab_api_token, verbose)
    
    # Get relationships between issues
    relationships = get_issue_relationships(gitlab_api_endpoint, project_info['project_id'], 
                                         issues, gitlab_api_token, verbose)
    
    # Save relationships to map file
    return save_relationships_to_map(relationships, output_file)

def cleanup_csv_file(input_file, output_file=None):
    """
    Clean up an existing CSV file to remove unnecessary columns.
    
    Args:
        input_file: Path to the input CSV file
        output_file: Path to the output file (default: overwrite input file)
        
    Returns:
        Number of rows processed
    """
    if output_file is None:
        output_file = input_file
    
    print(f"\nCleaning up CSV file {input_file}...")
    
    # Essential fields we want to keep
    essential_fields = [
        "gitlab_source_issue_iid", 
        "gitlab_target_issue_iid",
        "gitlab_relationship_type",
        "relationship_source", 
        "target_project_id",
        "gitlab_source_url",
        "gitlab_target_url",
        "github_source_url",
        "github_target_url",
        "target_url_valid",
        "status"
    ]
    
    try:
        # Read the existing file
        rows = []
        existing_fields = []
        with open(input_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            existing_fields = reader.fieldnames
            rows = list(reader)
        
        # Determine which fields to keep (intersection of essential and existing)
        fields_to_keep = [field for field in essential_fields if field in existing_fields]
        
        # Add any missing fields that are in our essential list but not in the existing file
        missing_fields = [field for field in essential_fields if field not in existing_fields]
        
        if missing_fields:
            print(f"Adding missing fields to the CSV file: {', '.join(missing_fields)}")
            fields_to_keep.extend(missing_fields)
            
            # Add default values for the missing fields
            for row in rows:
                for field in missing_fields:
                    if field in ["gitlab_source_url", "gitlab_target_url", "github_source_url", "github_target_url"]:
                        row[field] = ""
                    elif field == "target_url_valid":
                        row[field] = "false"
                    else:
                        row[field] = ""
        
        # Write the cleaned file
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fields_to_keep)
            writer.writeheader()
            
            # Clean each row
            for row in rows:
                cleaned_row = {field: row.get(field, '') for field in fields_to_keep}
                writer.writerow(cleaned_row)
        
        print(f"Successfully cleaned up {len(rows)} rows, keeping these columns:")
        for field in fields_to_keep:
            print(f"  - {field}")
            
        print(f"Cleaned file saved to {output_file}")
        
        return len(rows)
    except Exception as e:
        print(f"Error cleaning up CSV file: {str(e)}")
        return 0

def main():
    parser = argparse.ArgumentParser(
        description='GitLab/GitHub Issue Relationships Tool')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Create map command
    create_parser = subparsers.add_parser('create-map', 
                                         help='Read issues and their relationships from GitLab and create a mapping file')
    create_parser.add_argument('--verbose', action='store_true',
                            help='Show more detailed information about each issue/relationship')
    create_parser.add_argument('--output', type=str, default='relationships-map.csv',
                            help='Specify output file for the relationship map')
    
    # Apply relationships command
    apply_parser = subparsers.add_parser('apply-relationships',
                                       help='Apply issue relationships to GitHub issues based on the mapping file')
    apply_parser.add_argument('--verbose', action='store_true',
                           help='Show more detailed information during the process')
    apply_parser.add_argument('--input', type=str, default='relationships-map.csv',
                           help='Specify input file for the relationship map')
    apply_parser.add_argument('--diagnostic', action='store_true',
                           help='Run in diagnostic mode without making any changes. This will show what would happen without modifying any GitHub issues.')
    apply_parser.add_argument('--report-file', type=str,
                           help='Save diagnostic report to specified file (only used with --diagnostic)')
    apply_parser.add_argument('--skip-github-validation', action='store_true',
                           help='Skip GitHub validation in diagnostic mode (useful if you don\'t have GitHub credentials yet)')
    apply_parser.add_argument('--summary-only', action='store_true', 
                           help='Show only summary information in diagnostic mode, not individual relationships')
    apply_parser.add_argument('--skip-url-validation', action='store_true',
                           help='Skip URL validation when applying relationships (use with caution)')
    apply_parser.add_argument('--exclude-cross-project', action='store_true',
                           help='Exclude cross-project relationships (by default, cross-project relationships are included)')
    
    # Clean CSV command
    clean_parser = subparsers.add_parser('clean-csv',
                                      help='Clean up an existing CSV file to remove unnecessary columns')
    clean_parser.add_argument('--input', type=str, required=True,
                           help='Specify input CSV file to clean')
    clean_parser.add_argument('--output', type=str,
                           help='Specify output file (default: overwrite input file)')
    
    args = parser.parse_args()
    
    # If no command is provided, show help
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == 'create-map':
            # Create relationship map
            create_relationship_map(args.output, args.verbose)
            
        elif args.command == 'apply-relationships':
            # Apply relationships to GitHub issues
            apply_relationships(args.input, args.verbose, args.diagnostic, 
                              args.report_file, args.skip_github_validation, args.summary_only,
                              args.skip_url_validation, args.exclude_cross_project)
        
        elif args.command == 'clean-csv':
            # Clean up CSV file
            cleanup_csv_file(args.input, args.output)
            
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
        
    return 0

if __name__ == '__main__':
    exit(main())
