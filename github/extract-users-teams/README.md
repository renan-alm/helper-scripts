# GitHub Management CLI

A Python CLI tool to interact with GitHub organizations and extract user information.

## Features

- Fetch all user handles from a GitHub organization
- Export data to JSON format
- Paginated API requests to handle large organizations
- Comprehensive error handling
- Verbose output option

## Prerequisites

- Python 3.6+
- GitHub personal access token with appropriate permissions

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your GitHub token:
```bash
export GITHUB_TOKEN=your_personal_access_token_here
```

## Usage

### Basic Usage

```bash
python gh-management.py <organization> <output_file.json>
```

### Examples

```bash
# Extract users from Microsoft organization
python gh-management.py microsoft users.json

# Extract users with verbose output
python gh-management.py myorg output.json --verbose
```

### Command Line Arguments

- `org` - GitHub organization name (required)
- `output` - Output JSON file path (required)
- `--verbose, -v` - Enable verbose output (optional)

## Output Format

The generated JSON file contains:

```json
{
  "organization": "myorg",
  "total_members": 42,
  "generated_at": "timestamp",
  "user_handles": [
    "user1",
    "user2",
    "user3"
  ]
}
```

## GitHub Token Setup

1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Generate a new token with the following scopes:
   - `read:org` - Read organization membership
   - `read:user` - Read user profile information

3. Set the token as an environment variable:
```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

## Error Handling

The tool handles various error scenarios:

- **Missing GITHUB_TOKEN**: Prompts to set the environment variable
- **Invalid token**: Validates token before making API calls
- **Organization not found**: Clear error message for 404 responses
- **Permission denied**: Handles private organizations or insufficient permissions
- **API rate limits**: Automatically handles GitHub API pagination

## Troubleshooting

### "Organization not found"
- Verify the organization name is correct
- Ensure your token has access to the organization
- Check if the organization is private and you have appropriate permissions

### "Authentication failed"
- Verify your GITHUB_TOKEN is set correctly
- Check if the token has the required scopes
- Ensure the token hasn't expired

### "Access forbidden"
- Your token may not have permission to view the organization's members
- The organization may have member visibility set to private
- Contact the organization admin for access

## Examples of Output

### Small Organization
```json
{
  "organization": "smallcorp",
  "total_members": 5,
  "generated_at": "python-requests/2.32.4",
  "user_handles": [
    "alice",
    "bob",
    "charlie",
    "diana",
    "eve"
  ]
}
```

### Large Organization (truncated)
```json
{
  "organization": "bigcorp",
  "total_members": 1500,
  "generated_at": "python-requests/2.32.4",
  "user_handles": [
    "user001",
    "user002",
    "..."
  ]
}
```
