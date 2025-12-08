#!/usr/bin/python3

__author__ = "Renan Almeida <xrenan.alm@gmail.com>"

"""
This script is used to move repositories in a batch from GitLab to GitHub.

Pre-requisites:
    -   Linux environment
    -   Python 3.6+
    -   Install the required packages
    -   PEM key provided by your GitHub Admin must be placed in the same directory as this script (or a provided path)

What does this script do:
    - It will migrate all matching repos from GitLab to GitHub
    - It will protect your default branch if you provide one (default 'master')
    - It will configure your repository with basic settings and topics (if you wish to change anything please adjust the update_repo method)

Usage:
    ./movegitlab2github.py -gl ~/.renan/gitlab_token -t 'cdc' -r 'ansible-' -p 'internal' -b 'main'

Arguments:
    -gl, --gitlab-token: Path to a GitLab token (required)
    -gp, --github-pem: Path to a GitHub App PEM file/key path (Default authetication - A PEM key has been provided by your GitHub Admin)
    -gh, --github-token: Path to GitHub token (not required - Only applicable if your token is an Admin token)
    -t, --team: Team name (required)
    -r, --regex: Regex pattern to fetch from GitLab repos (required)
    -p, --privacy: Privacy setting for the migrated repository (optional, default: internal)
    -b, --branch: Default branch to be protected (optional, default: master)
    -d, --dry-run: Dry run - See only affected repos (optional, default: TRUE)

"""

import os, sys, argparse
import requests
import datetime
# import jwt  # PyJWT library - pip install pyjwt
import re
import time

GH_BASE = "solidifyeur.ghe.com"
#GH_BASE = "github.com"
ORG_OWNER = "ProximaEvaluation"   # aka ORG
ORGS_API_URL = f"https://api.{GH_BASE}/orgs/{ORG_OWNER}"
REPOS_API_URL = f"https://api.{GH_BASE}/repos/{ORG_OWNER}"
# GITLAB_ENDPOINT = "https://gitlab.com/api/v4/projects"
GITLAB_ENDPOINT = "https://gitlab.com/api/v4"

requests.packages.urllib3.disable_warnings()  # Disable SSL warnings

def create_app_token(
    app_id: str, key_path: str, installation_id: str, algorithm: str
) -> str:
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,  # Setting expiry to 10 min
        "iss": int(app_id),
    }

    # Inside your create_app_token function or main, read the key from the file
    with open(key_path, "rb") as key_file:
        private_key = key_file.read()
    signing_key = jwt.jwk_from_pem(private_key)
    jwt_instance = jwt.JWT()
    token_encoded = jwt_instance.encode(payload, signing_key, alg=algorithm)

    headers = {
        "Authorization": f"Bearer {token_encoded}",
        "Accept": "application/vnd.github.v3+json",
    }

    tries = 0
    while tries != 3:
        response = requests.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers=headers,
        )
        reponse_json = response.json()
        if response.status_code == 201 and str(reponse_json).find("token") is not None:
            access_token = response.json()["token"]
            return access_token
        else:
            tries = tries + 1
            time.sleep(2)
    return "TOKEN_NOT_ACQUIRED"

def get_gitlab_groups(gl_token:str) -> list:
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {gl_token}'
    }
    page = 1
    group_id_list = []
    while True:
        # Get groups
        response = requests.get(f'{GITLAB_ENDPOINT}/groups', headers=headers, params={'page': page, 'per_page': 100})
        groups = response.json()
        if response.status_code != 200:
            break
        if not groups:
            break
        group_id_list.extend([group['id'] for group in groups])
        # print(f"DEBUG: Group ID list: {group_id_list}")
        page += 1
    return group_id_list

def get_gitlab_projects(gl_token:str, pattern:str) -> list:
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {gl_token}'
    }
    group_ids = get_gitlab_groups(gl_token=gl_token)
    project_list = []
    clone_list = []
    
    for group_id in group_ids:
        page = 1
        while True:
        # Get projects matching the regex
            response = requests.get(f'{GITLAB_ENDPOINT}/groups/{group_id}/projects', headers=headers, params={'page': page, 'per_page': 100})
            projects = response.json()
            if response.status_code != 200:
                break
            if not projects:
                break
            for project in projects:
                # print(f"DEBUG - Project: {project['path_with_namespace']}")
                # print(f"DEBUG - Pattern: {pattern}")
                if re.search(pattern=pattern, string=project['path_with_namespace']):
                    project_list.append(project['name'])
                    clone_list.append(project['http_url_to_repo'])
            page += 1
    # print(f"DEBUG - Projects list: {project_list}")
    return list(zip(project_list, clone_list))

def read_token_file(token_path:str) -> str:
    if os.path.isfile(f"{token_path}"):
        print(f"Reading {token_path} ...")
        with open(token_path, "r") as file_input:
            lines = file_input.readlines()
            return lines[0]
    else:
        print(f"Make sure you have a file containing a token on path {token_path}")
        sys.exit()

def parse_git_url(git_url:str) -> str:
    repo_name = git_url.split(':')[1].split('.git')[0]
    if '/' in repo_name:
        repo_name = repo_name.split("/")
    return repo_name[len(repo_name)-1]

def validate_gh_team(team: str, token: str) -> int:
    print("Validating team name ...")
    if " " in team:
        print(f"Field 'team' '{team}' cannot contain spaces!")
        team = team.replace(" ", "-")
    team_id = get_team_id(team, token)
    if team_id is None:
        print(f"Team must exist in the organization. Exiting ...")
        sys.exit(1)
    return team_id

def get_team_id(team: str, token: str) -> str:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
    }

    tries = 0
    while tries != 3:
        try:

            response = requests.get(
                f"{ORGS_API_URL}/teams/{team}", headers=headers, verify=False
            )
            response.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            print("Failed to get teams. Error:", str(e))
            tries += 1
            print("Trying to get teams again in 5 seconds ...")
            time.sleep(5)
    teams = response.json()
    if teams.get("id"):
        print(f"Team '{team}' exists in the GitHub organization.")
        return teams["id"]
    return None

def mirror_push(gitlab_token:str, github_token: str, gitlab_clone_url:str, github_repo_url:str) -> None:
    os.system('rm -rf /tmp/move2gh-tmp')
    os.system('cd /tmp && mkdir move2gh-tmp')

    gitlab_clone_url = gitlab_clone_url.replace("https://", f"https://oauth2:{gitlab_token}@")
    os.system(f'cd /tmp/move2gh-tmp && git clone --bare {gitlab_clone_url} .')
    # Make a bare clone of the repository

    github_repo_url = github_repo_url.replace("https://", f"https://x-access-token:{github_token}@")
    os.system(f'cd /tmp/move2gh-tmp/ && git push --mirror {github_repo_url}')
    # Mirror-push to the new repository


class Repository:
    def __init__(self, name, token, team, default_branch="master", privacy="internal"):
        print(f"Creating repository '{name}' ...")
        self.name = f"{team}-{name}"
        self.token = token
        self.team = team
        self.default_branch = default_branch
        self.privacy = privacy

    def create(self, team_id: int) -> str:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        data = {
            "name": f"{self.name}",
            "description": f"This repository is created on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "auto_init": False,
            "private": True,
            "visibility": self.privacy,
            "team_id": team_id,
        }
        tries = 0
        while tries != 5:
            try:
                response = requests.post(
                    f"{ORGS_API_URL}/repos", headers=headers, json=data, verify=False
                )
                response.raise_for_status()
                if response.status_code == 201:
                    print(
                        f"Repository created successfully! URL: {response.json()['clone_url']}"
                    )
                    return response.json()['clone_url']
            except requests.exceptions.RequestException as e:
                print("Failed to CREATE repository. Error:", str(e))
                tries += 1
                print("Trying to create repository again in 5 seconds ...")
                time.sleep(5)
        if response.status_code != 201:
            sys.exit(1)

    def rename(self, repo_name: str) -> None:
        self.name = repo_name

    def update_repo(self, allow_squash_merge, allow_merge_commit, allow_rebase_merge):
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        data = {
            "name": f"{self.name}",
            "description": f" Batch moved to GitHub on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "visibility": self.privacy,
            "has_issues": False,
            "has_projects": False,
            "has_wiki": False,
            "has_pages": False,
            "allow_auto_merge": True,
            "is_template": False,
            "allow_squash_merge": allow_squash_merge,
            "allow_merge_commit": allow_merge_commit,
            "allow_rebase_merge": allow_rebase_merge,
            "delete_branch_on_merge": True,
            "allow_update_branch": True,
        }
        response = requests.patch(
            f"{REPOS_API_URL}/{self.name}", headers=headers, json=data, verify=False
        )

        # The call apply the content correctly but still often returns 422
        if response.status_code not in [200]:
            print(
                f"Failed to UPDATE repository {self.name}. Error {response.status_code}:",
                response.json()["message"],
            )
        else:
            print(f"Successfully UPDATED repository settings")

    def set_repo_topics(self, topics):
        print(f"Setting repository topics ...")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.mercy-preview+json",
        }
        data = {"names": topics}
        tries = 0
        while tries != 3:
            try:
                response = requests.put(
                    f"{REPOS_API_URL}/{self.name}/topics",
                    headers=headers,
                    json=data,
                    verify=False,
                )
                if response.status_code == 200:
                    print(f"Successfully set Topics!")
                    break
                else:
                    print(
                        f"Failed to set up topics - try {tries+1}/3. Error:",
                        response.json()["message"],
                    )
                    tries = tries + 1
                    print("Trying to set topics again in 5 seconds ...")
                    time.sleep(5)
            except Exception as e:
                print(f"An error occurred while setting up topics: {str(e)}")

    def set_repo_admin(self) -> None:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        data = {"permission": "admin"}
        print(f"Setting repository admin permissions ...")
        tries = 0
        while tries != 5:
            try:
                requests.put(
                    f"{ORGS_API_URL}/teams/{self.team.lower()}/repos/corporation/{self.name}",
                    headers=headers,
                    json=data,
                    verify=False,
                )
                print(f"Successfully set repository admin permissions!")
                break
            except requests.exceptions.RequestException as e:
                print("Failed to set up repository admin permissions. Error:", str(e))
                tries += 1
                print(
                    "Trying to set repository admin permissions again in 5 seconds ..."
                )
                time.sleep(5)
        if tries == 5:
            print("COULD NOT set repository admin permissions!")

    def set_branch_protection(self, branch_name: str):
        print(f"Setting branch protection for '{branch_name}' ...")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        data = {
            "required_status_checks": {"strict": True, "contexts": []},
            "enforce_admins": False,  # Does not enforce branch protection for admins
            "allow_force_pushes": True,
            "required_pull_request_reviews": {
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": True,
                "require_last_push_approval": False,
                "required_approving_review_count": 1,
            },
            "restrictions": None,
        }
        tries = 0
        while tries != 3:
            try:
                response = requests.put(
                    f"{REPOS_API_URL}/{self.name}/branches/{branch_name}/protection",
                    headers=headers,
                    json=data,
                    verify=False,
                )
                response.raise_for_status()
                print(
                    f"Successfully set branch protection for '{branch_name}' in {self.name}!"
                )
                break
            except requests.exceptions.RequestException as e:
                print(f"Failed to set up branch protection on '{branch_name}' - Try {tries+1}/3. Error:", str(e))
                tries += 1
                print("Trying to set branch protection again in 5 seconds ...")
                time.sleep(5)

    def delete_repo(self) -> None:
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {self.token}"
        }
        response = requests.delete(f"{REPOS_API_URL}/{self.name}", headers=headers, verify=False)
        if response.status_code == 204:
            print(f"Repository {self.name} deleted successfully!")
        else:
            print(f"Failed to delete repository {self.name}. Error {response.status_code}: {response.json()['message']}")
            sys.exit(1)


### END OF CLASS: Repository ###

if ( __name__ == "__main__"):
    parser = argparse.ArgumentParser(description="Move your repo from GitLab to GitHub")
    parser.add_argument('-gl','--gitlab-token', help="GitLab token path", required=True, default='./gitlab_token')
    parser.add_argument('-gp','--github-pem', help="GitHub App PEM key path", required=False, default='./renangh_app.pem')
    parser.add_argument('-gh','--github-token', help="GitHub token path", required=False)
    parser.add_argument('-t','--team', required=True, type=str, help="Team name")
    parser.add_argument('-r','--regex', help="Regex pattern to fetch from GitLab repos", required=True)
    parser.add_argument('-p','--privacy', help="Privacy to be set on the repository migrated", required=False, default='internal')
    parser.add_argument('-b','--branch', help="Default branch to be protected", required=False, default='master')
    parser.add_argument('-n','--name', help="New repo name", required=False) ## Only applicable when the regex matches only one repo
    parser.add_argument('--dry-run', action='store_true', help="Perform a dry run without making any changes", required=False)
    args = parser.parse_args()

    gl_token = read_token_file(args.gitlab_token).rstrip('\n')

    if args.github_token is None:
        print("GitHub token not provided. Using GitHub App PEM key ...")
        gh_token = create_app_token(
            app_id="975444",  # Provided by your GitHub Admin - Client ID: Iv23liDGAj8OZfvuwhKe
            key_path=args.github_pem,   # cdc-batch-migration-app
            installation_id="54003210",  # Provided by your GitHub Admin
            algorithm="RS256"
        )
    else:
        print("GitHub token provided. Using PAT token ...")
        gh_token = read_token_file(args.github_token).rstrip('\n')

    privacy_setting = args.privacy
    # print(f"DEBUG: GitLab token: {gl_token}")
    # print(f"DEBUG: GitHub token: {gh_token}")

    team_name = args.team.lower()
    team_id = validate_gh_team(team_name, gh_token)
    default_branch = args.branch

    repo_regex = args.regex

    gitlab_repos_list = get_gitlab_projects(gl_token=gl_token,pattern=repo_regex)
    if not gitlab_repos_list:
        print(f"No repositories found in GitLab matching the pattern '{repo_regex}'. Exiting ...")
        sys.exit(1)
    # print(f"DEBUG: List of applicable repos: \n{gitlab_repos_list}")

    for repo_item, clone_url_gitlab in gitlab_repos_list:
        repo_item = repo_item.split("/")[-1].replace(" ","-")
        if args.dry_run: 
            repo_name = args.name if args.name else f"{team_name}-{repo_item}"
            print(f"DRY-RUN: Creating repository '{repo_name}' ...")
        else:
            ## Remove the below line to create all repos without pauses (confirmation)
            new_repo = Repository(name=repo_item, token=gh_token, team=team_name, default_branch=default_branch, privacy=privacy_setting)
            if len(gitlab_repos_list) == 1:
                new_repo.rename(repo_name=args.name)

            input(f"\n\nPress Enter to create the repo '{new_repo.name}' ...")
            repo_url_github = new_repo.create(team_id=team_id)


            new_repo.update_repo(allow_squash_merge=True, 
                                allow_merge_commit=True, 
                                allow_rebase_merge=True)
            new_repo.set_repo_admin()
            mirror_push(gitlab_token=gl_token, 
                        github_token=gh_token, 
                        gitlab_clone_url=clone_url_gitlab, 
                        github_repo_url=repo_url_github)
            new_repo.set_branch_protection(branch_name=default_branch) # Default branch protection - Adjust after the migration if needed
            new_repo.set_repo_topics(topics=[team_name, privacy_setting])
            repo_url_github = repo_url_github.replace(".git","")
            print(f"Repository '{repo_url_github}' created successfully!")
            # new_repo.delete_repo()  # Uncomment this line to delete the repo after creation
