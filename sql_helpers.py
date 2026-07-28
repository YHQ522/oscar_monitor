"""Safe SQL parameter helpers for isql-based execution.

Since SQL is written to a temp file and piped to isql (no driver-level
parameter binding), these functions provide rigorous escaping and validation
to prevent SQL injection.
"""
import re

# ── String escaping ─────────────────────────────────────────

def _sql_escape(s):
    """Escape a string for use as an SQL string literal ('' for ')."""
    if s is None:
        return ''
    return str(s).replace("'", "''")


def sql_str(val, max_len=1000):
    """Return a safely-escaped SQL string literal (wrapped in quotes)."""
    escaped = _sql_escape(val)[:max_len]
    return f"'{escaped}'"


def sql_str_null(val, max_len=1000):
    """Like sql_str but returns NULL for empty values."""
    if val is None or str(val).strip() == '':
        return 'NULL'
    return sql_str(val, max_len)


# ── Numeric validation ──────────────────────────────────────

def sql_int(val, default=0):
    """Return a validated integer for SQL, or default if invalid."""
    try:
        return str(int(val))
    except (ValueError, TypeError):
        return str(default)


def sql_num(val, default=0.0):
    """Return a validated number for SQL, or default if invalid."""
    try:
        return str(float(val))
    except (ValueError, TypeError):
        return str(default)


def sql_bool(val):
    """Return SQL boolean literal."""
    return 'TRUE' if val else 'FALSE'


# ── Identifier validation ───────────────────────────────────

_IDENT_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def sql_ident(name, allowed=None):
    """Validate and return a safe SQL identifier. Raises ValueError if invalid.
    If `allowed` is a set/tuple, checks that name is in the whitelist."""
    if allowed is not None:
        if name not in allowed:
            raise ValueError(f"SQL identifier not in allowed set: {name}")
        return name
    if not _IDENT_RE.match(str(name)):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return str(name)


# ── Composite helpers ───────────────────────────────────────

def safe_concat(*sql_parts):
    """Join already-safe SQL fragments."""
    return ''.join(str(p) for p in sql_parts)


def sql_values(*values):
    """Build a VALUES clause from pre-escaped values.
    Each value should already be escaped via sql_str/sql_int/etc."""
    return '(' + ', '.join(str(v) for v in values) + ')'


# ── Table names whitelist (central registration) ────────────

_VALID_TABLES = {'OSCAR_LOG_COLLECT', 'OSCAR_SERVERS', 'OSCAR_USERS'}


def table(name):
    """Return a validated table name for SQL."""
    return sql_ident(name, _VALID_TABLES)
