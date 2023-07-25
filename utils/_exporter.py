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
        try:
            config = ConfigParser()
            config.read('config.ini')

            # Configuration
            self.redmine_url = config.get('Redmine', 'url')
            self.redmine_api_key = config.get('Redmine', 'api_key')
            self.attachments_dir = config.get('Exporter', 'attachments_dir')
            self.projects_dir = config.get('Exporter', 'projects_dir')
            self.log_file = config.get('Exporter', 'log_file')
            self.rate_limit_delay = config.getint('Exporter', 'rate_limit_delay')
            self.maximum_issues = config.getint('Exporter', 'maximum_issues')
        except ConfigParser.NoSectionError as e:
            raise RedmineExportError(f"Error in configuration file: {str(e)}")
        except ConfigParser.NoOptionError as e:
            raise RedmineExportError(f"Missing required option in configuration file: {str(e)}")
        except Exception as e:
            raise RedmineExportError(f"Error reading configuration: {str(e)}")

        self.logger = setup_logger(self.log_file)

        self.status_map = {
            1: '1',   # New issues (The issue is newly created and not yet assigned or in progress.)
            2: '2',   # In Progress issues (The issue is actively being worked on.)
            3: '3',   # Ready for Testing issues (The issue is ready for testing or quality assurance.)
            4: '4',   # Feedback issues (The issue is awaiting feedback or further input.)
            5: '5',   # Closed issues (The issue has been closed and is considered complete.)
            6: '6',   # Rejected issues (The issue has been rejected or deemed invalid.)
            7: '7',   # Approved issues (The issue has been approved and can proceed.)
            8: '8',   # Re-opened issues (The issue was previously closed but has been reopened for further work.)
            9: '9',   # Won't Fix issues (The issue will not be fixed or addressed.)
            10: '10', # On Hold issues
            11: '11', # Resolved issues (The issue has been resolved or completed.)
            12: '12'  # In View issues (The issue is being reviewed or examined.)
        }

        self.status_name_map = {
            1: 'New',
            2: 'In-Progress',
            3: 'Ready-for-Testing',
            4: 'Feedback',
            5: 'Closed',
            6: 'Rejected',
            7: 'Approved',
            8: 'Re-Opened',
            9: 'Wont-Fix',
            10: 'On-Hold',
            11: 'Resolved',
            12: 'In View'
        }

        self.priority_map = {
            1: '1',  # Low priority
            2: '2',  # Normal priority
            3: '3',  # High priority
            4: '4',  # Urgent priority
            5: '5'   # Immediate priority
        }

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

    def fetch_data(self, endpoint, params):
        try:
            response = requests.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error connecting to the server: {str(e)}")
            return None

    def fetch_data_with_pagination(self, endpoint, params):
        data = []
        offset = 0
        while True:
            params["offset"] = offset
            response_data = self.fetch_data(endpoint, params)

            if response_data is None or 'issues' not in response_data:
                break

            current_data = response_data["issues"]
            data.extend(current_data)

            if len(current_data) == 0:
                break

            offset += len(current_data)
        
        return data

    def fetch_issues(self, project_id=None, status=None, priority=None):
        if not self.validate_input(project_id, (int, str, type(None))):
            raise ValueError('Invalid project_id. Expected int, str or None.')
        if not self.validate_input(status, (int, type(None))):
            raise ValueError('Invalid status. Expected int or None.')
        if not self.validate_input(priority, (int, type(None))):
            raise ValueError('Invalid priority. Expected int or None.')

        params = {"key": self.redmine_api_key}

        if project_id:
            project_id = self.sanitize_input(project_id)
            self.logger.info(f"Fetching issues for project: {project_id}")
            params["project_id"] = project_id
        else:
            self.logger.info("Fetching all issues")
            params["subproject_id"] = "!*"

        if status is not None:
            status = self.sanitize_input(status)
            params["status_id"] = self.status_map.get(status, str(status))

        if priority:
            priority = self.sanitize_input(priority)
            params["priority_id"] = self.priority_map.get(priority, str(priority))

        params["limit"] = self.maximum_issues

        endpoint = f"{self.redmine_url}/issues.json"
        return self.fetch_data_with_pagination(endpoint, params)

    def fetch_journals(self, issue_id):
        endpoint = f"{self.redmine_url}/issues/{issue_id}.json"
        params = {"key": self.redmine_api_key, "include": "journals"}

        data = self.fetch_data(endpoint, params)

        if data is None or 'issue' not in data:
            return None

        journals = data["issue"].get("journals", [])
        total_journals = len(journals)

        self.logger.info(f"Total journals found for issue ({issue_id}): {total_journals}")

        journals_data = []
        for index, journal in enumerate(journals, start=1):
            self.logger.info(f"Processing journal: {index}/{total_journals}")
            try:
                parsed_journal = self.parse_journals([journal])[0]
                self.logger.info(f"Successfully fetched and processed journal: {index}")
                journals_data.append(parsed_journal)
            except Exception as e:
                self.logger.error(f"Error processing journal {index} for issue {issue_id}: {str(e)}")
                continue

        self.logger.info(f"Journals processing completed for issue {issue_id}")
        return journals_data

    def parse_journals(self, journals):
        journals_data = []
        for journal in journals:
            journal_id = journal.get("id")
            user = journal.get("user", {})
            created_on = journal.get("created_on")
            notes = journal.get("notes")

            comments = notes.split("\r\n") if notes else []

            entry = {
                "id": journal_id,
                "user": {
                    "id": user.get("id"),
                    "name": user.get("name")
                },
                "created_on": created_on,
                "notes": notes,
                "private_notes": journal.get("private_notes"),
                "comments": comments
            }

            journals_data.append(entry)

        return journals_data

    def fetch_attachments(self, issue_id):
        endpoint = f"{self.redmine_url}/issues/{issue_id}.json"
        params = {"key": self.redmine_api_key, "include": "attachments"}

        try:
            data = self.fetch_data(endpoint, params)

            if data is None or 'issue' not in data or 'attachments' not in data['issue']:
                return None

            attachments = data["issue"]["attachments"]
            total_attachments = len(attachments)

            self.logger.info(f"Total attachments found for issue ({issue_id}): {total_attachments}")

            for index, attachment in enumerate(attachments, start=1):
                attachment_url = attachment["content_url"]
                attachment_filename = attachment["filename"]

                attachment_content = self.fetch_attachment_content(attachment_url, attachment_filename, index, total_attachments)
                if attachment_content is not None:
                    self.save_attachment(issue_id, attachment_filename, attachment_content, index)

            self.logger.info(f"Attachment processing completed for issue {issue_id}")
        except requests.exceptions.HTTPError as errh:
            self.logger.error(f"Http Error while fetching issue from {endpoint}: {errh}")
        except requests.exceptions.ConnectionError as errc:
            self.logger.error(f"Error Connecting while fetching issue from {endpoint}: {errc}")
        except requests.exceptions.Timeout as errt:
            self.logger.error(f"Timeout Error while fetching issue from {endpoint}: {errt}")
        except requests.exceptions.RequestException as err:
            self.logger.error(f"Oops: Something Else while fetching issue from {endpoint}: {err}")

    def fetch_attachment_content(self, attachment_url, attachment_name, index, total):
        try:
            self.logger.info(f"Processing attachment ({attachment_name}): {index}/{total}")
            attachment_response = requests.get(attachment_url, stream=True)
            attachment_response.raise_for_status()
            return attachment_response
        except requests.exceptions.HTTPError as errh:
            self.logger.error(f"Fetching attachment ({index}) from ({attachment_url}) failed: Http Error: {errh}")
            return None
        except requests.exceptions.ConnectionError as errc:
            self.logger.error(f"Fetching attachment ({index}) from ({attachment_url}) failed: Error Connecting: {errc}")
            return None
        except requests.exceptions.Timeout as errt:
            self.logger.error(f"Fetching attachment ({index}) from ({attachment_url}) failed: Timeout Error: {errt}")
            return None
        except requests.exceptions.RequestException as err:
            self.logger.error(f"Fetching attachment ({index}) from ({attachment_url}) failed: Something Else: {err}")
            return None

    def save_attachment(self, issue_id, attachment_filename, attachment_content, index):
        try:
            attachment_path = os.path.join(self.attachments_dir, str(issue_id))
            os.makedirs(attachment_path, exist_ok=True)
            
            with open(os.path.join(attachment_path, attachment_filename), "wb") as file:
                chunk_size = 50 * 1024 * 1024  # 50MB chunk size
                for chunk in attachment_content.iter_content(chunk_size=chunk_size):
                    file.write(chunk)
            self.logger.info(f"Successfully fetched and saved attachment ({attachment_filename}): {index} ")
        except PermissionError:
            self.logger.error(f"Permission denied while saving attachment for issue {issue_id}. Check if the program has write access to the destination directory.")
        except IOError as e:
            self.logger.error(f"I/O error({e.errno}): {e.strerror} while saving attachment for issue {issue_id}.")
        except Exception as e:
            self.logger.error(f"Unexpected error occurred while saving attachment for issue {issue_id}: {str(e)}")

    def prepare_issue_data(self, issue, journals, attachments):
        if 'id' not in issue:
            self.logger.error(f"Issue does not contain 'id' key: {issue}")
            return None

        issue_data = {
            "issue": issue,
            "attachments": attachments,
            "journals": journals
        }
        return issue_data

    def process_issue(self, issue, output_file):
        try:
            try:
                journals = self.fetch_journals(issue["id"])  
            except Exception as e:
                self.logger.error(f"Error fetching journals for issue {issue['id']}: {str(e)}")
                return

            try:
                attachments = self.fetch_attachments(issue["id"])  
            except Exception as e:
                self.logger.error(f"Error fetching attachments for issue {issue['id']}: {str(e)}")
                return

            attachments_path = os.path.join(self.attachments_dir, str(issue["id"]))
            if os.path.exists(attachments_path):
                attachments = os.listdir(attachments_path)

            try:
                issue_data = self.prepare_issue_data(issue, journals, attachments)
            except Exception as e:
                self.logger.error(f"Error preparing data for issue {issue['id']}: {str(e)}")
                return

            if issue_data is None:
                self.logger.error(f"Failed to prepare data for issue {issue['id']}.")
                return

            self.export_data(issue_data, output_file)
        except (RedmineAuthenticationError, RedminePermissionError, RedmineNotFoundError) as e:
            self.logger.warning(str(e))
        except KeyboardInterrupt:
            self.logger.info("Script interrupted by user. Current issue will finish processing before exiting.")
            raise  # re-raise the exception to be caught in the run method
        except Exception as e:
            self.logger.error(f"Error processing issue {issue['id']}: {str(e)}")

    def export_data(self, data, output_file):
        try:
            with open(output_file, "a") as file:
                file.write(json.dumps(data) + "\n")
            self.logger.info(f"Successfully exported data for issue {data['issue']['id']}.")
        except IOError as e:
            self.logger.error(f"IOError while trying to write to {output_file} for issue {data['issue']['id']}: {str(e)}")
        except TypeError as e:
            self.logger.error(f"TypeError while trying to convert data to JSON for issue {data['issue']['id']}: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error while trying to export data for issue {data['issue']['id']}: {str(e)}")

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
        os.makedirs(self.projects_dir, exist_ok=True)

    def run(self, args):
        configure_logging(args.debug)

        self.setup_attachments_directory()
        self.setup_projects_directory()

        if not args.project:
            self.logger.info("No project specified.")
            return

        status_id = args.status  # This should be the integer status id
        status_name = self.status_name_map.get(status_id, "any").replace(' ', '-')

        project_name = args.project.replace(' ', '-')

        output_file = f"{project_name}_{status_name}_issues.json"
        progress_file = f"{project_name}_{status_name}_progress.log"

        if os.path.exists(output_file):
            options = [
                "\033[34m1\033[0m) Reset the data and start from scratch",
                "\033[34m2\033[0m) Continue from the last saved progress",
                "\033[90m3\033[0m) Exit and decide later what to do"
            ]
            option_text = "\n".join(options)

            try:  # Add this try/except block
                user_choice = input(
                    f"The file {output_file} already exists. What do you want to do?\n{option_text}\nEnter the corresponding number: ")
            except KeyboardInterrupt:
                self.logger.info("Exiting due to keyboard interrupt...")
                return

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
                self.logger.info(f"Processing issue ({issue['id']}): {i}/{len(issues)}")
                self.process_issue(issue, output_file)
                rate_limiter.wait()
                self.save_progress(i, progress_file)
        except KeyboardInterrupt:
            sys.exit(0)
        except (RedmineAuthenticationError, RedminePermissionError, RedmineNotFoundError) as e:
            self.logger.warning(str(e))
        except Exception as e:
            self.logger.error(f"Error: {str(e)}")

        self.logger.info("Issue export completed.")


if __name__ == "__main__":
    exporter = RedmineExporter()
    exporter.run(sys.argv[1:])
