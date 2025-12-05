#!/usr/bin/env python3
"""
GitLab Comments and Issues Mapper

This script helps with managing issue comments between GitLab and GitHub.

Usage:
    python gitlab-comment-mapper.py create-map [--verbose] [--output FILE]
    python gitlab-comment-mapper.py apply-nesting [--verbose] [--diagnostic]

Environment Variables Required:
    GITLAB_API_PRIVATE_TOKEN - GitLab API Private Token
    GITLAB_API_ENDPOINT - GitLab API Endpoint URL (e.g., https://gitlab.com/api/v4)
    GITLAB_REPO_URL - GitLab repository URL (e.g., https://gitlab.com/namespace/project)
    
For apply-nesting mode, all variables are required:
    GITLAB_API_PRIVATE_TOKEN - GitLab API Private Token
    GITLAB_API_ENDPOINT - GitLab API Endpoint URL
    GITLAB_REPO_URL - GitLab repository URL
    GITHUB_TOKEN - GitHub API Token
    GITHUB_REPO_URL - GitHub repository URL

Commands:
    create-map          - Read issue comments from GitLab and create a mapping file
    apply-nesting      - Find GitLab issues with comments, and apply them to corresponding GitHub issues

Options:
    --verbose           - Show more detailed information about each comment/issue
    --output FILE       - Specify output file for the comment map (default: comments-map.csv)
    --input FILE        - Specify input file for the comment map (default: comments-map.csv)
    --diagnostic        - Run in diagnostic mode without making any changes (for apply-nesting command)
"""

import os
import json
import argparse
import requests
import time
import csv
from datetime import datetime
from urllib.parse import urlparse, quote
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def validate_env_vars(mode='create'):
    """
    Validate required environment variables are set.
    
    Args:
        mode: 'create' for GitLab validation,
              'apply-nesting' for both GitLab and GitHub validation
    """
    if mode == 'create':
        required_vars = ['GITLAB_API_PRIVATE_TOKEN', 'GITLAB_API_ENDPOINT', 'GITLAB_REPO_URL']
    elif mode == 'apply-nesting':
        required_vars = ['GITLAB_API_PRIVATE_TOKEN', 'GITLAB_API_ENDPOINT', 
                         'GITLAB_REPO_URL', 'GITHUB_TOKEN', 'GITHUB_REPO_URL']
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
    if len(gitlab_path_parts) > 2:
        # Multi-level group
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
        print(f"Making paginated API call to {url} (page {page}, per_page {per_page})...")
    
    while True:
        params['page'] = page
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                page_results = response.json()
                
                if not page_results:
                    # No more results
                    break
                    
                results.extend(page_results)
                
                # Check if there are more pages
                if 'next' in response.links and 'url' in response.links['next']:
                    # Extract page from next URL or just increment
                    page += 1
                else:
                    # No more pages
                    break
            else:
                print(f"Error {error_prefix}: {response.status_code} - {response.text}")
                break
                
        except Exception as e:
            print(f"Exception {error_prefix}: {str(e)}")
            break
            
        if verbose:
            print(f"Retrieved page {page-1} with {len(page_results)} results")
    
    if verbose:
        print(f"Total results: {len(results)}")
        
    return results

def fetch_gitlab_issues(api_endpoint, project_id, api_token, verbose=False):
    """
    Fetch all issues from a GitLab project.
    
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

def get_issue_discussions(api_endpoint, project_id, issues, api_token, verbose=False):
    """
    Get comments for all issues, preserving discussion threads.
    
    Args:
        api_endpoint: GitLab API endpoint URL
        project_id: URL-encoded project ID
        issues: List of GitLab issues
        api_token: GitLab API private token
        verbose: Whether to print verbose output
        
    Returns:
        List of comments with discussion thread information
    """
    print("\nFetching issue discussions and comments...")
    
    headers = {
        'PRIVATE-TOKEN': api_token
    }
    
    all_comments = []
    issue_count_with_comments = 0
    total_comment_count = 0
    processed_count = 0
    total_issues = len(issues)
    
    # Loop through each issue to find discussions
    for i, issue in enumerate(issues):
        issue_iid = issue['iid']
        issue_id = issue['id']
        issue_title = issue['title']
        
        # Progress indicator
        processed_count += 1
        if verbose or processed_count % 10 == 0 or processed_count == total_issues:
            print(f"Processing issue {processed_count}/{total_issues}: #{issue_iid} - {issue_title}")
        
        # Get discussions for the issue
        url = f"{api_endpoint}/projects/{project_id}/issues/{issue_iid}/discussions"
        params = {
            'per_page': 100,
            'page': 1
        }
        
        discussions = paginated_api_call(url, headers, params, f"fetching discussions for issue #{issue_iid}", verbose)
        
        if not discussions:
            continue

        issue_had_comments = False
        
        # Each discussion is a thread
        for discussion in discussions:
            notes = discussion.get('notes', [])
            if not notes:
                continue

            # The first note in a discussion is the parent
            parent_note = notes[0]
            parent_comment_id = parent_note['id']

            # Process all notes in the thread
            for note in notes:
                # Skip system notes
                if note.get('system', False):
                    continue

                if not issue_had_comments:
                    issue_count_with_comments += 1
                    issue_had_comments = True
                
                total_comment_count += 1

                # Determine if the note is a reply
                is_reply = note['id'] != parent_comment_id
                
                comment_info = {
                    'gitlab_issue_id': issue_id,
                    'gitlab_issue_iid': issue_iid,
                    'gitlab_issue_title': issue_title[:15],
                    'gitlab_comment_id': note['id'],
                    'gitlab_parent_comment_id': parent_comment_id if is_reply else '',
                    'gitlab_comment_body': note['body'][:40],
                    'gitlab_comment_author': note.get('author', {}).get('username', 'unknown'),
                    'gitlab_comment_created_at': note.get('created_at', ''),
                    'gitlab_comment_updated_at': note.get('updated_at', ''),
                    'gitlab_comment_system': note.get('system', False),
                    'github_issue_number': '',  # Will be filled in later
                    'github_comment_id': '',    # Will be filled in later
                    'status': 'not_processed'
                }
                
                all_comments.append(comment_info)
                
                if verbose:
                    reply_info = f" (reply to #{comment_info['gitlab_parent_comment_id']})" if is_reply else ""
                    print(f"  Comment #{note['id']} by {comment_info['gitlab_comment_author']}{reply_info}")
                    print(f"  {comment_info['gitlab_comment_body'][:50]}...")
    
    print(f"Found {total_comment_count} comments in discussions across {issue_count_with_comments} issues")
    return all_comments

def print_comments(comments, verbose=False):
    """
    Print comment information in a readable format.
    
    Args:
        comments: List of comment dictionaries
        verbose: Whether to print verbose information
    """
    print(f"\nFound {len(comments)} comments:\n")
    print("=" * 80)
    
    for i, comment in enumerate(comments, 1):
        issue_iid = comment['gitlab_issue_iid']
        issue_title = comment['gitlab_issue_title']
        author = comment['gitlab_comment_author']
        created_at = comment['gitlab_comment_created_at']
        parent_id = comment.get('gitlab_parent_comment_id')
        
        reply_info = f" (in reply to #{parent_id})" if parent_id else ""
        print(f"{i}. Comment by {author} on issue #{issue_iid} ({issue_title}) at {created_at}{reply_info}")
        
        if verbose:
            print(f"   ID: {comment['gitlab_comment_id']}")
            print(f"   Content: {comment['gitlab_comment_body'][:100]}...")
            print(f"   System comment: {comment['gitlab_comment_system']}")
            print()
        
        print("-" * 80)

def save_comments_to_map(comments, output_file="comments-map.csv"):
    """
    Save comments to a CSV map file for later processing.
    
    Args:
        comments: List of comment dictionaries
        output_file: Path to the output file
        
    Returns:
        Number of comments saved
    """
    # Define CSV header
    headers = [
        "gitlab_issue_id", "gitlab_issue_iid", "gitlab_issue_title",
        "gitlab_comment_id", "gitlab_parent_comment_id", "gitlab_comment_body", 
        "gitlab_comment_author", "gitlab_comment_created_at", "gitlab_comment_updated_at",
        "gitlab_comment_system", "github_issue_number", "github_comment_id",
        "status"
    ]
    
    print(f"\nSaving comment map to {output_file}...")
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            # Write each comment row
            for comment in comments:
                writer.writerow(comment)
                
        print(f"Successfully saved {len(comments)} comments to {output_file}")
        return len(comments)
        
    except Exception as e:
        print(f"Error saving comment map: {str(e)}")
        return 0

def get_github_comment(owner, repo, comment_id, github_token, verbose=False):
    """
    Get a GitHub comment by its ID.
    
    Args:
        owner: GitHub repository owner
        repo: GitHub repository name
        comment_id: Comment ID
        github_token: GitHub API token
        verbose: Whether to print verbose output
        
    Returns:
        Dictionary with comment data or None if comment not found
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    try:
        if verbose:
            print(f"Fetching GitHub comment #{comment_id}...")
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            comment = response.json()
            
            if verbose:
                print(f"Successfully fetched comment #{comment_id}")
                
            return comment
        else:
            print(f"Error fetching GitHub comment #{comment_id}: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Exception fetching GitHub comment: {str(e)}")
        return None

def update_github_comment(owner, repo, comment_id, github_token, new_body, verbose=False):
    """
    Update an existing comment in a GitHub issue.
    
    Args:
        owner: GitHub repository owner
        repo: GitHub repository name
        comment_id: The ID of the comment to update
        github_token: GitHub API token
        new_body: The new body for the comment
        verbose: Whether to print verbose output
        
    Returns:
        Dictionary with updated comment data or None if update failed
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    data = {
        'body': new_body
    }
    
    try:
        if verbose:
            print(f"Updating GitHub comment #{comment_id}...")
        
        response = requests.patch(url, headers=headers, json=data)
        
        if response.status_code == 200:
            updated_comment = response.json()
            
            if verbose:
                print(f"Successfully updated comment with ID {updated_comment['id']}")
                
            return updated_comment
        else:
            print(f"Error updating GitHub comment: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Exception updating GitHub comment: {str(e)}")
        return None

def get_github_issue_comments(owner, repo, issue_number, github_token, verbose=False):
    """
    Get all comments for a GitHub issue.
    
    Args:
        owner: GitHub repository owner
        repo: GitHub repository name
        issue_number: Issue number
        github_token: GitHub API token
        verbose: Whether to print verbose output
        
    Returns:
        List of comments
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    params = {
        'per_page': 100,
        'page': 1
    }
    
    if verbose:
        print(f"Fetching all comments for GitHub issue #{issue_number}...")
        
    comments = paginated_api_call(url, headers, params, f"fetching comments for GitHub issue #{issue_number}", verbose)
    return comments

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
        if verbose:
            print(f"Fetching GitHub issue #{issue_number}...")
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            issue = response.json()
            
            if verbose:
                print(f"Successfully fetched issue #{issue_number} - {issue['title']}")
                
            return issue
        else:
            print(f"Error fetching GitHub issue #{issue_number}: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Exception fetching GitHub issue: {str(e)}")
        return None

def map_gitlab_to_github_issues(gitlab_issues, comment_map, github_repo_info, gitlab_repo_url, github_token, verbose=False, diagnostic=False):
    """
    Map GitLab issues to GitHub issues by title and create a map.
    
    Args:
        gitlab_issues: List of GitLab issues
        comment_map: Dictionary mapping GitLab issue IDs to comments
        github_repo_info: Dictionary with GitHub repository information
        gitlab_repo_url: GitLab repository URL
        github_token: GitHub API token
        verbose: Whether to print verbose output
        diagnostic: Whether to run in diagnostic mode
        
    Returns:
        Dictionary mapping GitLab issue IIDs to GitHub issue numbers
    """
    owner = github_repo_info['owner']
    repo = github_repo_info['repo']
    
    issue_map = {}
    
    print("\nMapping GitLab issues to GitHub issues...")
    
    # First, get all GitHub issues
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    params = {
        'state': 'all',
        'per_page': 100,
        'page': 1
    }
    
    github_issues = paginated_api_call(url, headers, params, "fetching GitHub issues", verbose)
    print(f"Found {len(github_issues)} GitHub issues")
    
    # Map GitLab issues to GitHub issues by title
    matched_count = 0
    
    for gitlab_issue in gitlab_issues:
        gitlab_iid = gitlab_issue['iid']
        gitlab_title = gitlab_issue['title']
        
        # Check if this issue has any comments in our map
        if not any(comment['gitlab_issue_iid'] == gitlab_iid for comment in comment_map):
            if verbose:
                print(f"Skipping GitLab issue #{gitlab_iid} as it has no comments in our map")
            continue
        
        # Try to find matching GitHub issue by title
        for github_issue in github_issues:
            github_title = github_issue['title']
            
            if gitlab_title.lower().strip() == github_title.lower().strip():
                issue_map[gitlab_iid] = github_issue['number']
                matched_count += 1
                
                if verbose:
                    print(f"Matched GitLab issue #{gitlab_iid} ('{gitlab_title}') to GitHub issue #{github_issue['number']} ('{github_title}')")
                break
    
    print(f"Matched {matched_count} GitLab issues with comments to GitHub issues")
    return issue_map

def apply_nesting_to_issues(input_file=None, verbose=False, diagnostic=False):
    """
    Apply comment nesting to existing GitHub issues based on the mapping file.
    This function finds replies and updates them to quote their parent comment.
    
    Args:
        input_file: Path to the input map file
        verbose: Whether to print verbose output
        diagnostic: Whether to run in diagnostic mode
        
    Returns:
        Tuple of (success_count, error_count, skipped_count)
    """
    input_file = input_file or "comments-map.csv"
    print(f"\nReading comment map from {input_file}...")
    
    # Validate environment variables
    validate_env_vars('apply-nesting')
    
    # Get environment variables
    gitlab_api_token = os.environ.get('GITLAB_API_PRIVATE_TOKEN')
    gitlab_api_endpoint = os.environ.get('GITLAB_API_ENDPOINT')
    gitlab_repo_url = os.environ.get('GITLAB_REPO_URL')
    github_token = os.environ.get('GITHUB_TOKEN')
    github_repo_url = os.environ.get('GITHUB_REPO_URL')
    
    # Get GitLab and GitHub repository information
    project_info = get_gitlab_project_info(gitlab_repo_url)
    github_repo_info = get_github_repo_info(github_repo_url)
    
    owner = github_repo_info['owner']
    repo = github_repo_info['repo']
    
    # Read the comment map
    gitlab_comments = []
    try:
        with open(input_file, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            gitlab_comments = list(reader)
    except Exception as e:
        print(f"Error reading comment map: {str(e)}")
        return (0, 0, 0)
    
    print(f"Found {len(gitlab_comments)} comments in map file")
    
    # Get all GitLab issues to map them to GitHub issues
    all_gitlab_issues = fetch_gitlab_issues(
        gitlab_api_endpoint, 
        project_info['project_id'], 
        gitlab_api_token, 
        verbose
    )
    
    # Map GitLab issues to GitHub issues by title
    gitlab_to_github_issue_map = map_gitlab_to_github_issues(
        all_gitlab_issues, 
        gitlab_comments,
        github_repo_info,
        gitlab_repo_url,
        github_token,
        verbose,
        diagnostic
    )
    
    if not gitlab_to_github_issue_map:
        print("No GitLab issues could be mapped to GitHub issues. Aborting.")
        return (0, 0, len(gitlab_comments))

    # Group GitLab comments by issue IID for efficient processing
    comments_by_issue = {}
    for comment in gitlab_comments:
        issue_iid = int(comment['gitlab_issue_iid'])
        if issue_iid not in comments_by_issue:
            comments_by_issue[issue_iid] = []
        comments_by_issue[issue_iid].append(comment)

    success_count = 0
    error_count = 0
    skipped_count = 0

    # Process each issue that has comments
    for gitlab_issue_iid, issue_comments in comments_by_issue.items():
        github_issue_number = gitlab_to_github_issue_map.get(gitlab_issue_iid)

        if not github_issue_number:
            print(f"Skipping {len(issue_comments)} comments for GitLab issue #{gitlab_issue_iid} (no matching GitHub issue found).")
            skipped_count += len(issue_comments)
            continue

        print(f"\nProcessing issue: GitLab #{gitlab_issue_iid} -> GitHub #{github_issue_number}")

        # Fetch all existing comments from the corresponding GitHub issue
        existing_github_comments = get_github_issue_comments(owner, repo, github_issue_number, github_token, verbose)
        if not existing_github_comments:
            print(f"Warning: No comments found on GitHub issue #{github_issue_number}. Cannot apply nesting.")
            skipped_count += len(issue_comments)
            continue
        
        # Create a map from GitLab comment ID to its existing GitHub comment data
        gitlab_to_github_comment_map = {}
        for gl_comment in issue_comments:
            # Construct the expected footer to find the matching comment
            expected_footer = f"*Imported from GitLab comment by @{gl_comment['gitlab_comment_author']} on {gl_comment['gitlab_comment_created_at']}*"
            
            found_match = False
            for gh_comment in existing_github_comments:
                if expected_footer in gh_comment['body']:
                    gitlab_to_github_comment_map[gl_comment['gitlab_comment_id']] = gh_comment
                    gl_comment['github_comment_id'] = gh_comment['id'] # Update map
                    found_match = True
                    break
            
            if not found_match:
                gl_comment['status'] = 'match_failed'
                error_count += 1
                if verbose:
                    print(f"  - Failed to match GitLab comment #{gl_comment['gitlab_comment_id']}")

        if verbose:
            print(f"  Matched {len(gitlab_to_github_comment_map)} out of {len(issue_comments)} comments for this issue.")

        # Now, iterate through replies and update them to quote their parent
        for gl_comment in issue_comments:
            parent_gitlab_id = gl_comment.get('gitlab_parent_comment_id')
            
            # Process only if it's a reply and has not been processed
            if not parent_gitlab_id or gl_comment.get('status') == 'nesting_applied':
                continue

            # Find the GitHub comment for this reply
            reply_gh_comment = gitlab_to_github_comment_map.get(gl_comment['gitlab_comment_id'])
            if not reply_gh_comment:
                continue # Match failed earlier

            # Find the GitHub comment for its parent
            parent_gh_comment = gitlab_to_github_comment_map.get(parent_gitlab_id)
            if not parent_gh_comment:
                print(f"  - Warning: Cannot apply nesting for reply #{reply_gh_comment['id']}. Parent comment not found in GitHub.")
                gl_comment['status'] = 'parent_match_failed'
                error_count += 1
                continue

            # Check if the comment has already been updated with a quote
            if reply_gh_comment['body'].lstrip().startswith('>'):
                if verbose:
                    print(f"  - Skipping GitHub comment #{reply_gh_comment['id']}. Already appears to be a quote reply.")
                gl_comment['status'] = 'nesting_applied'
                skipped_count += 1
                continue

            if diagnostic:
                print(f"  [DIAGNOSTIC] Would update GitHub comment #{reply_gh_comment['id']} to quote comment #{parent_gh_comment['id']}")
                success_count += 1
                gl_comment['status'] = 'nesting_applied'
                continue

            # Construct the new body with a quote, preserving the original reply body
            quoted_parent = "> " + "\n> ".join(parent_gh_comment['body'].splitlines())
            new_body = f"{quoted_parent}\n\n{reply_gh_comment['body']}"

            # Update the comment in GitHub
            updated_comment = update_github_comment(owner, repo, reply_gh_comment['id'], github_token, new_body, verbose)

            if updated_comment:
                print(f"  - Successfully applied nesting to GitHub comment #{reply_gh_comment['id']}")
                gl_comment['status'] = 'nesting_applied'
                success_count += 1
            else:
                print(f"  - Failed to update GitHub comment #{reply_gh_comment['id']}")
                gl_comment['status'] = 'update_failed'
                error_count += 1
            
            time.sleep(1) # Avoid rate limiting

    # Write the updated comment map back to the file
    try:
        with open(input_file, 'w', newline='', encoding='utf-8') as csvfile:
            # Ensure fieldnames are read from the original file if possible
            original_fieldnames = gitlab_comments[0].keys() if gitlab_comments else []
            writer = csv.DictWriter(csvfile, fieldnames=original_fieldnames)
            writer.writeheader()
            writer.writerows(gitlab_comments)
            
        print(f"\nNesting application summary:")
        print(f"  Successfully applied nesting: {success_count}")
        print(f"  Failed or missing matches: {error_count}")
        print(f"  Skipped (already nested or no parent): {skipped_count}")
        print(f"\nUpdated comment map saved to {input_file}")
        
    except Exception as e:
        print(f"Error writing updated comment map: {str(e)}")
    
    return (success_count, error_count, skipped_count)


def create_comment_map(output_file="comments-map.csv", verbose=False):
    """
    Create a map of GitLab issue comments to be imported into GitHub.
    
    Args:
        output_file: Path to the output file
        verbose: Whether to print verbose output
        
    Returns:
        Number of comments found
    """
    # Validate environment variables
    validate_env_vars('create')
    
    # Get environment variables
    gitlab_api_token = os.environ.get('GITLAB_API_PRIVATE_TOKEN')
    gitlab_api_endpoint = os.environ.get('GITLAB_API_ENDPOINT')
    gitlab_repo_url = os.environ.get('GITLAB_REPO_URL')
    
    # Get GitLab project and group info
    project_info = get_gitlab_project_info(gitlab_repo_url)
    
    # Get all issues first
    issues = fetch_gitlab_issues(
        gitlab_api_endpoint, 
        project_info['project_id'], 
        gitlab_api_token, 
        verbose
    )
    
    # Get comments for all issues by fetching discussions
    comments = get_issue_discussions(
        gitlab_api_endpoint, 
        project_info['project_id'], 
        issues, 
        gitlab_api_token, 
        verbose
    )
    
    # Print comments
    print_comments(comments, verbose)
    
    # Save comments to map file
    save_comments_to_map(comments, output_file)
    
    return len(comments)

def main():
    parser = argparse.ArgumentParser(
        description='GitLab/GitHub Comments Tool')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Create map command
    create_parser = subparsers.add_parser('create-map', 
                                         help='Read issue comments from GitLab and create a mapping file')
    create_parser.add_argument('--verbose', action='store_true',
                            help='Show more detailed information about each comment')
    create_parser.add_argument('--output', type=str, default='comments-map.csv',
                            help='Specify output file for the comment map')
    
    # Apply comments to issues command
    apply_nesting_parser = subparsers.add_parser('apply-nesting',
                                     help='Apply comments to GitHub issues based on GitLab issues')
    apply_nesting_parser.add_argument('--verbose', action='store_true',
                           help='Show more detailed information during the process')
    apply_nesting_parser.add_argument('--diagnostic', action='store_true',
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
            
            # Create comment map
            create_comment_map(args.output, args.verbose)
            
        elif args.command == 'apply-nesting':
            # Apply comments to GitHub issues
            apply_nesting_to_issues(verbose=args.verbose, diagnostic=args.diagnostic)
            
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
        
    return 0

if __name__ == '__main__':
    exit(main())
