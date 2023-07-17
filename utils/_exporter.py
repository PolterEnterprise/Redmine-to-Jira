# ############################################################################## #
# Created by Polterx, on Saturday, 1st of July, 2023                             #
# Website https://poltersanctuary.com                                            #
# Github  https://github.com/PolterEnterprise                                    #
# ############################################################################## #

import os
import sys
import requests
import json

from configparser import ConfigParser
from utils._logging import setup_logger, configure_logging
from utils._ratelimiter import RateLimiter


class RedmineExportError(Exception):
    pass


class RedmineAuthenticationError(RedmineExportError):
    pass


class RedminePermissionError(RedmineExportError):
    pass


class RedmineNotFoundError(RedmineExportError):
    pass


class RedmineExporter:
    def __init__(self):
        config = ConfigParser()
        config.read('config.ini')

        # Configuration
        self.redmine_url = config.get('Redmine', 'url')
        self.redmine_api_key = config.get('Redmine', 'api_key')
        self.attachments_dir = config.get('Exporter', 'attachments_dir')
        self.log_file = config.get('Exporter', 'log_file')
        self.rate_limit_delay = config.getint('Exporter', 'rate_limit_delay')
        self.maximum_issues = config.getint('Exporter', 'maximum_issues')

        self.logger = setup_logger(self.log_file)

    def fetch_issues(self, project_id=None, status=None, priority=None):
        if project_id:
            self.logger.info(f"Fetching issues for project: {project_id}")
            endpoint = f"{self.redmine_url}/issues.json"
            params = {"key": self.redmine_api_key, "project_id": project_id}
        else:
            self.logger.info("Fetching all issues")
            endpoint = f"{self.redmine_url}/issues.json"
            params = {"key": self.redmine_api_key, "subproject_id": "!*"}

        status_map = {
            1: '1',  # New issues (The issue is newly created and not yet assigned or in progress.)
            2: '2',  # In Progress issues (The issue is actively being worked on.)
            3: '3',  # Resolved issues (The issue has been resolved or completed.)
            4: '4',  # Feedback issues (The issue is awaiting feedback or further input.)
            5: '5',  # Closed issues (The issue has been closed and is considered complete.)
            6: '6',  # Rejected issues (The issue has been rejected or deemed invalid.)
            7: '7',  # Approved issues (The issue has been approved and can proceed.)
            8: '8',  # Won't Fix issues (The issue will not be fixed or addressed.)
            9: '9',  # Re-opened issues (The issue was previously closed but has been reopened for further work.)
            10: '10',  # In View issues (The issue is being reviewed or examined.)
            11: '11'  # Ready for Testing issues (The issue is ready for testing or quality assurance.)
        }

        priority_map = {
            1: '1',  # Low priority
            2: '2',  # Normal priority
            3: '3',  # High priority
            4: '4',  # Urgent priority
            5: '5'   # Immediate priority
        }

        if status is not None:
            if status == 'approved':
                params["status_id"] = status_map[7]
            elif status == "won't fix":
                params["status_id"] = status_map[8]
            elif status == "re-opened":
                params["status_id"] = status_map[9]
            elif status == "in view":
                params["status_id"] = status_map[10]
            elif status == "ready for testing":
                params["status_id"] = status_map[11]
            else:
                params["status_id"] = status_map.get(status, str(status))

        if priority:
            params["priority_id"] = priority_map.get(priority, str(priority))

        params["limit"] = self.maximum_issues

        issues = []
        offset = 0

        while True:
            params["offset"] = offset

            try:
                response = requests.get(endpoint, params=params)
                response.raise_for_status()
                data = response.json()
                current_issues = data["issues"]
                issues.extend(current_issues)

                if len(current_issues) == 0:
                    break

                offset += len(current_issues)
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error connecting to the server: {str(e)}")
                sys.exit(1)

        return issues

    def fetch_comments(self, issue_id):
        endpoint = f"{self.redmine_url}/issues/{issue_id}/journals.json"
        params = {"key": self.redmine_api_key}
        try:
            response = requests.get(endpoint, params=params)
            if response.status_code == 200:
                return response.json().get("journals", [])
            elif response.status_code == 401:
                raise RedmineAuthenticationError(f"Authentication failed for comments of issue {issue_id}.")
            elif response.status_code == 403:
                raise RedminePermissionError(f"Permission denied for comments of issue {issue_id}.")
            elif response.status_code == 404:
                self.logger.warning(f"Comments not found for issue {issue_id}.")
                return []  # Return an empty list if comments are not found
            else:
                raise RedmineExportError(
                    f"Error fetching comments for issue {issue_id}. HTTP status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error connecting to the server: {str(e)}")
            return []  # Return an empty list in case of connection errors

    def fetch_attachments(self, issue_id):
        endpoint = f"{self.redmine_url}/issues/{issue_id}.json"
        params = {"key": self.redmine_api_key, "include": "attachments"}

        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            data = response.json()
            attachments = data["issue"]["attachments"]

            for attachment in attachments:
                attachment_url = attachment["content_url"]
                attachment_filename = attachment["filename"]
                attachment_path = os.path.join(self.attachments_dir, str(issue_id))
                os.makedirs(attachment_path, exist_ok=True)

                # Download attachment
                attachment_response = requests.get(attachment_url, stream=True)
                attachment_response.raise_for_status()
                with open(os.path.join(attachment_path, attachment_filename), "wb") as file:
                    chunk_size = 50 * 1024 * 1024  # 50MB chunk size
                    for chunk in attachment_response.iter_content(chunk_size=chunk_size):
                        file.write(chunk)
        except Exception as e:
            print(f"Error fetching attachments for issue {issue_id}. Error: {str(e)}")

    def prepare_issue_data(self, issue, comments):
        issue_data = {
            "issue": issue,
            "attachments": [],
            "comments": comments
        }

        self.fetch_attachments(issue["id"])

        attachments_path = os.path.join(self.attachments_dir, str(issue["id"]))
        if os.path.exists(attachments_path):
            issue_data["attachments"] = os.listdir(attachments_path)

        return issue_data

    def export_data(self, data, output_file):
        with open(output_file, "a") as file:
            file.write(json.dumps(data) + "\n")

    def save_progress(self, current_issue_index, progress_file):
        with open(progress_file, "w") as file:
            file.write(str(current_issue_index))

    def load_progress(self, progress_file):
        if not os.path.exists(progress_file):
            return 0
        with open(progress_file, "r") as file:
            return int(file.read())

    def setup_attachments_directory(self):
        os.makedirs(self.attachments_dir, exist_ok=True)

    def setup_projects_directory(self):
        projects_dir = "projects"
        os.makedirs(projects_dir, exist_ok=True)

    def run(self, args):
        configure_logging(args.debug)

        self.setup_attachments_directory()
        self.setup_projects_directory()

        if not args.project:
            self.logger.info("No project specified.")
            return

        status_mapping = {
            1: "new",
            2: "in progress",
            3: "resolved",
            4: "feedback",
            5: "closed",
            6: "rejected",
            7: "approved",
            8: "won't fix",
            9: "re-opened",
            10: "in view",
            11: "ready for testing"
        }

        status_name = status_mapping.get(args.status, "any")
        project_name = args.project
        output_file = f"{project_name}_{status_name}_issues.json"
        progress_file = f"{project_name}_{status_name}_progress.log"

        if os.path.exists(output_file):
            options = [
                "\033[34m1\033[0m) Reset the data and start from scratch",
                "\033[34m2\033[0m) Continue from the last saved progress",
                "\033[90m3\033[0m) Exit and decide later what to do"
            ]
            option_text = "\n".join(options)
            user_choice = input(
                f"The file {output_file} already exists. What do you want to do?\n{option_text}\nEnter the corresponding number: ")

            if user_choice == "1":
                os.remove(output_file)
                os.remove(progress_file)
                self.logger.info(f"Deleted file: {output_file}")
                self.logger.info(f"Deleted file: {progress_file}")
                current_issue_index = 0
            elif user_choice == "2":
                current_issue_index = self.load_progress(progress_file)
                self.logger.info(f"Resuming from issue index: {current_issue_index}")
            elif user_choice == "3":
                self.logger.info("Exiting...")
                return
            else:
                self.logger.info("Invalid choice. Exiting...")
                return
        else:
            current_issue_index = 0

        issues = self.fetch_issues(args.project, args.status, args.priority)
        self.logger.info(f"Total issues found: {len(issues)}")

        rate_limiter = RateLimiter(self.rate_limit_delay)

        try:
            for i, issue in enumerate(issues[current_issue_index:], current_issue_index + 1):
                self.logger.info(f"Processing issue {i}/{len(issues)} (ID: {issue['id']})")

                try:
                    comments = self.fetch_comments(issue["id"])
                    self.logger.info(f"Total comments found for issue {issue['id']}: {len(comments)}")
                    issue_data = self.prepare_issue_data(issue, comments)
                    self.export_data(issue_data, output_file)
                    rate_limiter.wait()
                    self.save_progress(i, progress_file)
                except (RedmineAuthenticationError, RedminePermissionError, RedmineNotFoundError) as e:
                    self.logger.warning(str(e))
                except Exception as e:
                    self.logger.error(f"Error processing issue {issue['id']}: {str(e)}")

        except KeyboardInterrupt:
            self.logger.info("Script interrupted by user.")
            sys.exit(0)
        except (RedmineAuthenticationError, RedminePermissionError, RedmineNotFoundError) as e:
            self.logger.warning(str(e))
        except Exception as e:
            self.logger.error(f"Error processing issue {issue['id']}: {str(e)}")

        self.logger.info("Issue export completed.")


if __name__ == "__main__":
    exporter = RedmineExporter()
    exporter.run(sys.argv[1:])
