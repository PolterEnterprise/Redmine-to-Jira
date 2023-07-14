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
- -s, --status [Filter issues by status: 1 (new), 2 (inprogress), 3 (resolved), 4 (feedback), 5 (closed), 6 (rejected), 7 (approved), 8 (won't fix), 9 (re-opened), 10 (in view), 11 (ready for testing)]
- -pr, --priority [Filter issues by priority: 1 (low), 2 (normal), 3 (high), 4 (urgent)]
- -d, --debug [Enable debug mode (verbose logging)]

___
*Features*:
- [x] `importer class`
- [x] `exporter class`
- [ ] `ranges`
- [ ] `threads`
- [ ] `workers`
- [ ] `chunks`
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
___

**YOU DO NOT HAVE PERMISSION TO MODIFY THIS PROJECT'S CORE FUNCTIONALITY WITHOUT A PROPER CONSENT**

*(C) Polter Enterprise | All rights reserved! [Website](https://poltersanctuary.com). [Discord](https://discord.gg/eVvPpe7).*
