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
- -x, --activate-extraction [Activate and import already extracted issues]
- -f, --filename [Specify the issues JSON file name for import]
- -p, --project [Fetch issues for a specific project]
- -a, --attachments [Export attachments] <- Feature Functionality still missing
- -c, --comments [Export comments] <- Feature Functionality still missing
- -s, --status [Filter issues by status: 1 (open), 2 (closed)]
- -pr, --priority [Filter issues by priority: 1 (low), 2 (normal), 3 (high), 4 (urgent)]
- -d, --debug [Enable debug mode (verbose logging)]

___
*Features*:
- [x] `importer class`
- [x] `exporter class`
- [ ] `ranges`
- [ ] `threads`
- [ ] `workers`
- [ ] `categorization`
- [ ] `prioritization`
- [x] `improved exception handling`
- [x] `improved logging handling`
- [x] `encapsulation`
- [ ] `simplification for conditional logic`
- [ ] `appropriate abstractions`
- [ ] `improvement of readability`
- [x] `rate limiter optimization`
- [ ] `memory implementation`
- [ ] `refactoring`
___

**YOU DO NOT HAVE PERMISSION TO MODIFY THIS PROJECT'S CORE FUNCTIONALITY WITHOUT A PROPER CONSENT**

*(C) Polter Enterprise | All rights reserved! [Website](https://poltersanctuary.com). [Discord](https://discord.gg/eVvPpe7).*
