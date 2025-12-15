# GitHub CLI (gh) - 10 Common Use Cases

The GitHub CLI makes it easy to use GitHub from the command line. Here are the most practical examples.

## 1. Authentication - Login to GitHub

```bash
# Authenticate with GitHub (opens browser for OAuth)
gh auth login

# Choose protocol and authentication method when prompted
# Select HTTPS, GitHub.com, and follow OAuth flow

# Check current authentication status
gh auth status
```

**Use Case**: First-time setup or re-authenticating with GitHub.

---

## 2. List Issues - Find Tasks to Work On

```bash
# List open issues in current repo
gh issue list

# List with filters
gh issue list --state open --assignee @me

# List issues with specific labels
gh issue list --label "bug,help wanted"

# List issues assigned to someone
gh issue list --assignee username

# List in table format with limit
gh issue list --limit 20 --state open
```

**Use Case**: Quick view of what needs to be done without opening the browser.

---

## 3. Create an Issue - Report a Bug or Feature

```bash
# Interactive issue creation
gh issue create

# Create with inline options
gh issue create --title "Fix login bug" --body "Users cannot login with email" --label "bug" --assignee @me

# Create with title only (opens editor for body)
gh issue create --title "Improve documentation"

# Create and get the URL
gh issue create --title "New feature" --body "Description here" --web
```

**Use Case**: Quick bug reports and feature requests without leaving the terminal.

---

## 4. View Issue Details - Get Full Context

```bash
# View specific issue details
gh issue view 42

# View in browser
gh issue view 42 --web

# View with comments
gh issue view 42 --comments

# View a closed issue
gh issue view 42 --state all
```

**Use Case**: Review issue details, comments, and history before starting work.

---

## 5. List Pull Requests - Track Reviews

```bash
# List open pull requests
gh pr list

# List PRs assigned to you
gh pr list --assignee @me

# List PRs you created
gh pr list --author @me

# List PRs waiting for your review
gh pr list --search "review-requested:@me"

# List with status checks
gh pr list --state open --limit 10
```

**Use Case**: Stay on top of PRs needing attention or review.

---

## 6. Create a Pull Request - Submit Code Changes

```bash
# Create PR interactively
gh pr create

# Create with inline options
gh pr create --title "Add user authentication" --body "Implements OAuth flow" --base main

# Create and open in browser
gh pr create --title "Feature: Dark mode" --draft

# Create from branch with auto-body
gh pr create --title "Fix: Memory leak" --web
```

**Use Case**: Submit changes for review without using the GitHub web interface.

---

## 7. Check PR Status - Monitor Reviews and Checks

```bash
# View PR details
gh pr view 123

# View in browser
gh pr view 123 --web

# Check review status
gh pr view 123 --comments

# View PR checks/CI status
gh pr view 123
```

**Use Case**: Verify CI passes and reviews are complete before merging.

---

## 8. Manage Branches - List and Delete

```bash
# List local branches
gh repo view --json defaultBranchRef

# List all branches
git branch -a

# Delete a branch after PR merge
git branch -d feature/login

# Delete remote branch
git push origin --delete feature/login

# Create feature branch from issue
gh repo clone owner/repo
cd repo
git checkout -b feature/issue-123
```

**Use Case**: Clean branch management and staying organized.

---

## 9. Run Workflows - Trigger GitHub Actions

```bash
# List workflows in repo
gh workflow list

# View workflow runs
gh run list

# View specific run details
gh run view run-id

# View run logs
gh run view run-id --log

# Trigger workflow manually (if set up for manual trigger)
gh workflow run workflow-name.yml

# Cancel a run
gh run cancel run-id
```

**Use Case**: Monitor CI/CD pipelines and troubleshoot failing builds.

---

## 10. Create Release - Package and Deploy

```bash
# Create a release interactively
gh release create

# Create release with title and notes
gh release create v1.0.0 --title "Version 1.0" --notes "First stable release"

# Create release with auto-generated notes
gh release create v1.0.0 --generate-notes

# Create pre-release
gh release create v2.0.0-beta --prerelease

# Create and upload files
gh release create v1.0.0 --notes "Release notes" ./dist/app.zip

# View releases
gh release list

# View specific release
gh release view v1.0.0
```

**Use Case**: Automate release management and distribution.

---

## Bonus: Search and Clone - Find Repositories

```bash
# Clone a repository
gh repo clone owner/repo
cd repo

# View repo information
gh repo view

# View repo in browser
gh repo view --web

# Get repository URL
gh repo view --json url

# List repositories for an organization
gh repo list organization-name --limit 50
```

---

## Pro Tips

### Alias Commands for Speed
```bash
# Create aliases for frequently used commands
gh alias set issues 'issue list --state open --limit 10'
gh alias set prs 'pr list --assignee @me'
gh alias set ready 'pr list --search "draft:false review-requested:@me"'

# Use them
gh issues    # Lists open issues
gh prs       # Lists your PRs
gh ready     # Shows PRs waiting for your review
```

### Environment Variables
```bash
# Set default GitHub host
export GH_HOST=github.enterprise.com

# Disable paging for scripts
export GH_PAGER=cat

# Set editor for PR/issue creation
export GH_EDITOR=vim
```

### Piping and Automation
```bash
# Get issue URLs
gh issue list --json url --jq '.[].url'

# Count open issues
gh issue list --jq 'length'

# List issue titles
gh issue list --json title --jq '.[].title'

# Programmatic access
gh api repos/owner/repo/issues --jq '.[0]'
```

---

## Common Workflow Example

```bash
# 1. List issues you can work on
gh issue list --assignee @me --state open

# 2. Claim an issue
gh issue view 42
gh issue edit 42 --assignee @me

# 3. Create and switch to feature branch
git checkout -b feature/issue-42

# 4. Make changes and commit
git add .
git commit -m "Fix: resolve issue #42"

# 5. Create a pull request
gh pr create --title "Fix issue #42" --body "Closes #42"

# 6. Monitor your PR
gh pr view

# 7. After merge, cleanup
git checkout main
git pull
git branch -d feature/issue-42
```

---

## Resources

- **Official Docs**: https://cli.github.com
- **Manual**: `gh help` or `gh help <command>`
- **Check specific command**: `gh issue --help`
- **API Documentation**: https://docs.github.com/en/rest
