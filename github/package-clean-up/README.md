# package-clean-up

Find GitHub Packages in an organization by regex, review the list manually, then delete them.

## Setup

From this directory, create and activate a virtual environment, then install the dependencies:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Debian/Ubuntu, install `python3-venv` first if `venv` complains that `ensurepip` is missing.

Copy the template to the ignored `.env` file and edit it:

```sh
cp .env.example .env
```

Run `deactivate` when done.

`.env` variables:

| Variable   | Description                                                        |
|------------|--------------------------------------------------------------------|
| `ORG`      | GitHub organization                                                |
| `GH_TOKEN` | PAT with `read:packages`, `delete:packages` (and `repo` for packages linked to private repos) |
| `DIR`      | Where the review CSV is written (default `~/.cache/packages-to-clean-up`) |
| `DRY_RUN`  | `true` (default) only prints what would be deleted                 |

## Usage

### 1. List matching packages

```sh
./package-clean-up.py list '^legacy-'
./package-clean-up.py list 'snapshot$' --package-type maven npm --case-sensitive
./package-clean-up.py --env-file other.env list 'old' -o review.csv
```

Scans all package types (`npm`, `maven`, `rubygems`, `docker`, `nuget`, `container`) unless `--package-type` is given, and writes `$DIR/packages-<org>.csv`. The regex is matched with `re.search` (case-insensitive by default).

### 2. Review

Open the CSV. Every row starts with `delete=yes`. Set it to `no`, or remove the row, for packages you want to keep.

### 3. Delete

```sh
./package-clean-up.py delete                 # honors DRY_RUN from .env
./package-clean-up.py delete --no-dry-run    # actually delete
./package-clean-up.py delete -i review.csv --no-dry-run -y   # skip confirmation
```

Before each deletion the script asks `Delete [type] name? [y/N/a/q]`: `y` deletes it, `n` or Enter skips it, `a` deletes it and all remaining without asking, and `q` stops. Pass `-y` to skip the prompts. It exits non-zero if any deletion fails.

## Notes

- Deleting a package removes all of its versions. You can restore it within 30 days, as long as the namespace is still free.
- GitHub won't delete public packages with more than 5,000 downloads through the API. Those rows will be reported as failures.
