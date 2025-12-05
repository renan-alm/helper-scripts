#!/usr/bin/env python3
"""
GitLab to GitHub URL Replacer Script

This script sweeps GitHub repositories for GitLab URLs and repository references (e.g., "repo-name#123") 
in issues and PRs, creates a mapping file, and optionally replaces them with GitHub URLs.

For repository references, it ignores timestamp suffixes in repository names. For example,
if the repository is named "migration-test-1755078343906", it will match references like 
"migration-test#2" and map them to "https://github.com/org/migration-test-1755078343906/issues/2".

Usage:
    python gitlab_to_github_url_replacer.py [create-map|execute|revalidate] [options]

Environment Variables Required:
    GITHUB_TOKEN - GitHub Personal Access Token
    GITLAB_API_PRIVATE_TOKEN - GitLab API Private Token
    GITLAB_API_ENDPOINT - GitLab API Endpoint URL
    GITHUB_REPO_URL - GitHub repository URL (e.g., https://github.com/org/repo)
    GITLAB_REPO_URL - GitLab repository URL (e.g., https://gitlab.com/namespace/project)

Commands:
    create-map    - Scan repository and create mapping CSV file (default)
    execute       - Execute replacements from CSV file
    revalidate    - Re-check URL validation for entries in an existing CSV file
    test-url      - Test a single GitHub URL with detailed diagnostics

Options:
    --csv-file <file>   - Specify CSV file for mapping (default: gh-links.csv)
    --output-csv <file> - Output CSV file for revalidation (default: overwrite input)
    --url <url>         - URL to test with the test-url command
    --dry-run           - Run without making actual changes (for execute command)
    --force             - Replace URLs even if not validated as existing (for execute)
    --verbose           - Show more detailed information during processing

Examples:
    python gitlab_to_github_url_replacer.py create-map
    python gitlab_to_github_url_replacer.py execute --csv-file gh-links.csv
    python gitlab_to_github_url_replacer.py execute --dry-run
    python gitlab_to_github_url_replacer.py execute --force --dry-run
    python gitlab_to_github_url_replacer.py revalidate --csv-file gh-links.csv
    python gitlab_to_github_url_replacer.py test-url --url https://github.com/org/repo/issues/1
"""

import os
import re
import csv
import argparse
import requests
from typing import List, Dict, Tuple
from urllib.parse import urlparse
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def validate_env_vars():
    required_vars = ['GITHUB_TOKEN', 'GITLAB_API_PRIVATE_TOKEN', 'GITLAB_API_ENDPOINT',
                'GITHUB_REPO_URL', 'GITLAB_REPO_URL']
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

class GitLabToGitHubReplacer:
    def __init__(self, verbose=False):
        self.github_token = os.environ.get('GITHUB_TOKEN')
        self.gitlab_token = os.environ.get('GITLAB_API_PRIVATE_TOKEN')
        self.gitlab_endpoint = os.environ.get('GITLAB_API_ENDPOINT')
        github_repo_url = os.environ.get('GITHUB_REPO_URL')
        gitlab_repo_url = os.environ.get('GITLAB_REPO_URL')
        self.repo_base_name = None  # Will store the repository name without timestamp
        self.verbose = verbose  # Flag to control verbose output for debugging


        validate_env_vars()

        self.github_repo_url = github_repo_url.rstrip('/')
        self.gitlab_repo_url = gitlab_repo_url.rstrip('/')

        # Parse repository URLs
        github_parsed = urlparse(self.github_repo_url)
        github_path_parts = github_parsed.path.strip('/').split('/')
        if len(github_path_parts) < 2:
            raise ValueError(f"Invalid GitHub repository URL: {github_repo_url}")
        self.github_org = github_path_parts[0]
        self.github_repo = github_path_parts[1]

        # Extract components from GitLab URL
        gitlab_parsed = urlparse(self.gitlab_repo_url)
        self.gitlab_domain = gitlab_parsed.netloc
        gitlab_path_parts = gitlab_parsed.path.strip('/').split('/')
        if len(gitlab_path_parts) < 2:
            raise ValueError(f"Invalid GitLab repository URL: {gitlab_repo_url}")
        self.gitlab_namespace = '/'.join(gitlab_path_parts[:-1])
        self.gitlab_project = gitlab_path_parts[-1]
        
        # Extract the base name of the repository (without timestamp)
        # Pattern to match: repo-name-timestamp where timestamp is a sequence of digits at the end
        repo_match = re.match(r'^(.*?)(?:-\d+)?$', self.github_repo)
        if repo_match:
            self.repo_base_name = repo_match.group(1)
        else:
            self.repo_base_name = self.github_repo

        # Remove the old validation block since we now validate above

        # Setup API headers
        self.github_headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        self.gitlab_headers = {
            'PRIVATE-TOKEN': self.gitlab_token
        }

        print(f"GitHub repository: {self.github_repo_url}")
        print(f"GitLab repository: {self.gitlab_repo_url}")
        print(f"GitLab domain: {self.gitlab_domain}")
        print(f"GitLab namespace/project: {self.gitlab_namespace}/{self.gitlab_project}")
        print(f"Repository base name (for reference matching): {self.repo_base_name}")

    def find_gitlab_urls(self, text: str) -> List[str]:
        """Find all GitLab URLs in the given text."""
        # Pattern to match any GitLab URLs (not just from our specific repository)
        gitlab_pattern = r'https?://[^/]*gitlab[^/]*[^\s\)]*'
        return re.findall(gitlab_pattern, text, re.IGNORECASE)
        
    def find_repo_references(self, text: str) -> List[Tuple[str, int]]:
        """
        Find all repository references in the format "repo-name#123" in the given text.
        
        Returns a list of tuples containing the full match and the issue number.
        Example: [("migration-test#2", 2)]
        """
        if not self.repo_base_name:
            return []
            
        # Pattern to match repo-name#123 references
        # Ensures it doesn't match URLs or other unintended formats
        repo_pattern = r'(?<![/\w])' + re.escape(self.repo_base_name) + r'#(\d+)(?![/\w])'
        matches = re.findall(repo_pattern, text, re.IGNORECASE)
        return [(f"{self.repo_base_name}#{match}", int(match)) for match in matches]

    def convert_repo_reference_to_github_url(self, repo_reference_tuple: Tuple[str, int]) -> str:
        """
        Convert a repository reference to a GitHub issue URL.
        
        Args:
            repo_reference_tuple: A tuple containing (reference_text, issue_number)
        
        Returns:
            str: The GitHub issue URL
        """
        _, issue_number = repo_reference_tuple
        return f"{self.github_repo_url}/issues/{issue_number}"
    
    def convert_gitlab_to_github_url(self, gitlab_url: str) -> str:
        """Convert GitLab URL to corresponding GitHub URL, preserving line references."""
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(gitlab_url)

        # Extract fragment (e.g., L61, L10-L20)
        fragment = parsed.fragment

        # Extract path components
        path_parts = parsed.path.strip('/').split('/')

        if len(path_parts) >= 2:
            # For the GitLab URL structure, the project is the last part of the path before any /-/ or other path markers
            # Find where the repository part of the path ends (before /-/ or similar markers)
            repo_path_end = len(path_parts)  # Default: use all parts
            for i, part in enumerate(path_parts):
                if i >= 2 and (part == '-' or part.startswith('issue') or part.startswith('merge_request')):
                    repo_path_end = i
                    break
            
            # The project name is typically the second element in the path
            # But GitLab can have nested groups, so the project is the last element before special markers
            url_project = path_parts[1] if len(path_parts) > 1 else ""
            url_namespace = path_parts[0] if len(path_parts) > 0 else ""
            
            # Store the project name for later use
            gitlab_project_name = url_project
            
            # Debug output for URL parsing
            if self.verbose:
                print(f"URL: {gitlab_url}")
                print(f"Parsed path parts: {path_parts}")
                print(f"URL namespace: {url_namespace}")
                print(f"URL project: {url_project}")
                print(f"Our namespace: {self.gitlab_namespace}")
                print(f"Our project: {self.gitlab_project}")
            
            # Check if this is our main repository or a different one
            is_main_repo = (url_project == self.gitlab_project)
            
            if self.verbose:
                print(f"URL project: '{url_project}', Our project: '{self.gitlab_project}'")
                print(f"Is main repo: {is_main_repo}")
            
            # Assume the structure is /namespace/project/...
            remaining_path = '/' + '/'.join(path_parts[2:]) if len(path_parts) > 2 else ''

            # Handle GitLab-specific path prefixes
            if remaining_path.startswith('/-/'):
                # GitLab uses /-/ for various views, remove it for GitHub
                remaining_path = remaining_path[3:]
                if remaining_path and not remaining_path.startswith('/'):
                    remaining_path = '/' + remaining_path

            # Convert specific GitLab paths to GitHub equivalents
            if remaining_path.startswith('/merge_requests/'):
                remaining_path = remaining_path.replace('/merge_requests/', '/pull/')

            if is_main_repo:
                # If it's our main repository, use the configured GitHub URL
                github_url = f"{self.github_repo_url}{remaining_path}"
                if self.verbose:
                    print(f"Main repo match - using configured URL: {github_url}")
            else:
                # If it's a different repository, preserve the original repository name
                # Extract GitHub organization from the configured repository URL
                github_org_parts = urlparse(self.github_repo_url).path.strip('/').split('/')
                github_org = github_org_parts[0] if github_org_parts else self.github_org
                
                # Construct a URL that preserves the original repository name
                github_url = f"https://github.com/{github_org}/{gitlab_project_name}{remaining_path}"
                if self.verbose:
                    print(f"Different repo - preserving original name: {github_url}")
                    print(f"  Original URL: {gitlab_url}")
                    print(f"  Repository: {gitlab_project_name}")
                    print(f"  Organization: {github_org}")

            # If the original GitLab URL had a line fragment, append it to the GitHub URL
            if fragment:
                # Only append if it matches a line reference (e.g., L61, L10-L20)
                if re.match(r"^L\d+(-L\d+)?$", fragment):
                    github_url = f"{github_url}#{fragment}"
            return github_url

        # If we can't parse it properly, return the original URL
        return gitlab_url

    def check_github_url_exists(self, github_url: str) -> bool:
        """
        Check if the GitHub URL exists by making API requests.
        Uses the GitHub API to check resources instead of direct HEAD requests when possible.
        """
        try:
            # Parse the URL to extract resource information
            from urllib.parse import urlparse
            parsed = urlparse(github_url)
            path_parts = parsed.path.strip('/').split('/')
            
            # Skip validation for non-GitHub URLs
            if 'github.com' not in parsed.netloc:
                print(f"Warning: Non-GitHub URL validation skipped: {github_url}")
                return True
                
            # Check if URL points to an issue or PR
            if len(path_parts) >= 4 and path_parts[2] in ['issues', 'pull']:
                # Convert web URL to API URL for proper validation
                org = path_parts[0]
                repo = path_parts[1]
                resource_type = 'pulls' if path_parts[2] == 'pull' else path_parts[2]  # 'issues' stays 'issues'
                resource_id = path_parts[3]
                
                # Use GitHub API to check if the resource exists
                api_url = f"https://api.github.com/repos/{org}/{repo}/{resource_type}/{resource_id}"
                response = requests.get(api_url, headers=self.github_headers, timeout=10)
                return response.status_code == 200
            
            # For other GitHub URLs like code paths, try a standard GET request with auth
            response = requests.get(github_url, headers=self.github_headers, timeout=10)
            return response.status_code == 200
        except requests.RequestException as e:
            print(f"Warning: URL validation error for {github_url}: {str(e)}")
            # Be more permissive - assume URL exists if we can't validate it
            return True
            
    def test_single_url(self, url: str) -> None:
        """
        Test a single GitHub URL and print detailed diagnostic information.
        
        Args:
            url: The GitHub URL to test
        """
        print(f"Testing URL: {url}")
        
        # Parse URL components
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path_parts = parsed.path.strip('/').split('/')
        
        print(f"URL components:")
        print(f"  Domain: {parsed.netloc}")
        print(f"  Path: {parsed.path}")
        print(f"  Path parts: {path_parts}")
        
        # Try different validation methods
        print("\nTesting with direct HEAD request:")
        try:
            response = requests.head(url, headers=self.github_headers, timeout=10)
            print(f"  Status code: {response.status_code}")
            print(f"  Success: {response.status_code == 200}")
            if response.status_code != 200:
                print(f"  Headers: {dict(response.headers)}")
        except requests.RequestException as e:
            print(f"  Error: {str(e)}")
        
        print("\nTesting with GET request:")
        try:
            response = requests.get(url, headers=self.github_headers, timeout=10)
            print(f"  Status code: {response.status_code}")
            print(f"  Success: {response.status_code == 200}")
            if response.status_code != 200:
                print(f"  Headers: {dict(response.headers)}")
        except requests.RequestException as e:
            print(f"  Error: {str(e)}")
        
        # If it's an issue or PR, try the API endpoint
        if len(path_parts) >= 4 and path_parts[2] in ['issues', 'pull']:
            org = path_parts[0]
            repo = path_parts[1]
            resource_type = 'pulls' if path_parts[2] == 'pull' else path_parts[2]
            resource_id = path_parts[3]
            
            api_url = f"https://api.github.com/repos/{org}/{repo}/{resource_type}/{resource_id}"
            
            print(f"\nTesting with GitHub API ({api_url}):")
            try:
                response = requests.get(api_url, headers=self.github_headers, timeout=10)
                print(f"  Status code: {response.status_code}")
                print(f"  Success: {response.status_code == 200}")
                if response.status_code != 200:
                    print(f"  Response: {response.text[:500]}")  # Show first 500 chars of response
                else:
                    print("  API response successful")
            except requests.RequestException as e:
                print(f"  Error: {str(e)}")
        
        # Final test with our improved validation method
        print("\nTesting with improved validation method:")
        exists = self.check_github_url_exists(url)
        print(f"  URL exists: {exists}")
        
    def revalidate_mapping_file(self, input_csv: str, output_csv: str = None) -> None:
        """
        Re-validate URLs in an existing mapping file.
        This is useful when URLs initially failed validation but might be valid now.
        
        Args:
            input_csv: The input CSV mapping file
            output_csv: The output CSV file with updated validation results (defaults to overwriting input)
        """
        if not os.path.exists(input_csv):
            raise FileNotFoundError(f"CSV file not found: {input_csv}")
            
        output_csv = output_csv or input_csv
        temp_csv = f"{output_csv}.temp"
        
        print(f"Revalidating URLs in {input_csv}...")
        validated_count = 0
        total_count = 0
        
        with open(input_csv, 'r', encoding='utf-8') as infile, \
             open(temp_csv, 'w', newline='', encoding='utf-8') as outfile:
            
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames
            
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in reader:
                total_count += 1
                github_url = row['github_url']
                url_exists = self.check_github_url_exists(github_url)
                
                if url_exists:
                    validated_count += 1
                
                # Update the validation result
                row['url_exists'] = str(url_exists)
                writer.writerow(row)
                
                # Progress feedback for large files
                if total_count % 10 == 0:
                    print(f"Processed {total_count} URLs, {validated_count} validated...")
        
        # Replace the original file with the updated one
        if input_csv == output_csv:
            os.replace(temp_csv, output_csv)
        else:
            # If output is different, move the temp file to the output name
            os.rename(temp_csv, output_csv)
            
        print(f"Revalidation complete: {validated_count} of {total_count} URLs validated.")
        print(f"Updated results saved to: {output_csv}")

    def get_github_issues(self) -> List[Dict]:
        """Get all issues from GitHub repository."""
        issues = []
        page = 1

        while True:
            url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/issues"
            params = {
                'state': 'all',
                'per_page': 100,
                'page': page
            }

            response = requests.get(url, headers=self.github_headers, params=params)
            if response.status_code != 200:
                print(f"Error fetching issues: {response.status_code} - {response.text}")
                break

            page_issues = response.json()
            if not page_issues:
                break

            issues.extend(page_issues)
            page += 1

            # Rate limiting
            time.sleep(0.1)

        return issues

    def get_github_prs(self) -> List[Dict]:
        """Get all pull requests from GitHub repository."""
        prs = []
        page = 1

        while True:
            url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/pulls"
            params = {
                'state': 'all',
                'per_page': 100,
                'page': page
            }

            response = requests.get(url, headers=self.github_headers, params=params)
            if response.status_code != 200:
                print(f"Error fetching PRs: {response.status_code} - {response.text}")
                break

            page_prs = response.json()
            if not page_prs:
                break

            prs.extend(page_prs)
            page += 1

            # Rate limiting
            time.sleep(0.1)

        return prs

    def get_issue_comments(self, issue_number: int) -> List[Dict]:
        """Get all comments for a specific issue."""
        url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/issues/{issue_number}/comments"

        response = requests.get(url, headers=self.github_headers)
        if response.status_code == 200:
            return response.json()
        return []

    def get_pr_comments(self, pr_number: int) -> List[Dict]:
        """Get all comments for a specific pull request with pagination."""
        # Get issue comments (PRs are issues too)
        issue_comments = self.get_issue_comments(pr_number)

        # Get review comments with pagination
        review_comments = []
        page = 1
        
        while True:
            url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/pulls/{pr_number}/comments"
            params = {
                'per_page': 100,  # Maximum allowed by GitHub API
                'page': page
            }
            
            response = requests.get(url, headers=self.github_headers, params=params)
            if response.status_code != 200:
                break
                
            page_comments = response.json()
            if not page_comments:
                break
                
            review_comments.extend(page_comments)
            page += 1

        return issue_comments + review_comments

    def update_comment(self, comment_id: int, new_body: str, dry_run: bool) -> bool:
        """Update a comment with new body content."""
        if dry_run:
            print(f"[DRY RUN] Would update comment {comment_id}")
            return True

        url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/issues/comments/{comment_id}"
        data = {'body': new_body}

        response = requests.patch(url, headers=self.github_headers, json=data)
        return response.status_code == 200

    def update_issue_body(self, issue_number: int, new_body: str, dry_run: bool) -> bool:
        """Update an issue body with new content."""
        if dry_run:
            print(f"[DRY RUN] Would update issue {issue_number} body")
            return True

        url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/issues/{issue_number}"
        data = {'body': new_body}

        response = requests.patch(url, headers=self.github_headers, json=data)
        return response.status_code == 200

    def update_pr_body(self, pr_number: int, new_body: str, dry_run: bool) -> bool:
        """Update a PR body with new content."""
        if dry_run:
            print(f"[DRY RUN] Would update PR {pr_number} body")
            return True

        url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/pulls/{pr_number}"
        data = {'body': new_body}

        response = requests.patch(url, headers=self.github_headers, json=data)
        return response.status_code == 200

    def create_mapping_file(self, csv_filename: str = 'gh-links.csv') -> None:
        """Create a mapping file of GitLab URLs and repo references found in GitHub repository."""
        print(f"Creating mapping file: {csv_filename}")
        print(f"Scanning repository: {self.github_repo_url}")

        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['type', 'item_number', 'location', 'original_text', 'github_url', 'url_exists', 'reference_type'])

            # Process issues
            print("Fetching issues...")
            issues = self.get_github_issues()
            # Filter out pull requests from issues list
            actual_issues = [issue for issue in issues if issue.get('pull_request') is None]
            print(f"Found {len(actual_issues)} issues")

            for issue in actual_issues:
                # Check issue body
                if issue.get('body'):
                    # Find and process GitLab URLs
                    gitlab_urls = self.find_gitlab_urls(issue['body'])
                    for gitlab_url in gitlab_urls:
                        github_url = self.convert_gitlab_to_github_url(gitlab_url)
                        url_exists = self.check_github_url_exists(github_url)
                        writer.writerow(['issue', issue['number'], 'body', gitlab_url, github_url, url_exists, 'gitlab-url'])
                    
                    # Find and process repository references
                    repo_refs = self.find_repo_references(issue['body'])
                    for repo_ref_text, issue_number in repo_refs:
                        github_url = f"{self.github_repo_url}/issues/{issue_number}"
                        url_exists = self.check_github_url_exists(github_url)
                        writer.writerow(['issue', issue['number'], 'body', repo_ref_text, github_url, url_exists, 'repo-ref'])

                # Check issue comments
                comments = self.get_issue_comments(issue['number'])
                for comment in comments:
                    if comment.get('body'):
                        # Find and process GitLab URLs
                        gitlab_urls = self.find_gitlab_urls(comment['body'])
                        for gitlab_url in gitlab_urls:
                            github_url = self.convert_gitlab_to_github_url(gitlab_url)
                            url_exists = self.check_github_url_exists(github_url)
                            writer.writerow(['issue', issue['number'], f'comment-{comment["id"]}',
                                           gitlab_url, github_url, url_exists, 'gitlab-url'])
                        
                        # Find and process repository references
                        repo_refs = self.find_repo_references(comment['body'])
                        for repo_ref_text, issue_number in repo_refs:
                            github_url = f"{self.github_repo_url}/issues/{issue_number}"
                            url_exists = self.check_github_url_exists(github_url)
                            writer.writerow(['issue', issue['number'], f'comment-{comment["id"]}',
                                           repo_ref_text, github_url, url_exists, 'repo-ref'])

                # Rate limiting
                time.sleep(0.1)

            # Process pull requests
            print("Fetching pull requests...")
            prs = self.get_github_prs()
            print(f"Found {len(prs)} pull requests")

            for pr in prs:
                # Skip if it's actually an issue (PRs are issues in GitHub API)
                if pr.get('pull_request') is None:
                    continue

                # Check PR body
                if pr.get('body'):
                    # Find and process GitLab URLs
                    gitlab_urls = self.find_gitlab_urls(pr['body'])
                    for gitlab_url in gitlab_urls:
                        github_url = self.convert_gitlab_to_github_url(gitlab_url)
                        url_exists = self.check_github_url_exists(github_url)
                        writer.writerow(['pr', pr['number'], 'body', gitlab_url, github_url, url_exists, 'gitlab-url'])
                    
                    # Find and process repository references
                    repo_refs = self.find_repo_references(pr['body'])
                    for repo_ref_text, issue_number in repo_refs:
                        github_url = f"{self.github_repo_url}/issues/{issue_number}"
                        url_exists = self.check_github_url_exists(github_url)
                        writer.writerow(['pr', pr['number'], 'body', repo_ref_text, github_url, url_exists, 'repo-ref'])

                # Check PR comments
                comments = self.get_pr_comments(pr['number'])
                for comment in comments:
                    if comment.get('body'):
                        # Find and process GitLab URLs
                        gitlab_urls = self.find_gitlab_urls(comment['body'])
                        for gitlab_url in gitlab_urls:
                            github_url = self.convert_gitlab_to_github_url(gitlab_url)
                            url_exists = self.check_github_url_exists(github_url)
                            writer.writerow(['pr', pr['number'], f'comment-{comment["id"]}',
                                           gitlab_url, github_url, url_exists, 'gitlab-url'])
                        
                        # Find and process repository references
                        repo_refs = self.find_repo_references(comment['body'])
                        for repo_ref_text, issue_number in repo_refs:
                            github_url = f"{self.github_repo_url}/issues/{issue_number}"
                            url_exists = self.check_github_url_exists(github_url)
                            writer.writerow(['pr', pr['number'], f'comment-{comment["id"]}',
                                           repo_ref_text, github_url, url_exists, 'repo-ref'])

                # Rate limiting
                time.sleep(0.1)

        print(f"Mapping file created: {csv_filename}")

    def execute_replacements(self, csv_filename: str = 'gh-links.csv', dry_run: bool = True,
                             force: bool = False) -> None:
        """Execute URL replacements based on CSV mapping file."""
        if not os.path.exists(csv_filename):
            raise FileNotFoundError(f"CSV file not found: {csv_filename}")

        print(f"Executing replacements from: {csv_filename}")
        if dry_run:
            print("DRY RUN MODE - No actual changes will be made")
        if force:
            print("FORCE MODE - Replacing URLs even if not validated as existing")

        replacements_made = 0

        with open(csv_filename, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            # Group replacements by item and location
            replacements = {}
            skipped_due_to_validation = 0
            
            for row in reader:
                # Process URLs that exist on GitHub, or all URLs if force is enabled
                if force or row['url_exists'].lower() == 'true':
                    key = (row['type'], row['item_number'], row['location'])
                    if key not in replacements:
                        replacements[key] = []
                    # Use original_text instead of gitlab_url to handle both GitLab URLs and repo references
                    replacements[key].append((row['original_text'], row['github_url']))
                else:
                    skipped_due_to_validation += 1
            
            if skipped_due_to_validation > 0:
                print(f"Skipping {skipped_due_to_validation} URLs that failed validation. Use --force to include them.")

            for (item_type, item_number, location), url_pairs in replacements.items():
                try:
                    item_number = int(item_number)

                    if location == 'body':
                        # Handle issue/PR body
                        if item_type == 'issue':
                            if self._replace_in_issue_body(item_number, url_pairs, dry_run):
                                replacements_made += 1
                        elif item_type == 'pr':
                            if self._replace_in_pr_body(item_number, url_pairs, dry_run):
                                replacements_made += 1
                    elif location.startswith('comment-'):
                        # Handle comments
                        comment_id = int(location.split('-')[1])
                        if self._replace_in_comment(comment_id, url_pairs, dry_run):
                            replacements_made += 1

                except (ValueError, IndexError) as e:
                    print(f"Error processing {item_type} {item_number} {location}: {e}")
                    continue

        print(f"Replacements made: {replacements_made}")

    def _replace_in_issue_body(self, issue_number: int, url_pairs: List[Tuple[str, str]], dry_run: bool) -> bool:
        """Replace URLs and repository references in issue body."""
        url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/issues/{issue_number}"
        response = requests.get(url, headers=self.github_headers)

        if response.status_code != 200:
            print(f"Error fetching issue {issue_number}: {response.status_code}")
            return False

        issue = response.json()
        new_body = issue.get('body', '')

        for original_text, github_url in url_pairs:
            new_body = new_body.replace(original_text, github_url)

        if new_body != issue.get('body', ''):
            return self.update_issue_body(issue_number, new_body, dry_run)
        return False

    def _replace_in_pr_body(self, pr_number: int, url_pairs: List[Tuple[str, str]], dry_run: bool) -> bool:
        """Replace URLs and repository references in PR body."""
        url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/pulls/{pr_number}"
        response = requests.get(url, headers=self.github_headers)

        if response.status_code != 200:
            print(f"Error fetching PR {pr_number}: {response.status_code}")
            return False

        pr = response.json()
        new_body = pr.get('body', '')

        for original_text, github_url in url_pairs:
            new_body = new_body.replace(original_text, github_url)

        if new_body != pr.get('body', ''):
            return self.update_pr_body(pr_number, new_body, dry_run)
        return False

    def _replace_in_comment(self, comment_id: int, url_pairs: List[Tuple[str, str]], dry_run: bool) -> bool:
        """Replace URLs and repository references in comment."""
        url = f"https://api.github.com/repos/{self.github_org}/{self.github_repo}/issues/comments/{comment_id}"
        response = requests.get(url, headers=self.github_headers)

        if response.status_code != 200:
            print(f"Error fetching comment {comment_id}: {response.status_code}")
            return False

        comment = response.json()
        new_body = comment.get('body', '')

        for original_text, github_url in url_pairs:
            new_body = new_body.replace(original_text, github_url)

        if new_body != comment.get('body', ''):
            return self.update_comment(comment_id, new_body, dry_run)
        return False

    def process_repository(self, dry_run: bool) -> None:
        """Process a repository to find and replace GitLab URLs."""
        print(f"Processing repository: {self.github_repo_url}")

        # Create CSV file for tracking links
        csv_filename = 'gh-links.csv'
        replacements_made = 0

        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['type', 'gitlab_url', 'github_url', 'found_in_github', 'replaced'])

            # Process issues
            print("Fetching issues...")
            issues = self.get_github_issues()
            print(f"Found {len(issues)} issues")

            for issue in issues:
                # Check issue body
                if issue.get('body'):
                    gitlab_urls = self.find_gitlab_urls(issue['body'])
                    if gitlab_urls:
                        new_body = issue['body']
                        for gitlab_url in gitlab_urls:
                            github_url = self.convert_gitlab_to_github_url(gitlab_url)
                            url_exists = self.check_github_url_exists(github_url)

                            writer.writerow(['issue', gitlab_url, github_url, url_exists, False])

                            if url_exists:
                                new_body = new_body.replace(gitlab_url, github_url)

                        if new_body != issue['body']:
                            if self.update_issue_body(issue['number'], new_body, dry_run):
                                replacements_made += 1
                                print(f"Updated issue #{issue['number']}")

                # Check issue comments
                comments = self.get_issue_comments(issue['number'])
                for comment in comments:
                    if comment.get('body'):
                        gitlab_urls = self.find_gitlab_urls(comment['body'])
                        if gitlab_urls:
                            new_body = comment['body']
                            for gitlab_url in gitlab_urls:
                                github_url = self.convert_gitlab_to_github_url(gitlab_url)
                                url_exists = self.check_github_url_exists(github_url)

                                writer.writerow(['issue', gitlab_url, github_url, url_exists, False])

                                if url_exists:
                                    new_body = new_body.replace(gitlab_url, github_url)

                            if new_body != comment['body']:
                                if self.update_comment(comment['id'], new_body, dry_run):
                                    replacements_made += 1
                                    print(f"Updated comment in issue #{issue['number']}")

                # Rate limiting
                time.sleep(0.1)

            # Process pull requests
            print("Fetching pull requests...")
            prs = self.get_github_prs()
            print(f"Found {len(prs)} pull requests")

            for pr in prs:
                # Skip if it's actually an issue (PRs are issues in GitHub API)
                if pr.get('pull_request') is None:
                    continue

                # Check PR body
                if pr.get('body'):
                    gitlab_urls = self.find_gitlab_urls(pr['body'])
                    if gitlab_urls:
                        new_body = pr['body']
                        for gitlab_url in gitlab_urls:
                            github_url = self.convert_gitlab_to_github_url(gitlab_url)
                            url_exists = self.check_github_url_exists(github_url)

                            writer.writerow(['pr', gitlab_url, github_url, url_exists, False])

                            if url_exists:
                                new_body = new_body.replace(gitlab_url, github_url)

                        if new_body != pr['body']:
                            if self.update_pr_body(pr['number'], new_body, dry_run):
                                replacements_made += 1
                                print(f"Updated PR #{pr['number']}")

                # Check PR comments
                comments = self.get_pr_comments(pr['number'])
                for comment in comments:
                    if comment.get('body'):
                        gitlab_urls = self.find_gitlab_urls(comment['body'])
                        if gitlab_urls:
                            new_body = comment['body']
                            for gitlab_url in gitlab_urls:
                                github_url = self.convert_gitlab_to_github_url(gitlab_url)
                                url_exists = self.check_github_url_exists(github_url)

                                writer.writerow(['pr', gitlab_url, github_url, url_exists, False])

                                if url_exists:
                                    new_body = new_body.replace(gitlab_url, github_url)

                            if new_body != comment['body']:
                                if self.update_comment(comment['id'], new_body, dry_run):
                                    replacements_made += 1
                                    print(f"Updated comment in PR #{pr['number']}")

                # Rate limiting
                time.sleep(0.1)

        print(f"\nProcessing complete!")
        print(f"CSV file created: {csv_filename}")
        if dry_run:
            print("Dry run mode - no actual replacements were made")
        else:
            print(f"Replacements made: {replacements_made}")


def main():
    parser = argparse.ArgumentParser(
        description='Replace GitLab URLs with GitHub URLs in repository issues and PRs')
    parser.add_argument('command', nargs='?', choices=['create-map', 'execute', 'revalidate', 'test-url'], default='create-map',
                        help='Command to execute (default: create-map)')
    parser.add_argument('--csv-file', default='gh-links.csv',
                        help='CSV file for mapping (default: gh-links.csv)')
    parser.add_argument('--output-csv', 
                        help='Output CSV file for revalidation (default: overwrite input file)')
    parser.add_argument('--url',
                        help='URL to test when using the test-url command')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run without making actual changes (applies to execute command)')
    parser.add_argument('--force', action='store_true',
                        help='Replace URLs even if not validated as existing (applies to execute command)')
    parser.add_argument('--verbose', action='store_true',
                        help='Show more detailed information during processing')

    args = parser.parse_args()

    try:
        replacer = GitLabToGitHubReplacer(verbose=args.verbose)

        if args.command == 'create-map':
            replacer.create_mapping_file(args.csv_file)
        elif args.command == 'execute':
            replacer.execute_replacements(args.csv_file, args.dry_run, args.force)
        elif args.command == 'revalidate':
            replacer.revalidate_mapping_file(args.csv_file, args.output_csv)
        elif args.command == 'test-url':
            if not args.url:
                parser.error("The test-url command requires a --url argument")
            replacer.test_single_url(args.url)

    except ValueError as e:
        print(f"Error: {e}")
        return 1
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
