import argparse

from utils._logging import configure_logging
from utils._exporter import RedmineExporter
from utils._importer import JiraImporter


def main():
    parser = argparse.ArgumentParser(description="Jira Issue Importer")
    parser.add_argument("-x", "--activate-extraction", action="store_true",
                        help="Activate and import already extracted issues")
    parser.add_argument("-f", "--filename", type=str, default="any_issues.json",
                        help="Specify the issues JSON file name for import")
    parser.add_argument("-p", "--project", type=str,
                        help="Fetch issues for a specific project")
    parser.add_argument("-a", "--attachments", action="store_true",
                        help="Export attachments")
    parser.add_argument("-s", "--status", type=int, choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                        help="Filter issues by status: 1 (new), 2 (inprogress), 3 (resolved), 4 (feedback), 5 (closed), 6 (rejected), 7 (approved), 8 (won't fix), 9 (re-opened), 10 (in view), 11 (ready for testing), 12 (on hold)")
    parser.add_argument("-pr", "--priority", type=int,
                        choices=[1, 2, 3, 4, 5],
                        help="Filter issues by priority: 1 (low), 2 (normal), 3 (high), 4 (urgent), 5 (immediate)")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Enable debug mode (verbose logging)")
    args = parser.parse_args()

    configure_logging(args.debug)

    try:
        if args.activate_extraction:
            importer = JiraImporter()
            importer.import_issues(args.filename)
        else:
            exporter = RedmineExporter()
            exporter.run(args)
    except Exception as e:
        print("An error occurred:", e)


if __name__ == "__main__":
    main()
