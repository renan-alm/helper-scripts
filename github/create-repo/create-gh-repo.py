#!/usr/bin/env python3

import argparse
import datetime
import requests
import sys
import json
import time
import base64

requests.packages.urllib3.disable_warnings()  # Disable SSL warnings
ORG_OWNER = "icagruppen"
ORGS_API_URL = f"https://api.github.com/orgs/{ORG_OWNER}"
REPOS_API_URL = f"https://api.github.com/repos/{ORG_OWNER}"


class Runner_Group:
    def __init__(self, token) -> None:
        self.token = token

    def find_team_runner_groups(self, repo_name) -> str:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        team_name = repo_name.split("-")[0]

        try:
            response = requests.get(
                f"{ORGS_API_URL}/actions/runner-groups", headers=headers, verify=False
            ).json()
        except requests.exceptions.RequestException as e:
            print("Failed to get runner groups. Error:", str(e))

        print(f"Searching for {team_name} on all existing Runner Groups...")

        runner_groups = response["runner_groups"]
        for item in runner_groups:
            if team_name in item["name"]:
                return item["id"]
            else:
                continue
        print(f"Failed to find Runner Group for {team_name}.")
        return None

    def add_repo(self, rg_id: str, repo_id: str) -> str:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        response = requests.put(
            f"{ORGS_API_URL}/actions/runner-groups/{rg_id}/repositories/{repo_id}",
            headers=headers,
            verify=False,
        )
        if response.status_code == 204:
            print(f"Repo assigned to Runner Group successfully!")
            return response.content
        else:
            print(f"Failed to assign REPO to Runner Group. Error:", response.json())
            sys.exit(1)


### END OF CLASS: Runner_Groups ###


class Repository:
    def __init__(self, name, token, team):
        print("Initializing new instance of a repository ...")
        self.name = f"{team}-{name}"
        self.token = token
        self.team = team

    def create(self, team_id: int) -> str:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        data = {
            "name": f"{self.name}",
            "description": f"This repository is created on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "auto_init": True,
            "private": True,
            "visibility": "internal",
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
                        f"Repository created successfully! https://github.com/icagruppen/{self.name}"
                    )
                    return response.content
            except requests.exceptions.RequestException as e:
                print("Failed to CREATE repository. Error:", str(e))
                tries += 1
                print("Trying to create repository again in 5 seconds ...")
                time.sleep(5)
        if response.status_code != 201:
            sys.exit(1)

    def update_repo(self, allow_squash_merge, allow_merge_commit, allow_rebase_merge):
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        data = {
            "name": f"{self.name}",
            "description": f" Created on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "visibility": "internal",
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
                        f"Failed to set up topics - try N{tries}. Error:",
                        response.json()["message"],
                    )
                    tries = tries + 1
                    print("Trying to set topics again in 5 seconds ...")
                    time.sleep(5)
            except Exception as e:
                print(f"An error occurred while setting up topics: {str(e)}")

    def set_codeowners(self) -> None:
        print(f"Setting CODEOWNERS ...")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

        content = f"# Lines starting with '#' are comments.\n# Each line is a file pattern followed by one or more owners or team assigned to repo.\n# These owners will be the default owners for everything in the repo.\n* @icagruppen/{self.team}"
        base64_encoded_content = base64.b64encode(content.encode("utf-8")).decode(
            "utf-8"
        )
        data = {
            "message": "Adjust CODEOWNER file",
            "committer": {"name": "ICA CDC-Team", "email": "cdc@ica.se"},
            "content": base64_encoded_content,
        }
        tries = 0
        while tries != 5:
            try:
                response = requests.put(
                    f"{REPOS_API_URL}/{self.name}/contents/.github/CODEOWNERS",
                    headers=headers,
                    json=data,
                    verify=False,
                )
                print("Successfully set CODEOWNERS!")
                break
            except requests.exceptions.RequestException as e:
                print("Failed to set up CODEOWNERS. Error:", str(e))
                tries += 1
                print("Trying to set CODEOWNERS again in 5 seconds ...")
                time.sleep(5)
        if tries == 5:
            print(f"COULD NOT set CODEOWNERS")

    def set_repo_admin(self) -> None:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }
        data = {"permission": "admin"}
        tries = 0
        while tries != 5:
            try:
                requests.put(
                    f"{ORGS_API_URL}/teams/{self.team.lower()}/repos/icagruppen/{self.name}",
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
                print("Failed to set up branch protection. Error:", str(e))
                tries += 1
                print("Trying to set branch protection again in 5 seconds ...")
                time.sleep(5)


### END OF CLASS: Repository ###


def repo_exists_check(repo_name: str, token: str) -> bool:
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"{REPOS_API_URL}/{repo_name}", headers=headers, verify=False
    )
    if response.status_code == 200:
        return True
    elif response.status_code == 404:
        return False
    else:
        print(
            "Failed to check repository existence. Error:", response.json()["message"]
        )
        sys.exit(1)


def validate_repo(repo_name: str, token: str) -> None:
    print("Validating repo name ...")
    if " " in repo_name:
        print(f"Field repo'{repo_name}' cannot contain spaces!")
        sys.exit(1)

    if repo_exists_check(repo_name, token):
        print(
            f"The repository '{repo_name}' already exists! - https://github.com/icagruppen/{repo_name}"
        )
        sys.exit(1)


def validate_team(team: str, token: str) -> int:
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
        print(f"Team '{team}' exists in the organization.")
        return teams["id"]
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Create a new repository in a GitHub organization"
    )
    parser.add_argument("--token", required=True, type=str, help="GitHub token")
    parser.add_argument(
        "--repo", required=True, type=str, help="GitHub repository name"
    )
    parser.add_argument("--team", required=True, type=str, help="Team name")
    parser.add_argument("--appid", required=True, type=str, help="Team App id")
    parser.add_argument("--opco", required=True, type=str, help="Opco name")
    parser.add_argument(
        "--topics",
        required=False,
        type=str,
        help="Custom topics to Repo (comma-separated)",
    )
    parser.add_argument(
        "--allow-merge-commit",
        action="store_true",
        default=True,
        required=False,
        help="Boolean to allow merge commits",
    )
    parser.add_argument(
        "--allow-rebase-merge",
        action="store_true",
        default=True,
        required=False,
        help="Boolean to allow rebase merges",
    )
    parser.add_argument(
        "--allow-squash-merge",
        action="store_true",
        default=True,
        required=False,
        help="Boolean to allow squash merges",
    )
    args = parser.parse_args()

    if args.topics:
        topics_list = args.topics.split(",")
    else:
        topics_list = []

    token = args.token
    team_name = args.team.lower()
    repo_name = args.repo.lower()

    validate_repo(f"{team_name}-{repo_name}", token)
    team_id = validate_team(team_name, token)

    repo = Repository(repo_name, token, team_name)
    repo_info = repo.create(team_id)
    repo_info = json.loads(repo_info)
    repo.set_codeowners()
    repo.set_repo_admin()
    repo.update_repo(
        allow_merge_commit=args.allow_merge_commit,
        allow_rebase_merge=args.allow_rebase_merge,
        allow_squash_merge=args.allow_squash_merge,
    )

    repo.set_branch_protection(branch_name="main")
    repo.set_repo_topics(topics=([team_name, args.appid, args.opco] + topics_list))

    runner_group = Runner_Group(token)
    rg_id = runner_group.find_team_runner_groups(repo_name=repo_info["name"])
    if rg_id is not None:
        runner_group.add_repo(rg_id=rg_id, repo_id=repo_info["id"])
    ## FEATURE: else: create the runner group using the Ansible role group_runner

    print(f"Script complete!")


if __name__ == "__main__":
    main()
