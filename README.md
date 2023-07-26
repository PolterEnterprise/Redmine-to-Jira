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
- -x, --activate-extraction [Activate and import already extracted issues] <- will be modified in future updates
- -f, --filename [Specify the issues JSON file name for import]
- -p, --project [Fetch issues for a specific project]
- -a, --attachments [Export attachments] <- will be modified in future updates
- -c, --comments [Export comments] <- will be modified in future updates
- -s, --status [Filter issues by status: 1 (New), 2 (In Progress), 3 (Ready For Testing), 4 (Feedback), 5 (Closed), 6 (Rejected), 7 (Approved), 8 (Re-Opened), 9 (Won't Fix), 10 (On Hold), 11 (In Review)]
- -pr, --priority [Filter issues by priority: 1 (Highest), 2 (High), 3 (Medium), 4 (Low), 5 (Lowest)]
- -d, --debug [Enable debug mode (verbose logging)] <- will be modified in future updates

___
*Implementations*: (under dev)
- [x] `importer class`
- [x] `exporter class`
- [x] `ranges`
- [ ] `threads`
- [ ] `workers`
- [ ] `chunks`
- [x] `refined attachments`
- [x] `categorization`
- [x] `prioritization`
- [x] `improved exception handling`
- [x] `improved logging handling`
- [x] `encapsulation`
- [x] `simplification for conditional logic`
- [x] `appropriate abstractions`
- [x] `improvement of readability`
- [x] `rate limiter optimization`
- [x] `logging optimization`
- [x] `memory progress`
___

**YOU DO NOT HAVE PERMISSION TO MODIFY THIS PROJECT'S CORE FUNCTIONALITY WITHOUT A PROPER CONSENT**

*(C) Polter Enterprise | All rights reserved! [Website](https://poltersanctuary.com). [Discord](https://discord.gg/eVvPpe7).*
