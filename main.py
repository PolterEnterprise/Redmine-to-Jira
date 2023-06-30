# ############################################################################## #
# Created by Polterx, on Friday 30th of June, 2023                               #
# Website https://poltersanctuary.com                                            #
# ############################################################################## #
# The script is in development mode, might not work as intended for every user   #
# ############################################################################## #

import argparse
import json
import os
import sys
import requests
import time
import shutil

from configparser import ConfigParser
from utils._logging import setup_logger
import logging
import coloredlogs

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

        if status:
            params["status_id"] = status

        if priority:
            params["priority_id"] = priority

        params["limit"] = 100

        issues = []

        offset = 0
        total_count = 0
        while True:
            params["offset"] = offset
            try:
                response = requests.get(endpoint, params=params)
                response.raise_for_status()
                data = response.json()
                current_issues = data["issues"]
                issues.extend(current_issues)
                total_count = data["total_count"]
                if len(issues) >= total_count:
                    break
                offset += params["limit"]
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error connecting to the server: {str(e)}")
                sys.exit(1)

        return issues

    def fetch_comments(self, issue_id):
        endpoint = f"{self.redmine_url}/issues/{issue_id}/comments.json"
        params = {"key": self.redmine_api_key}
        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            if response.status_code == 200:
                return response.json()["comments"]
            elif response.status_code == 401:
                raise RedmineAuthenticationError(f"Authentication failed for comments of issue {issue_id}.")
            elif response.status_code == 403:
                raise RedminePermissionError(f"Permission denied for comments of issue {issue_id}.")
            elif response.status_code == 404:
                raise RedmineNotFoundError(f"Comments not found for issue {issue_id}.")
            else:
                raise RedmineExportError(f"Error fetching comments for issue {issue_id}. HTTP status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error connecting to the server: {str(e)}")
            sys.exit(1)

    def fetch_attachments(self, issue_data):
        issue_id = issue_data["id"]
        attachments = issue_data["attachments"]
        attachment_path = os.path.join(self.attachments_dir, str(issue_id))

        if attachments and not os.path.exists(attachment_path):
            os.makedirs(attachment_path, exist_ok=True)
            self.logger.info(f"Downloading attachments for issue {issue_id}")

            for attachment in attachments:
                attachment_url = attachment["content_url"]
                attachment_filename = attachment["filename"]
                full_path = os.path.join(attachment_path, attachment_filename)

                try:
                    response = requests.get(attachment_url, stream=True)
                    response.raise_for_status()
                    with open(full_path, "wb") as file:
                        shutil.copyfileobj(response.raw, file)
                    del response
                except Exception as e:
                    self.logger.warning(f"Error downloading attachment: {str(e)}")

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

    def main(self):
        parser = argparse.ArgumentParser(description="Redmine Issue Exporter")
        parser.add_argument("-p", "--project", type=str, help="Fetch issues for a specific project")
        parser.add_argument("-a", "--attachments", action="store_true", help="Export attachments")
        parser.add_argument("-s", "--status", type=int, choices=[1, 2], help="Filter issues by status: 1 (open), 2 (closed)")
        parser.add_argument("-pr", "--priority", type=int, choices=[1, 2, 3, 4], help="Filter issues by priority: 1 (low), 2 (normal), 3 (high), 4 (urgent)")
        parser.add_argument("-d", "--debug", action="store_true", help="Enable debug mode (verbose logging)")
        args = parser.parse_args() 

        if args.debug:
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO

        coloredlogs.install(level=log_level, fmt='%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s')
        logging.basicConfig(level=log_level, filename=self.log_file)

        if args.attachments:
            self.setup_attachments_directory()

        if args.project:
            if args.status == 1:
                output_file = "redmine_open_issues.json"
                progress_file = "redmine_open_progress.log"
            elif args.status == 2:
                output_file = "redmine_closed_issues.json"
                progress_file = "redmine_closed_progress.log"
            else:
                output_file = "redmine_any_issues.json"
                progress_file = "redmine_any_progress.log"

            if os.path.exists(output_file):
                options = [
                    f"\033[34m1\033[0m) Reset the data and start from scratch",
                    f"\033[34m2\033[0m) Continue from the last saved progress",
                    f"\033[90m3\033[0m) Exit and decide later what to do"
                ]
                option_text = "\n".join(options)
                user_choice = input(f"The file {output_file} already exists. What do you want to do?\n{option_text}\nEnter the corresponding number: ")

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

            for i, issue in enumerate(issues[current_issue_index:], current_issue_index + 1):
                self.logger.info(f"Processing issue {i}/{len(issues)} (ID: {issue['id']})")

                try:
                    if "attachments" in issue:
                        self.fetch_attachments(issue)
                    self.export_data(issue, output_file)
                    if "comments" in issue:
                        comments = self.fetch_comments(issue["id"])
                        self.logger.info(f"Total comments found for issue {issue['id']}: {len(comments)}")
                        for comment in comments:
                            self.export_data(comment, output_file)
                    rate_limiter.wait()
                    self.save_progress(i, progress_file)
                except (RedmineAuthenticationError, RedminePermissionError, RedmineNotFoundError) as e:
                    self.logger.warning(str(e))
                except Exception as e:
                    self.logger.error(f"Error processing issue {issue['id']}: {str(e)}")

            self.logger.info("Issue export completed.")
        else:
            self.logger.info("No project specified.")

class RateLimiter:
    def __init__(self, delay):
        self.delay = delay
        self.last_request_time = time.time()

    def wait(self):
        elapsed_time = time.time() - self.last_request_time
        if elapsed_time < self.delay:
            time.sleep(self.delay - elapsed_time)
        self.last_request_time = time.time()

if __name__ == "__main__":
    exporter = RedmineExporter()
    exporter.main()
