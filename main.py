import argparse
from utils._exporter import RedmineExporter
from utils._logging import configure_logging

def main():
    parser = argparse.ArgumentParser(description="Redmine Issue Exporter")
    parser.add_argument("-p", "--project", type=str, help="Fetch issues for a specific project")
    parser.add_argument("-a", "--attachments", action="store_true", help="Export attachments")
    parser.add_argument("-s", "--status", type=int,
                        choices=[1, 2, 3, 4, 5, 6],
                        help="Filter issues by status: 1 (new), 2 (in progress), 3 (resolved), 4 (feedback), 5 (closed), 6 (rejected)")
    parser.add_argument("-pr", "--priority", type=int,
                        choices=[1, 2, 3, 4, 5],
                        help="Filter issues by priority: 1 (low), 2 (normal), 3 (high), 4 (urgent), 5 (immediate)")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug mode (verbose logging)")
    args = parser.parse_args()

    configure_logging(args.debug)

    exporter = RedmineExporter()
    exporter.run(args)

if __name__ == "__main__":
    main()
