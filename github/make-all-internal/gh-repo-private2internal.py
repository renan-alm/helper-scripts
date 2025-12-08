#!/usr/local/bin/python3

import requests
import json

# url = "https://api.github.com/orgs/icagruppen/repos?page=1&per_page=100&type=internal"
url = "https://api.github.com/orgs/icagruppen/repos?page=1&per_page=100&type=private"

payload = {}
headers = {
  'Accept': 'application/vnd.github+json',
  'per_page': '100',
  'page': '1', # Change the page if there are too many
  'type': 'private',
  'Authorization': 'Bearer ghp_712312312312'
}

response = requests.request("GET", url, headers=headers, data=payload)
print(json.dumps(response.json(), indent=4))

## To count the amount of repos
## ./gh-repo-private2internal.py | jq '.[].name' | wc -l


### Change whatever was found in the response to internal
payload = json.dumps({
  "visibility": "internal"
})
for repo in response.json():
    repo_name = repo['name']
    print(f"Querying towards url: {repo_name}")
    url = f"https://api.github.com/repos/icagruppen/{repo_name}"
    print(url)
    response = requests.request("PATCH", url, headers=headers, data=payload).json()
    print(json.dumps(response, indent=2))
