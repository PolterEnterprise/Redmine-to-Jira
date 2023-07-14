# ############################################################################## #
# Created by Polterx, on Saturday, 1st of July, 2023                             #
# Website https://poltersanctuary.com                                            #
# Github  https://github.com/PolterEnterprise                                    #
# ############################################################################## #

import os
import sys
import requests
import json

from requests.auth import HTTPBasicAuth

from configparser import ConfigParser
from utils._logging import setup_logger, configure_logging
from utils._ratelimiter import RateLimiter


class JiraExportError(Exception):
    pass


class JiraAuthenticationError(JiraExportError):
    pass


class JiraPermissionError(JiraExportError):
    pass


class JiraNotFoundError(JiraExportError):
    pass


class JiraAttachmentError(JiraExportError):
    pass


class JiraImporter:
    def __init__(self):
        config = ConfigParser()
        config.read('config.ini')

        # Configuration
        self.log_file = config.get('Importer', 'log_file')
        self.jira_url = config.get('Jira', 'url')
        self.jira_email = config.get('Jira', 'email')
        self.jira_api_key = config.get('Jira', 'api_key')
        self.jira_project_key = config.get('Jira', 'project_key')
        self.attachments_dir = config.get('Importer', 'attachments_dir')
        self.rate_limit_delay = config.getint('Importer', 'rate_limit_delay')

        self.logger = setup_logger(self.log_file)
        configure_logging()

        self.rate_limiter = RateLimiter(self.rate_limit_delay)

        self.auth = HTTPBasicAuth(self.jira_email, self.jira_api_key)

    def import_to_jira(self, issue_data):
        issue_data["issue"]["subject"] = issue_data["issue"]["subject"].encode('utf-8').decode()
        issue_data["issue"]["description"] = issue_data["issue"]["description"].encode('utf-8').decode()

        jira_issue = {
            "fields": {
                "project": {
                    "key": self.jira_project_key
                },
                "summary": issue_data["issue"]["subject"],
                "description": issue_data["issue"]["description"],
                "issuetype": {
                    "name": issue_data["issue"]["tracker"]["name"]
                },
                "reporter": {
                    "name": issue_data["issue"]["author"]["name"]
                },
                "assignee": {
                    "name": issue_data["issue"]["assigned_to"]["name"]
                },
                # "priority": {
                #     "name": issue_data["issue"]["priority"]["name"]
                # },
            }
        }

        # If the issue data contains 'due_date' and it's not None, add it to the issue fields.
        if issue_data["issue"].get("due_date"):
            jira_issue["fields"]["duedate"] = issue_data["issue"]["due_date"]

        with self.rate_limiter:
            try:
                response = requests.post(f"{self.jira_url}issue/", auth=self.auth, json=jira_issue)
                response.raise_for_status()

                jira_issue_key = response.json()["key"]
                self.logger.info(f"Successfully created issue {issue_data['issue']['id']} in JIRA with key {jira_issue_key}")

                # If the issue data contains attachments, upload them to the created JIRA issue
                if issue_data.get("attachments"):
                    self.upload_attachments_to_issue(jira_issue_key, issue_data)

            except requests.HTTPError as e:
                if e.response.status_code == 401:
                    raise JiraAuthenticationError('Invalid Jira credentials')
                elif e.response.status_code == 403:
                    raise JiraPermissionError('Jira permission error')
                elif e.response.status_code == 404:
                    raise JiraNotFoundError('Jira issue not found')
                else:
                    self.logger.error("An error occurred during Jira export: %s", str(e))
                    self.logger.error("Response content: %s", e.response.content.decode())
                    raise JiraExportError('Jira export error')
            except Exception as e:
                self.logger.error("An error occurred during Jira export: %s", str(e))
                raise JiraExportError('Jira export error')

    def upload_attachments_to_issue(self, issue_key, issue_data):
        for attachment in issue_data["attachments"]:
            with open(os.path.join(self.attachments_dir, str(issue_data["issue"]["id"]), attachment), "rb") as file:
                try:
                    response = requests.post(
                        f"{self.jira_url}issue/{issue_key}/attachments",
                        headers={"X-Atlassian-Token": "no-check"},
                        files={"file": file},
                        auth=self.auth
                    )
                    response.raise_for_status()
                except requests.HTTPError as e:
                    self.logger.error(f"Error occurred while uploading attachment to Jira issue {issue_key}. Error: {str(e)}")
                    if e.response.status_code == 401:
                        raise JiraAuthenticationError('Invalid Jira credentials')
                    elif e.response.status_code == 403:
                        raise JiraPermissionError('Jira permission error')
                    else:
                        raise JiraAttachmentError(f"Uploading attachment failed for issue {issue_data['issue']['id']}") from e

    def import_issues(self, filename):
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                issue_data = json.loads(line)
                self.import_to_jira(issue_data)

    def run(self, args):
        if args.project and not args.activate_extraction:
            extracted_issues = []
            self.logger.info(f"Extracted {len(extracted_issues)} issues for project: {args.project}")

            # Save extracted issues to a file
            with open(args.filename, "w") as f:
                for issue in extracted_issues:
                    f.write(json.dumps(issue) + "\n")

        if args.attachments:
            # Handle the -a or --attachments option
            self.logger.info("Exporting attachments...")

        if args.status:
            # Handle the -s or --status option
            self.logger.info(f"Filtering issues by status: {args.status}")

        if args.priority:
            # Handle the -pr or --priority option
            self.logger.info(f"Filtering issues by priority: {args.priority}")

        if args.activate_extraction:
            self.import_issues(args.filename)
