# MigrationV2-Redmine-to-Jira


### How to run?
```
python ./main.py -arg 
```
### Missing Packages?
```
pip install -r requirements.txt
```

### List of Available Arguments
- -p, --project [Fetch issues for a specific project]
- -a, --attachments [Export attachments] <- Feature Functionality still missing
- -c, --comments [Export comments] <- Feature Functionality still missing
- -s, --status [Filter issues by status: 1 (open), 2 (closed)]
- -pr, --priority [Filter issues by priority: 1 (low), 2 (normal), 3 (high), 4 (urgent)]
- -d, --debug [Enable debug mode (verbose logging)]
