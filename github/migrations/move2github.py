#!/usr/bin/python3

import os, sys, argparse
#from git import Repo
import requests, json


def read_token_file(token_path:str) -> str:
    if os.path.isfile(f"{token_path}"):
        print(f"Reading {token_path} ...")
        with open(token_path, "r") as file_input:
            lines = file_input.readlines()
            # print(lines[0])
            return lines[0]
    else:
        print(f"Make sure you have a file containing a token on path {token_path}")
        sys.exit()

def parse_git_url(git_url:str) -> str:
    repo_name = git_url.split(':')[1].split('.git')[0]
    if '/' in repo_name:
        repo_name = repo_name.split("/")
    return repo_name[len(repo_name)-1]

if ( __name__ == "__main__"):
    parser = argparse.ArgumentParser(description="Move your repo from GitLab to GitHub")
    parser.add_argument('-g','--git-url', help="Git clone url", required=True)
    parser.add_argument('-p','--path', help="Path to GitHub token", required=False, default='./gh_token')
    args = parser.parse_args()

    repo_name = parse_git_url(args.git_url)
    gh_token = read_token_file(args.path)

    repo_api_url = "https://api.github.com/orgs/icagruppen/repos"
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': f'token {gh_token}'
    }

    os.system('rm -rf /tmp/move2gh-tmp')
    os.system('cd /tmp && mkdir move2gh-tmp')
    os.system(f'cd /tmp/move2gh-tmp && git clone --bare {args.git_url} .')

    payload = json.dumps({
        "name": repo_name,
        "description": "This is your first repository",
        "homepage": f"https://github.com/icagruppen/{repo_name}",
        "private": False,
        "visibility": "private",
        "has_issues": False,
        "has_projects": True,
        "has_wiki": False,
        "allow_rebase_merge": False,
        "allow_rebase_merge": True,
        "use_squash_pr_title_as_default": True
        })
    response = requests.post(repo_api_url, headers=headers, data=payload)
    # print(response.text)

    os.system(f'cd /tmp/move2gh-tmp && git push --mirror "https://github.com/icagruppen/{repo_name}.git"')
    os.system(f'rm -rf /tmp/move2gh-tmp')
