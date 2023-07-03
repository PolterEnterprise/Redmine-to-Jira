import os
import json
import time
import requests
import urllib.request
import logging
import coloredlogs
import threading
import argparse
import glob
from queue import PriorityQueue, Queue
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, stop_after_delay, wait_fixed, wait_random, retry_if_exception_type
from jira import JIRA

# Set up logging
logging.basicConfig(filename='issues.log', level=logging.DEBUG)
logger = logging.getLogger()

# Disable propagation for the root logger
logger.propagate = False

# Add console handler
# console = logging.StreamHandler()
# console.setLevel(logging.DEBUG)
# logger.addHandler(console)

# Add colored logs
coloredlogs.install(level='DEBUG', logger=logger)  

# Global constants
attachments_dir = './attachments'

class IssueCreationError(Exception):
    pass

class CommentAddingError(Exception):
    pass

class AttachmentUploadingError(Exception):
    pass

class JiraImporter:
    def __init__(self, jira_server, jira_email, jira_api_token, jira_project_key):
        self.jira = JIRA(jira_server, basic_auth=(jira_email, jira_api_token))
        self.jira_project_key = jira_project_key
        self.pause_event = threading.Event()  # Event to pause and resume operation
        self.pause_event.set()  # Initially set to resume state
        self.condition = threading.Condition()  # Condition variable to synchronize threads

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
    def import_issue(self, issue_data):
        # Preprocess the data, apply encoding and validate
        self.preprocess_issue_data(issue_data)

        # Create the JIRA issue
        new_issue = self.create_jira_issue(issue_data)

        # Update the issue status
        self.update_issue_status(new_issue, issue_data)

        # Add comments to the issue
        self.add_comments_to_issue(new_issue, issue_data)

        # Upload attachments to the issue
        self.upload_attachments_to_issue(new_issue, issue_data)

        return new_issue.key

    def preprocess_issue_data(self, issue_data):
        issue_data["issue"]["subject"] = issue_data["issue"]["subject"].encode('utf-8').decode()
        issue_data["issue"]["description"] = issue_data["issue"]["description"].encode('utf-8').decode()

        # Validate priority exists in Jira
        priorities = self.jira.priorities()
        priority_names = [priority.name for priority in priorities]
        if issue_data["issue"]["priority"]["name"] not in priority_names:
            logger.error(f"Priority {issue_data['issue']['priority']['name']} does not exist in Jira. Setting to default.")
            issue_data["issue"]["priority"]["name"] = priority_names[0]  # Setting to first priority as default

        # Validate issuetype exists in Jira
        issue_types = self.jira.issue_types()
        issue_type_names = [issue_type.name for issue_type in issue_types]
        if issue_data["issue"]["tracker"]["name"] not in issue_type_names:
            logger.error(f"Issue type {issue_data['issue']['tracker']['name']} does not exist in Jira. Setting to default.")
            issue_data["issue"]["tracker"]["name"] = issue_type_names[0]  # Setting to first issue type as default

    def create_jira_issue(self, issue_data):
        issue_dict = {
            'project': {'key': self.jira_project_key},
            'summary': issue_data["issue"]["subject"],
            'description': issue_data["issue"]["description"],
            'issuetype': {'name': issue_data["issue"]["tracker"]["name"]},
            'reporter': {'name': issue_data["issue"]["author"]["name"]},
            'assignee': {'name': issue_data["issue"]["assigned_to"]["name"]},
            'priority': {'name': issue_data["issue"]["priority"]["name"]},
            'duedate': issue_data["issue"]["due_date"],
        }

        try:
            new_issue = self.jira.create_issue(issue_dict)
        except Exception as e:
            logger.error(f"Error occurred while creating issue in Jira. Error: {str(e)}")
            raise IssueCreationError(f"Issue creation failed for issue {issue_data['issue']['id']}")
        return new_issue

    def update_issue_status(self, new_issue, issue_data):
        try:
            new_issue.fields.status = {'name': issue_data["issue"]["status"]["name"]}
            new_issue.update(fields={"status": new_issue.fields.status})
        except Exception as e:
            logger.error(f"Error occurred while setting status for Jira issue {new_issue.key}. Error: {str(e)}")

    def add_comments_to_issue(self, new_issue, issue_data):
        for comment in issue_data["comments"]:
            try:
                self.jira.add_comment(new_issue, comment)
            except Exception as e:
                logger.error(f"Error occurred while adding comment to Jira issue {new_issue.key}. Error: {str(e)}")
                raise CommentAddingError(f"Adding comment failed for issue {issue_data['issue']['id']}")

    def upload_attachments_to_issue(self, new_issue, issue_data):
        for attachment in issue_data["attachments"]:
            with open(os.path.join("./attachments", str(issue_data["issue"]["id"]), attachment), "rb") as file:
                try:
                    self.jira.add_attachment(issue=new_issue.key, attachment=file)
                except Exception as e:
                    logger.error(f"Error occurred while uploading attachment to Jira issue {new_issue.key}. Error: {str(e)}")
                    raise AttachmentUploadingError(f"Uploading attachment failed for issue {issue_data['issue']['id']}")
    
    def user_wants_to_continue(self):
        with self.condition:
            response = input("An error occurred. Do you want to continue? (y/n): ")
            if response.lower() == "y":
                self.pause_event.set()  # Resume operation
                self.condition.notify_all()  # Notify all threads to continue
            else:
                self.pause_event.clear()
            return response.lower() == "y"