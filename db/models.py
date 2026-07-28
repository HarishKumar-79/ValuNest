"""
RowProxy — Wraps Supabase dict results to behave like sqlite3.Row.

Ensures consistent row['column'] and row[0] access patterns
across both Supabase (dict) and SQLite (sqlite3.Row) backends.
"""


class RowProxy:
    """Wraps a dictionary to behave like an sqlite3.Row object.

    Supports:
        - row['column_name']  → dict-style key access
        - row[0]              → integer index access
        - dict(row)           → dict conversion
        - row.keys()          → column names
        - len(row)            → number of columns
        - 'col' in row        → membership test
        - iteration           → iterate over values
    """

    def __init__(self, data):
        if data is None:
            self._data = {}
            self._keys_list = []
        else:
            self._data = dict(data)
            self._keys_list = list(self._data.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._data[self._keys_list[key]]
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value
        if key not in self._keys_list:
            self._keys_list.append(key)

    def __contains__(self, key):
        return key in self._data

    def __iter__(self):
        return iter(self._data.values())

    def __len__(self):
        return len(self._data)

    def __repr__(self):
        return f"RowProxy({self._data})"

    def __bool__(self):
        return bool(self._data)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()

    def get(self, key, default=None):
        return self._data.get(key, default)
