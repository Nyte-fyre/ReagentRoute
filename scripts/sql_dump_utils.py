"""Shared utilities for parsing mangos-family (classic-db / tbc-db) MySQL
dump files without a database server: extract one table's INSERT VALUES
blob and split it into row tuples, respecting quoted strings.
"""
import re


def extract_table_sql(full_text, table_name):
    marker = f"-- Table structure for table `{table_name}`"
    start = full_text.index(marker)
    next_marker = full_text.find("-- Table structure for table `", start + len(marker))
    section = full_text[start:next_marker if next_marker != -1 else len(full_text)]
    insert_match = re.search(
        r"INSERT INTO `%s` VALUES\s*(.*?);\s*(?:UNLOCK TABLES|/\*!40000)" % re.escape(table_name),
        section, re.DOTALL,
    )
    if not insert_match:
        raise ValueError(f"No INSERT found for {table_name}")
    return insert_match.group(1)


def parse_tuples(values_blob):
    """Split a VALUES (...),(...),... blob into lists of raw field strings."""
    tuples = []
    i, n = 0, len(values_blob)
    while i < n:
        if values_blob[i] == "(":
            depth, j, fields, field_start, in_quote = 1, i + 1, [], i + 1, False
            while j < n and depth > 0:
                c = values_blob[j]
                if in_quote:
                    if c == "\\":
                        j += 1  # skip escaped char
                    elif c == "'":
                        in_quote = False
                else:
                    if c == "'":
                        in_quote = True
                    elif c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                        if depth == 0:
                            fields.append(values_blob[field_start:j])
                            break
                    elif c == "," and depth == 1:
                        fields.append(values_blob[field_start:j])
                        field_start = j + 1
                j += 1
            tuples.append([f.strip() for f in fields])
            i = j + 1
        else:
            i += 1
    return tuples


def unquote(field):
    field = field.strip()
    if field == "NULL":
        return None
    if field.startswith("'") and field.endswith("'"):
        return field[1:-1].replace("\\'", "'").replace("''", "'")
    return field


def to_int(field):
    v = unquote(field)
    return 0 if v is None else int(v)
