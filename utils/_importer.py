# ############################################################################## #
# Created by Polterx, on Saturday, 1st of July, 2023                             #
# Website https://poltersanctuary.com                                            #
# Github  https://github.com/PolterEnterprise                                    #
# ############################################################################## #

import os
import sys
import requests
import json
import html
import copy
import mimetypes

from requests.auth import HTTPBasicAuth
from html import escape

from configparser import ConfigParser, NoSectionError, NoOptionError
from utils._logging import setup_logger, configure_logging
from utils._ratelimiter import RateLimiter


class JiraExportError(Exception):
    pass


class JiraBadRequestError(JiraExportError):
    pass


class JiraAuthenticationError(JiraExportError):
    pass


class JiraPermissionError(JiraExportError):
    pass


class JiraNotFoundError(JiraExportError):
    pass


class JiraRequestTimeoutError(JiraExportError):
    pass


class JiraTooManyRequestsError(JiraExportError):
    pass


class JiraServerError(JiraExportError):
    pass


class JiraAttachmentError(JiraExportError):
    pass


class JiraImporter:
    RESPONSE_CONTENT_TEMPLATE = "Response content: %s"

    def __init__(self):
        try:
            config = ConfigParser()
            config.read('config.ini')

            config_params = {
                "log_dir": {"section": "General", "key": "log_dir"},
                "log_file": {"section": "General", "key": "log_file"},
                "rate_limit": {"section": "General", "key": "rate_limit"},
                "jira_url": {"section": "Jira", "key": "url"},
                "jira_email": {"section": "Jira", "key": "email"},
                "jira_api_key": {"section": "Jira", "key": "api_key"},
                "jira_project_key": {"section": "Jira", "key": "project_key"},
                "attachments_dir": {"section": "Importer", "key": "attachments_dir"},
                "allowed_file_types": {"section": "Importer", "key": "allowed_file_types"},
                "maximum_file_size": {"section": "Importer", "key": "maximum_file_size"},
            }

            for attribute, params in config_params.items():
                config_value = config.get(params["section"], params["key"])
                if attribute == "allowed_file_types":
                    setattr(self, attribute, config_value.split(','))
                else:
                    setattr(self, attribute, config_value)

            self.auth = HTTPBasicAuth(self.jira_email, self.jira_api_key)
            self.rate_limiter = RateLimiter(delay=float(self.rate_limit))
            self.logger = setup_logger('importer', self.log_dir, self.log_file)

        except NoSectionError as e:
            raise JiraExportError(f"Error in configuration file: {str(e)}")
        except NoOptionError as e:
            raise JiraExportError(f"Missing required option in configuration file: {str(e)}")
        except Exception as e:
            raise JiraExportError(f"Error reading configuration: {str(e)}")

        # for patch v1.0.4
        self.fields_mappings = {
            "subject": {"mapping": "summary", "type": str, "sanitize": True},
            "description": {"mapping": "description", "type": str, "sanitize": True},
            "author": {"mapping": "reporter", "type": dict, "sanitize": True},
            "assigned_to": {"mapping": "assignee", "type": dict, "sanitize": True},
            "project": {"mapping": "project", "type": dict, "sanitize": True},  # Assuming project maps to category
            "priority": {"mapping": "priority", "type": dict, "sanitize": True},
            "start_date": {"mapping": "customfield_10015", "type": str, "sanitize": False},
            "due_date": {"mapping": "duedate", "type": str, "sanitize": False},
            "created_on": {"mapping": "customfield_10075", "type": str, "sanitize": False},
            "updated_on": {"mapping": "customfield_10076", "type": str, "sanitize": False},
            "closed_on": {"mapping": "customfield_10077", "type": str, "sanitize": False},
            "estimated_hours": {"mapping": "customfield_10078", "type": int, "sanitize": False},
            "labels": {"mapping": "labels", "type": list, "sanitize": True},  # For Labels, it will depend on how those are structured in your input
            "fix_versions": {"mapping": "fixVersions", "type": list, "sanitize": True},  # For Fix Versions, it will depend on how those are structured in your input
            "attachments": {"mapping": "attachments", "type": list, "sanitize": True},  # For Attachments, may require special handling, depending on their structure
            "journals": {"mapping": "journals", "type": list, "sanitize": True},  # For Journals, may require special handling, depending on their structure
        }

        self.status_mappings = {
            "New": {"mapping": "1", "type": int, "sanitize": False},
            "In Progress": {"mapping": "2", "type": int, "sanitize": False},
            "Ready For Testing": {"mapping": "3", "type": int, "sanitize": False},
            "Feedback": {"mapping": "4", "type": int, "sanitize": False},
            "Closed": {"mapping": "5", "type": int, "sanitize": False},
            "Rejected": {"mapping": "6", "type": int, "sanitize": False},
            "Approved": {"mapping": "7", "type": int, "sanitize": False},
            "Re-Opened": {"mapping": "8", "type": int, "sanitize": False},
            "Won't Fix": {"mapping": "9", "type": int, "sanitize": False},
            "On Hold": {"mapping": "10", "type": int, "sanitize": False},
            "In Review": {"mapping": "11", "type": int, "sanitize": False},
        }

        self.priority_mappings = {
            "(1) Immediate": {"mapping": "Highest", "type": str, "sanitize": False},
            "(2) Urgent": {"mapping": "High", "type": str, "sanitize": False},
            "(3) High": {"mapping": "Medium", "type": str, "sanitize": False},
            "(4) Normal": {"mapping": "Low", "type": str, "sanitize": False},
            "(5) Low": {"mapping": "Lowest", "type": str, "sanitize": False},
        }

    def log_response_content(self, response):
        self.logger.error(JiraImporter.RESPONSE_CONTENT_TEMPLATE, response.content.decode())

    def validate_input(self, input_data, input_types):
        if isinstance(input_data, input_types):
            return True
        else:
            return False

    def sanitize_input(self, input_data):
        if isinstance(input_data, str):
            return html.escape(input_data)
        else:
            return input_data

    def get_field_id(self, field_name):
        response = requests.get(f"{self.jira_url}field", auth=self.auth)
        fields = response.json()
        for field in fields:
            if field["name"] == field_name:
                return field["id"]
        return None

    def set_field_value(self, jira_issue, field_name, value, field_mapping_dict):
        if field_name in field_mapping_dict:
            field_id = field_mapping_dict[field_name]["mapping"]

            # Validate the input based on its expected type
            if not self.validate_input(value, field_mapping_dict[field_name]["type"]):
                self.logger.error(f"Invalid type for {field_name}: {value}")
                return

            # If sanitize flag is set to True, sanitize the value
            if field_mapping_dict[field_name]["sanitize"]:
                value = self.sanitize_input(value)

            # Set the value in jira_issue
            jira_issue["fields"][field_id] = value
        else:
            self.logger.error(f"Field mapping not found for field name: {field_name}")

    def get_user(self, username):
        if not self.validate_input(username, str):
            raise ValueError(f'Invalid username: {username}')

        sanitized_username = self.sanitize_input(username)
        headers = {"Accept": "application/json"}
        response = requests.request(
            "GET",
            self.jira_url + "user/search?query=" + sanitized_username,
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

    def get_transition_id(self, issue_key, target_status):
        transitions_url = f"{self.jira_url}issue/{issue_key}/transitions"
        transitions_response = requests.get(transitions_url, auth=self.auth)
        transitions_response.raise_for_status()
        transitions = transitions_response.json().get('transitions', [])
        for transition in transitions:
            if transition['to']['name'].lower() == target_status.lower():
                return transition['id']
        return None

    def handle_http_error(self, e, error_message):
        if e.response.status_code == 400:
            raise JiraBadRequestError('Bad request') from e
        elif e.response.status_code == 401:
            raise JiraAuthenticationError('Invalid Jira credentials') from e
        elif e.response.status_code == 403:
            raise JiraPermissionError('Jira permission error') from e
        elif e.response.status_code == 404:
            raise JiraNotFoundError('Jira issue not found') from e
        elif e.response.status_code == 408:
            raise JiraRequestTimeoutError('Request Timeout') from e
        elif e.response.status_code == 429:
            raise JiraTooManyRequestsError('Too Many Requests') from e
        elif 500 <= e.response.status_code < 600:
            raise JiraServerError('Server Error') from e
        else:
            self.logger.error(f"{error_message}. Error: {str(e)}")
            self.log_response_content(e.response)
            raise JiraExportError('Jira import error') from e

    def is_allowed_file_type(self, filepath):
        mime_type, _ = mimetypes.guess_type(filepath)
        if mime_type:
            file_type = mime_type.split('/')[1]
            return file_type in self.allowed_file_types
        else:
            return False

    # This is a placeholder for malware checking logic
    def is_malware_infected(self):
        return True

    def handle_reporter(self, issue_data, jira_issue):
        reporter_info = issue_data["issue"].get("author")
        if not reporter_info:
            self.logger.warn(f"No reporter found for issue {issue_data['issue']['id']}")
            return

        old_reporter_name = reporter_info.get("name")
        if not old_reporter_name:
            self.logger.warn(f"No reporter name found for issue {issue_data['issue']['id']}")
            return

        try:
            new_reporter = self.get_user(old_reporter_name)
            if not new_reporter:
                self.logger.warn(f"Could not find reporter with the name ({old_reporter_name}) for issue {issue_data['issue']['id']}")
                default_user_name = "Anonymous"
                default_user_id = "63776502489de2f7f46267eb"
                jira_issue["fields"]["reporter"] = {"name": default_user_name, "id": default_user_id}
                self.logger.warn(f"Setting reporter to default ({default_user_name}) for issue: {issue_data['issue']['id']}")
                return

            reporter_id = new_reporter.get("accountId")
            if not reporter_id:
                self.logger.warn(f"Could not find account ID for reporter ({old_reporter_name}) for issue {issue_data['issue']['id']}")
                return

            jira_issue["fields"]["reporter"] = {"id": reporter_id}
            self.logger.info(f"Setting of reporter ({reporter_id}) completed for issue: {issue_data['issue']['id']}")
        except Exception as e:
            self.logger.error(f"Could not set reporter due to error: {str(e)} for issue: {issue_data['issue']['id']}")

    def handle_assignee(self, issue_data, jira_issue):
        assignee_info = issue_data["issue"].get("assigned_to")
        if not assignee_info:
            self.logger.warn(f"No assignee found for issue {issue_data['issue']['id']}")
            return

        old_assignee_name = assignee_info.get("name")
        if not old_assignee_name:
            self.logger.warn(f"No assignee name found for issue {issue_data['issue']['id']}")
            return

        try:
            new_assignee = self.get_user(old_assignee_name)
            if not new_assignee:
                self.logger.warn(f"Could not find assignee with the name ({old_assignee_name}) for issue {issue_data['issue']['id']}")
                jira_issue["fields"]["assignee"] = None
                self.logger.warn(f"Setting assignee to default (Unassigned) for issue: {issue_data['issue']['id']}")
                return

            assignee_id = new_assignee.get("accountId")
            if not assignee_id:
                self.logger.warn(f"Could not find account ID for assignee ({old_assignee_name}) for issue {issue_data['issue']['id']}")
                return

            jira_issue["fields"]["assignee"] = {"id": assignee_id}
            self.logger.info(f"Setting of assignee ({assignee_id}) completed for issue: {issue_data['issue']['id']}")
        except Exception as e:
            self.logger.error(f"Could not set assignee due to error: {str(e)} for issue: {issue_data['issue']['id']}")

    def handle_priority(self, issue_data, jira_issue):
        field_name = "priority"
        old_priority = issue_data["issue"].get(field_name)
        
        if old_priority and old_priority.get("name"):
            old_priority_name = old_priority["name"]

            # Check if old_priority_name exists in priority_mappings
            if old_priority_name in self.priority_mappings:
                new_priority_name = self.priority_mappings[old_priority_name]["mapping"]

                # If sanitize flag is set to True, sanitize the value
                if self.priority_mappings[old_priority_name]["sanitize"]:
                    new_priority_name = self.sanitize_input(new_priority_name)

                # Build a dictionary to fit Jira's expected format for priority field
                new_priority_value = {"name": new_priority_name}

                # Use set_field_value to handle setting the value and error handling
                self.set_field_value(jira_issue, field_name, new_priority_value, self.fields_mappings)

    def handle_category(self, issue_data, jira_issue):
        field_name = "category"
        category = issue_data["issue"].get(field_name)
        
        if category and "name" in category:
            category_name = category["name"].strip()
            if " " in category_name:
                category_name = category_name.replace(" ", "_")
            
            # Use set_field_value to handle setting the value and error handling
            self.set_field_value(jira_issue, "labels", [category_name], self.fields_mappings)
        else:
            self.set_field_value(jira_issue, "labels", [], self.fields_mappings)

    def handle_start_date(self, issue_data, jira_issue):
        field_name = "start_date"
        if issue_data["issue"].get(field_name):
            field_value = issue_data["issue"][field_name]
            self.set_field_value(jira_issue, field_name, field_value, self.fields_mappings)

    def handle_duedate(self, issue_data, jira_issue):
        field_name = "due_date"
        if issue_data["issue"].get(field_name):
            field_value = issue_data["issue"][field_name]
            self.set_field_value(jira_issue, field_name, field_value, self.fields_mappings)

    def handle_created_on(self, issue_data, jira_issue):
        field_name = "created_on"
        if issue_data["issue"].get(field_name):
            field_value = issue_data["issue"][field_name]
            self.set_field_value(jira_issue, field_name, field_value, self.fields_mappings)

    def handle_updated_on(self, issue_data, jira_issue):
        field_name = "updated_on"
        if issue_data["issue"].get(field_name):
            field_value = issue_data["issue"][field_name]
            self.set_field_value(jira_issue, field_name, field_value, self.fields_mappings)

    def handle_closed_on(self, issue_data, jira_issue):
        field_name = "closed_on"
        if issue_data["issue"].get(field_name):
            field_value = issue_data["issue"][field_name]
            self.set_field_value(jira_issue, field_name, field_value, self.fields_mappings)

    def handle_dates(self, issue_data, jira_issue):
        self.handle_start_date(issue_data, jira_issue)
        self.handle_duedate(issue_data, jira_issue)
        self.handle_created_on(issue_data, jira_issue)
        self.handle_updated_on(issue_data, jira_issue)
        self.handle_closed_on(issue_data, jira_issue)

    def handle_estimated_hours(self, issue_data, jira_issue):
        field_name = "estimated_hours"
        if issue_data["issue"].get(field_name):
            field_value = issue_data["issue"][field_name]
            self.set_field_value(jira_issue, field_name, field_value, self.fields_mappings)

    def handle_attachments(self, issue_key, issue_data):
        if not self.validate_input(issue_data["attachments"], list):
            self.logger.error(f"Invalid type for attachments: {issue_data['attachments']}")
            return

        for attachment in issue_data["attachments"]:
            attachment_path = os.path.join(self.attachments_dir, str(issue_data["issue"]["id"]), attachment)
            if not os.path.isfile(attachment_path):
                self.logger.warn(f"Attachment file not found: {attachment_path}")
                continue

            # File size check
            if os.path.getsize(attachment_path) > int(self.maximum_file_size):
                self.logger.error(f"Attachment file is too large: {attachment_path}")
                continue

            # File type check
            if not self.is_allowed_file_type(attachment_path):
                self.logger.error(f"Disallowed file type in attachment: {attachment_path}")
                continue

            # File name sanitization
            sanitized_filename = self.sanitize_input(attachment)

            # malware check logic
            # if not self.is_malware_infected(attachment_path):
            #     self.logger.error(f"Attachment file contains malware: {attachment_path}")
            #     continue

            with open(attachment_path, "rb") as file:
                try:
                    response = requests.post(
                        f"{self.jira_url}issue/{issue_key}/attachments",
                        headers={"X-Atlassian-Token": "no-check"},
                        files={"file": (sanitized_filename, file)},
                        auth=self.auth
                    )
                    response.raise_for_status()
                except requests.HTTPError as e:
                    self.handle_http_error(e, f"Error occurred while uploading attachment to Jira issue {issue_key}")
                except Exception as e:
                    self.logger.error(f"Error occurred while uploading attachment to Jira issue {issue_key}. Error: {str(e)}")
                    raise JiraAttachmentError(f"Uploading attachment failed for issue {issue_data['issue']['id']}") from e

    def handle_journals(self, journal, issue_key):
        if not self.validate_input(journal, dict):
            self.logger.error(f"Invalid type for journal: {journal}")
            return

        comment_body = journal["notes"]
        if not comment_body:
            return

        comment_body = self.sanitize_input(comment_body)

        jira_comment = {
            "body": comment_body
        }

        try:
            response = requests.post(f"{self.jira_url}issue/{issue_key}/comment", auth=self.auth, json=jira_comment)
            response.raise_for_status()
            self.logger.info(f"Successfully uploaded journal comment for issue: {issue_key}")
        except requests.HTTPError as e:
            self.handle_http_error(e, f"Failed to add comment for issue {issue_key}")
        except Exception as e:
            self.logger.error(f"Failed to add comment for issue {issue_key}: {str(e)}")
            raise JiraExportError(f"Failed to add comment for issue {issue_key}")

    def issues_setup(self, issue_data):
        with self.rate_limiter:
            if not self.validate_input(issue_data, dict):
                raise ValueError(f'Invalid issue data: {issue_data}')

            sanitized_issue_data = copy.deepcopy(issue_data)
            sanitized_issue_data["issue"]["subject"] = self.sanitize_input(sanitized_issue_data["issue"]["subject"])
            sanitized_issue_data["issue"]["description"] = self.sanitize_input(sanitized_issue_data["issue"]["description"])

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

            self.handle_reporter(issue_data, jira_issue)
            self.handle_assignee(issue_data, jira_issue)
            self.handle_dates(issue_data, jira_issue)
            self.handle_priority(issue_data, jira_issue)
            self.handle_category(issue_data, jira_issue)
            self.handle_estimated_hours(issue_data, jira_issue)

            try:
                response = requests.post(f"{self.jira_url}issue/", auth=self.auth, json=jira_issue)
                response.raise_for_status()

                try:
                    jira_issue_key = response.json()["key"]
                except json.JSONDecodeError:
                    self.logger.error("Could not decode JSON response: %s", response.text)
                    return

                if issue_data.get("attachments"):
                    self.handle_attachments(jira_issue_key, issue_data)

                if issue_data.get("journals"):
                    for journal in issue_data["journals"]:
                        self.handle_journals(journal, jira_issue_key)

                # Transform the status after the issue is created
                status_name = issue_data["issue"]["status"]["name"]
                transition_id = self.get_transition_id(jira_issue_key, status_name)
                if transition_id is None:
                    self.logger.error(f"No transition found to status {status_name} for issue: {issue_data['issue']['id']}")
                else:
                    status_url = f"{self.jira_url}issue/{jira_issue_key}/transitions"
                    transition_payload = {
                        "transition": {
                            "id": transition_id
                        }
                    }
                    transition_response = requests.post(status_url, auth=self.auth, json=transition_payload)
                    try:
                        transition_response.raise_for_status()
                        self.logger.info(f"Status transformed successfully for issue: {issue_data['issue']['id']}")
                    except requests.HTTPError as e:
                        self.handle_http_error(e, f"Failed to transform status for issue: {issue_data['issue']['id']}: {str(e)}")

                self.logger.info(f"Successfully created issue {issue_data['issue']['id']} in JIRA with key {jira_issue_key}")
                self.logger.info("-"*50)  # Add separator line at the end of processing an issue
                    
            except requests.HTTPError as e:
                self.handle_http_error(e, f"Failed creating issue {issue_data['issue']['id']} in JIRA with key {jira_issue_key}")
            except Exception as e:
                self.logger.error("An error occurred during Jira import: %s", str(e))
                raise JiraExportError('Jira import error')

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
                        self.issues_setup(issue_data)
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
        configure_logging(args.debug)
        
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
