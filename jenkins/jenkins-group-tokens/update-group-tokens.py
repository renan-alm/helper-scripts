#!/usr/bin/python3

import argparse
import requests
import os


def update_jenkins_credential(instance: str, appid: str, user: str, password: str, new_value: str) -> None:
    # instance for example "cdc"
    api_url = f"buildserver.ia.icacorp.net/{instance}/credentials/store/system/domain/_/credential/gitlab-id/config.xml"

    # Create the XML payload for updating the credential value
    xml_payload = f"""
    <com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl>
        <scope>GLOBAL</scope>
        <id>gitlab-id</id>
        <description>Updated credential value</description>
        <username>f'svc_gitlab_{appid}'</username>
        <password>{new_value}</password>
    </com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl>
    """

    ## Send the API request to update the credential
    # response = requests.post(api_url, auth=(user, password), data=xml_payload)

    # if response.status_code == 200:
    #     print("Credential updated successfully.")
    # else:
    #     print("Failed to update credential.")


def main():
    parser = argparse.ArgumentParser(description="Update a Jenkins credential")
    parser.add_argument("--instance", help="Jenkins Instance", required=True)
    parser.add_argument("--appid", help="App ID", required=True)
    parser.add_argument("--username", help="Jenkins username", default=os.environ.get('JENKINS_USERNAME'))
    parser.add_argument("--password", help="Jenkins password", default=os.environ.get('JENKINS_PASSWORD'))
    parser.add_argument("--new-value", help="New value for the credential", required=True)
    args = parser.parse_args()

    # Call the function to update the Jenkins credential
    update_jenkins_credential(args.instance, args.appid, args.username, args.password, args.new_value)


if __name__ == "__main__":
    main()
