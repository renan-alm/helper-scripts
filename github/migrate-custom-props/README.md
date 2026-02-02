# GitHub Custom Properties Migration CLI

Migrate custom properties between GitHub Organizations.

## Quick Setup

```bash
# 1. Install dependencies
pip install PyGithub python-dotenv requests

# 2. Configure authentication (choose one)
export GITHUB_TOKEN="ghp_xxxx"
# OR copy .env.example to .env.local and fill in values

# 3. Run
python migrate-custom-props.py --source-org SOURCE --target-org TARGET --dry-run
```

## CLI Options

| Flag | Short | Description |
|------|-------|-------------|
| `--source-org` | `-s` | Source organization to read properties from |
| `--target-org` | `-t` | Target organization to create properties in |
| `--dry-run` | `-d` | Preview mode - no changes made |
| `--source-pat` | | PAT for source org (defaults to `GITHUB_TOKEN`) |
| `--target-pat` | | PAT for target org (defaults to `GITHUB_TOKEN`) |
| `--target-enterprise` | | Enterprise slug for enterprise-level properties |
| `--sync-repos` | | Sync repo property values (repos must exist in both orgs) |

## Configuration Precedence

1. CLI arguments
2. `.env.local` file (same directory as script)
3. Environment variables

## Common Flows

### 1. Preview Migration (Dry Run)

See what properties exist and would be migrated:

```bash
python migrate-custom-props.py -s source-org -t target-org --dry-run
```

### 2. Migrate Org-Level Properties Only

Create property schemas in target org:

```bash
python migrate-custom-props.py -s source-org -t target-org
```

### 3. Include Enterprise Properties

Migrate enterprise-level properties (requires enterprise admin PAT):

```bash
python migrate-custom-props.py -s source-org -t target-org --target-enterprise my-enterprise
```

### 4. Sync Repository Values

Copy property values from repos in source to matching repos in target:

```bash
python migrate-custom-props.py -s source-org -t target-org --sync-repos
```

### 5. Full Migration

Properties + enterprise properties + repo values:

```bash
python migrate-custom-props.py \
  -s source-org \
  -t target-org \
  --target-enterprise my-enterprise \
  --sync-repos
```

### 6. Different PATs for Source/Target

When source and target require different authentication:

```bash
python migrate-custom-props.py \
  -s source-org \
  -t target-org \
  --source-pat ghp_source_token \
  --target-pat ghp_target_token
```

## Using .env.local

Copy `.env.example` to `.env.local`:

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```env
SOURCE_ORG=my-source-org
TARGET_ORG=my-target-org
GITHUB_TOKEN=ghp_xxxx
# Optional
SOURCE_PAT=ghp_source_token
TARGET_PAT=ghp_target_token
TARGET_ENTERPRISE=my-enterprise
```

Then run with minimal flags:

```bash
python migrate-custom-props.py --dry-run
python migrate-custom-props.py --sync-repos
```

## Required Permissions

| Scope | Required For |
|-------|--------------|
| `admin:org` | Read/write org custom properties |
| `repo` | Read repo properties, check repo existence |
| `admin:enterprise` | Enterprise-level properties (with `--target-enterprise`) |

## Property Types

The script handles:

- **Org-level properties** (`source_type: organization`) - Created via PyGithub
- **Enterprise-level properties** (`source_type: enterprise`) - Created via REST API when `--target-enterprise` is set

## Rate Limiting

The script includes automatic rate limit handling:
- Checks remaining API calls before each request
- Waits automatically when approaching limits
- Shows progress updates during long operations

## Output

The script provides emoji-coded output:

- 🚀 Migration start
- 📤 Source organization
- 📥 Target organization  
- 🏷️ Property details
- 🏛️ Org-level property
- 🏢 Enterprise-level property
- ✅ Success
- ❌ Error
- ⏳ In progress
