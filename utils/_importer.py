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

        self.priority_mappings = {
            "(5) Low": "Lowest",
            "(4) Normal": "Medium",
            "(3) High": "High",
            "(2) Urgent": "Highest",
            "(1) Immediate": "Highest",
        }

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
                    "name": issue_data["issue"]["assigned_to"]["name"] if issue_data["issue"].get("assigned_to") else None
                }
            }
        }

        if issue_data["issue"].get("priority"):
            old_priority_name = issue_data["issue"]["priority"]["name"]
            # Use the priority_mappings dictionary to get the new name
            new_priority_name = self.priority_mappings.get(old_priority_name, old_priority_name)
            jira_issue["fields"]["priority"] = {
                "name": new_priority_name
            }

        category = issue_data["issue"].get("category")
        if category and "name" in category:
            jira_issue["fields"]["labels"] = [category["name"]]
        else:
            # Handle the case when the category or name is missing
            jira_issue["fields"]["labels"] = []

        if issue_data["issue"].get("start_date"):
            jira_issue["fields"]["customfield_10015"] = issue_data["issue"]["start_date"]

        if issue_data["issue"].get("due_date"):
            jira_issue["fields"]["duedate"] = issue_data["issue"]["due_date"]

        if issue_data["issue"].get("created_on"):
            jira_issue["fields"]["customfield_10061"] = issue_data["issue"]["created_on"]

        if issue_data["issue"].get("updated_on"):
            jira_issue["fields"]["customfield_10062"] = issue_data["issue"]["updated_on"]

        if issue_data["issue"].get("closed_on"):
            jira_issue["fields"]["customfield_10063"] = issue_data["issue"]["closed_on"]

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
        checkpoint_file = "issue_progress.log"
        start_from_checkpoint = False
        checkpoint_id = 0

        if os.path.isfile(checkpoint_file):
            options = [
                "\033[34m1\033[0m) Reset the data and start from scratch",
                "\033[34m2\033[0m) Continue from the last saved progress",
                "\033[90m3\033[0m) Exit and decide later what to do"
            ]

            user_choice = input(
                f"The checkpoint file {checkpoint_file} already exists. What do you want to do?\n{', '.join(options)}\nEnter the corresponding number: "
            )

            if user_choice == "1":
                os.remove(checkpoint_file)
                self.logger.info(f"Deleted checkpoint file: {checkpoint_file}")
            elif user_choice == "2":
                with open(checkpoint_file, "r") as f:
                    checkpoint_id = int(f.read())
                start_from_checkpoint = True
                self.logger.info(f"Resuming from issue index: {checkpoint_id}")
            elif user_choice == "3":
                self.logger.info("Exiting...")
                return
            else:
                self.logger.info("Invalid choice. Exiting...")
                return
        # eline
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if start_from_checkpoint and line_num <= checkpoint_id:
                        continue

                    try:
                        issue_data = json.loads(line)
                        self.import_to_jira(issue_data)
                    except Exception as e:
                        self.logger.error("An error occurred during issue import: %s", str(e))
                        self.logger.error("Skipping issue data: %s", line)

                    checkpoint_id = line_num
                    with open(checkpoint_file, "w") as f:
                        f.write(str(checkpoint_id))
        # eline
        except KeyboardInterrupt:
            self.logger.info("Script interrupted by user.")
            sys.exit(0)

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

