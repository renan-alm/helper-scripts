#!/usr/bin/python3

import requests
import urllib3
import warnings
import json

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

def fetch_gitlab_groups():
    url = "https://git.ica.ia-hc.net/api/v4/groups?per_page=100"
    headers = {
        "Private-Token": "dvmMzS63FwyN4snNouyQ"
    }

    response = requests.get(url, headers=headers, verify=False)
    if response.status_code == 200:
        groups = response.json()
        for gitlab_group in groups:
            if "use_gitlab_group_token" in gitlab_group:
                print(json.dumps(gitlab_group, indent=4))


            # if gitlab_group["name"] == "CDC":
            #     print(json.dumps(gitlab_group, indent=4))
    else:
        print("Failed to fetch Gitlab groups")


if __name__ == "__main__":
    fetch_gitlab_groups()
