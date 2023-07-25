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
    RESPONSE_CONTENT_TEMPLATE = "Response content: %s"
    
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
        self.projects_dir = config.get('Importer', 'projects_dir')
        self.rate_limit_delay = config.getint('Importer', 'rate_limit_delay')

        self.logger = setup_logger(self.log_file)
        configure_logging()

        self.rate_limiter = RateLimiter(self.rate_limit_delay)

        self.auth = HTTPBasicAuth(self.jira_email, self.jira_api_key)

        # will be removed in future updates
        self.priority_mappings = {
            "(5) Low": "Lowest",
            "(4) Normal": "Medium",
            "(3) High": "High",
            "(2) Urgent": "Highest",
            "(1) Immediate": "Highest",
        }

        # will be removed in future updates
        self.field_mappings = {
            "created_on": "customfield_10075",
            "updated_on": "customfield_10076",
            "closed_on": "customfield_10077",
            "estimated_hours": "customfield_10078"
        }

    def get_field_id(self, field_name):
        response = requests.get(f"{self.jira_url}field", auth=self.auth)
        fields = response.json()
        for field in fields:
            if field["name"] == field_name:
                return field["id"]
        return None

    def set_field_value(self, jira_issue, field_name, field_value):
        field_id = self.get_field_id(field_name)
        if field_id:
            jira_issue["fields"][field_id] = field_value
            self.logger.info(f"Field value set successfully for field: {field_name}")
        else:
            raise KeyError(f"Failed to set field value for field: {field_name}")

    def get_user(self, username):
        headers = {"Accept": "application/json"}

        response = requests.request(
            "GET",
            self.jira_url + "user/search?query=" + username,
            headers=headers,
            auth=self.auth
        )

        if response.status_code == 200:
            user_data = response.json()
            if user_data:
                return user_data[0]
            else:
                return None
        else:
            self.logger.error(f"Failed to fetch user data: {response.content}")
            return None

    def log_response_content(self, response):
        self.logger.error(JiraImporter.RESPONSE_CONTENT_TEMPLATE, response.content.decode())

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
                }
            }
        }

        if issue_data["issue"].get("author"):
            old_reporter_name = issue_data["issue"]["author"]["name"]
            try:
                new_reporter_name = self.get_user(old_reporter_name)
                if new_reporter_name:
                    jira_issue["fields"]["reporter"] = {
                        "id": new_reporter_name["accountId"]
                    }
                else:
                    self.logger.warn(f"Could not find a reporter with name: {old_reporter_name}")
                    jira_issue["fields"]["reporter"] = {
                        "name": "Anonymous",
                        "id": "63776502489de2f7f46267eb"
                    }
            except Exception as e:
                self.logger.error(f"Could not set reporter: {str(e)}")

        if issue_data["issue"].get("assigned_to"):
            old_assignee_name = issue_data["issue"]["assigned_to"]["name"]
            try:
                new_assignee_name = self.get_user(old_assignee_name)
                if new_assignee_name:
                    jira_issue["fields"]["assignee"] = {
                        "id": new_assignee_name["accountId"]
                    }
                else:
                    self.logger.warn(f"Could not find an assignee with name {old_assignee_name}")
            except Exception as e:
                self.logger.error(f"Could not set assignee: {str(e)}")

        if issue_data["issue"].get("priority"):
            old_priority_name = issue_data["issue"]["priority"]["name"]
            new_priority_name = self.priority_mappings.get(old_priority_name, old_priority_name)
            jira_issue["fields"]["priority"] = {
                "name": new_priority_name
            }

        category = issue_data["issue"].get("category")
        if category and "name" in category:
            category_name = category["name"].strip()
            if " " in category_name:
                category_name = category_name.replace(" ", "_")
            jira_issue["fields"]["labels"] = [category_name]
        else:
            jira_issue["fields"]["labels"] = []

        if issue_data["issue"].get("start_date"):
            field_value = issue_data["issue"]["start_date"]
            try:
                self.set_field_value(jira_issue, "Start date", field_value)
            except KeyError as e:
                self.logger.error(str(e))

        if issue_data["issue"].get("due_date"):
            field_value = issue_data["issue"]["due_date"]
            try:
                self.set_field_value(jira_issue, "Due date", field_value)
            except KeyError as e:
                self.logger.error(str(e))

        # needs rework
        if issue_data["issue"].get("created_on"):
            field_name = "created_on"
            field_id = self.field_mappings.get(field_name)
            if field_id:
                jira_issue["fields"][field_id] = issue_data["issue"]["created_on"]
            else:
                self.logger.error(f"Field ID not found for field name: {field_name}")

        if issue_data["issue"].get("updated_on"):
            field_name = "updated_on"
            field_id = self.field_mappings.get(field_name)
            if field_id:
                jira_issue["fields"][field_id] = issue_data["issue"]["updated_on"]
            else:
                self.logger.error(f"Field ID not found for field name: {field_name}")

        if issue_data["issue"].get("closed_on"):
            field_name = "closed_on"
            field_id = self.field_mappings.get(field_name)
            if field_id:
                jira_issue["fields"][field_id] = issue_data["issue"]["closed_on"]
            else:
                self.logger.error(f"Field ID not found for field name: {field_name}")

        if issue_data["issue"].get("estimated_hours"):
            field_name = "estimated_hours"
            field_id = self.field_mappings.get(field_name)
            if field_id:
                jira_issue["fields"][field_id] = issue_data["issue"]["estimated_hours"]
            else:
                self.logger.error(f"Field ID not found for field name: {field_name}")
        ####

        if issue_data["issue"].get("estimated_hours"):
            field_value = issue_data["issue"]["estimated_hours"]
            try:
                self.set_field_value(jira_issue, "Estimated hours", field_value)
            except KeyError as e:
                self.logger.error(str(e))

        with self.rate_limiter:
            try:
                response = requests.post(f"{self.jira_url}issue/", auth=self.auth, json=jira_issue)
                response.raise_for_status()

                try:
                    jira_issue_key = response.json()["key"]
                except json.JSONDecodeError:
                    self.logger.error("Could not decode JSON response: %s", response.text)
                    return

                self.logger.info(f"Successfully created issue {issue_data['issue']['id']} in JIRA with key {jira_issue_key}")

                # upload attachments
                if issue_data.get("attachments"):
                    self.upload_attachments_to_issue(jira_issue_key, issue_data)

                # upload comments
                if issue_data.get("journals"):
                    for journal in issue_data["journals"]:
                        self.upload_journal_comment_to_issue(journal, jira_issue_key)

                # Transform the status after the issue is created
                status_id = issue_data["issue"]["status"]["id"]
                transformed_status_id = max(0, status_id - 1)
                if status_id == 1:
                    self.logger.warning(f"No status was assigned for issue {issue_data['issue']['id']} in the original system.")
                if transformed_status_id >= 0:
                    status_url = f"{self.jira_url}issue/{jira_issue_key}/transitions"
                    transition_payload = {
                        "transition": {
                            "id": transformed_status_id
                        }
                    }
                    transition_response = requests.post(status_url, auth=self.auth, json=transition_payload)
                    try:
                        transition_response.raise_for_status()
                        self.logger.info(f"Status transformed successfully for issue {issue_data['issue']['id']}")
                    except requests.HTTPError as e:
                        self.logger.error(f"Failed to transform status for issue {issue_data['issue']['id']}: {str(e)}")
                        self.logger.error("Response content: %s", e.response.content.decode())

            except requests.HTTPError as e:
                if e.response.status_code == 401:
                    raise JiraAuthenticationError('Invalid Jira credentials')
                elif e.response.status_code == 403:
                    raise JiraPermissionError('Jira permission error')
                elif e.response.status_code == 404:
                    raise JiraNotFoundError('Jira issue not found')
                else:
                    self.logger.error("An error occurred during Jira import: %s", str(e))
                    # Use the constant for the response content
                    self.log_response_content(e.response)
                    raise JiraExportError('Jira import error')
            except Exception as e:
                self.logger.error("An error occurred during Jira import: %s", str(e))
                raise JiraExportError('Jira import error')

    def upload_attachments_to_issue(self, issue_key, issue_data):
        for attachment in issue_data["attachments"]:
            attachment_path = os.path.join(self.attachments_dir, str(issue_data["issue"]["id"]), attachment)
            if not os.path.isfile(attachment_path):
                self.logger.warn(f"Attachment file not found: {attachment_path}")
                continue

            with open(attachment_path, "rb") as file:
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
                    # Use the constant for the response content
                    self.log_response_content(e.response)
                    if e.response.status_code == 401:
                        raise JiraAuthenticationError('Invalid Jira credentials')
                    elif e.response.status_code == 403:
                        raise JiraPermissionError('Jira permission error')
                    else:
                        raise JiraAttachmentError(f"Uploading attachment failed for issue {issue_data['issue']['id']}") from e


    def upload_journal_comment_to_issue(self, journal, issue_key):
        comment_body = journal["notes"]
        if not comment_body:
            return

        jira_comment = {
            "body": comment_body
        }

        with self.rate_limiter:
            try:
                response = requests.post(f"{self.jira_url}issue/{issue_key}/comment", auth=self.auth, json=jira_comment)
                response.raise_for_status()
                self.logger.info(f"Successfully uploaded journal comment for issue: {issue_key}")
            except requests.HTTPError as e:
                self.logger.error(f"Failed to add comment for issue {issue_key}: {str(e)}")
                # Use the constant for the response content
                self.log_response_content(e.response)
                raise JiraExportError(f"Failed to add comment for issue {issue_key}")
            except Exception as e:
                self.logger.error(f"Failed to add comment for issue {issue_key}: {str(e)}")
                raise JiraExportError(f"Failed to add comment for issue {issue_key}")

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

            print(f"The checkpoint file {checkpoint_file} already exists. What do you want to do?")
            for option in options:
                print(option)

            user_choice = input("Enter the corresponding number: ")

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
