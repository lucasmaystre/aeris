# aeris

A command-line tool for jotting down notes, backed by a PostgreSQL database.

## Installation

```bash
pip install aeris
```

## Configuration

Create `~/.aeris.yaml`:

```yaml
database_url: "postgresql+psycopg://user:password@localhost/aeris"
```

Then initialize the database:

```bash
aeris reset-db
```

## Usage

```bash
aeris add                        # open $EDITOR to write a note
aeris list                       # list recent notes
aeris list --last "2 hours"      # notes from the last 2 hours
aeris display [id]               # display note(s) in full
aeris delete <id>                # delete a note
```
