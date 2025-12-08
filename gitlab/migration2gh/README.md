# GitLab to GitHub Migration Scripts

A collection of Python scripts to help migrate GitLab projects to GitHub, including issues, comments, milestones, and relationships.

## Prerequisites

Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Setup

Create a `.env` file in this directory with the required credentials:

```bash
GITLAB_API_PRIVATE_TOKEN=your_gitlab_token
GITLAB_API_ENDPOINT=https://gitlab.com/api/v4
GITLAB_REPO_URL=https://gitlab.com/namespace/project

GITHUB_TOKEN=your_github_token
GITHUB_REPO_URL=https://github.com/org/repo
```

## Scripts Overview

### 1. gitlab-milestones-mapper.py

Maps GitLab milestones to GitHub and applies them to issues.

**Workflow:**

1. Create a mapping file from GitLab milestones
2. Create milestones in GitHub
3. Apply milestones to GitHub issues

**Usage:**

Create mapping file:

```bash
python gitlab-milestones-mapper.py create-map
```

Create milestones in GitHub from mapping:

```bash
python gitlab-milestones-mapper.py create-milestones
```

Apply milestones to GitHub issues (all-in-one):

```bash
python gitlab-milestones-mapper.py apply-milestones
```

**Options:**

- `--verbose` - Show detailed information
- `--output FILE` - Specify output mapping file (default: `milestones-map.csv`)
- `--input FILE` - Specify input mapping file (default: `milestones-map.csv`)
- `--diagnostic` - Run without making changes

### 2. gitlab-comment-mapper.py

Migrates GitLab issue comments to GitHub issues.

**Workflow:**

1. Create a mapping file of GitLab comments
2. Apply comments to corresponding GitHub issues

**Usage:**

Create mapping file:

```bash
python gitlab-comment-mapper.py create-map
```

Apply comments to GitHub issues:

```bash
python gitlab-comment-mapper.py apply-nesting
```

**Options:**

- `--verbose` - Show detailed information
- `--output FILE` - Specify output mapping file (default: `comments-map.csv`)
- `--input FILE` - Specify input mapping file (default: `comments-map.csv`)
- `--diagnostic` - Run without making changes

### 3. gitlab-relationship-mapper.py

Maps and applies issue relationships (links, blockers, etc.) between GitLab and GitHub.

**Workflow:**

1. Create a mapping file of issue relationships from GitLab
2. Apply relationships to GitHub issues

**Usage:**

Create mapping file:

```bash
python gitlab-relationship-mapper.py create-map
```

Apply relationships to GitHub issues:

```bash
python gitlab-relationship-mapper.py apply-relationships
```

**Options:**

- `--verbose` - Show detailed information
- `--output FILE` - Specify output mapping file (default: `relationships-map.csv`)
- `--input FILE` - Specify input mapping file (default: `relationships-map.csv`)
- `--diagnostic` - Run without making changes
- `--report-file FILE` - Save diagnostic report to file
- `--skip-github-validation` - Skip GitHub validation (useful for testing)
- `--summary-only` - Show only summary in diagnostic mode

### 4. gitlab-github-url-replacer.py

Finds and replaces GitLab URLs and repository references in GitHub issues and PRs with GitHub URLs.

**Workflow:**

1. Scan GitHub repository for GitLab URLs and repo references
2. Create mapping file of found URLs
3. Execute replacements

**Usage:**

Create mapping file:

```bash
python gitlab-github-url-replacer.py create-map
```

Execute replacements:

```bash
python gitlab-github-url-replacer.py execute
```

Re-validate existing mapping:

```bash
python gitlab-github-url-replacer.py revalidate
```

Test a single URL:

```bash
python gitlab-github-url-replacer.py test-url --url https://github.com/org/repo/issues/1
```

**Options:**

- `--csv-file FILE` - Specify mapping file (default: `gh-links.csv`)
- `--output-csv FILE` - Output file for revalidation (default: overwrite input)
- `--dry-run` - Run without making changes
- `--force` - Replace URLs even if not validated
- `--verbose` - Show detailed information

## Migration Mapping Files

The scripts generate/use CSV mapping files:

- `milestones-map.csv` - Milestone mappings
- `comments-map.csv` - Comment mappings
- `relationships-map.csv` - Issue relationship mappings
- `gh-links.csv` - GitHub URL mappings

## Example Migration Workflow

```bash
# 1. Set up environment
# (Create .env file with your tokens)

# 2. Migrate milestones
python gitlab-milestones-mapper.py apply-milestones

# 3. Migrate comments
python gitlab-comment-mapper.py create-map
python gitlab-comment-mapper.py apply-nesting

# 4. Migrate relationships
python gitlab-relationship-mapper.py create-map
python gitlab-relationship-mapper.py apply-relationships

# 5. Replace URLs
python gitlab-github-url-replacer.py create-map
python gitlab-github-url-replacer.py execute --dry-run  # Preview changes
python gitlab-github-url-replacer.py execute             # Apply changes
```

## Diagnostic Mode

All scripts support diagnostic mode to preview changes without making modifications:

```bash
python script_name.py command --diagnostic
```

Use `--verbose` to see detailed information:

```bash
python script_name.py command --verbose --diagnostic
```
