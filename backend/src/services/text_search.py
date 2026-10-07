from sqlalchemy import ColumnElement, or_
from sqlalchemy.orm import InstrumentedAttribute


def contains(
    query: str, *columns: InstrumentedAttribute[str] | InstrumentedAttribute[str | None]
) -> list[ColumnElement[bool]]:
    """Filters for rows where any of `columns` holds `query`, case-insensitive
    and literally: % and _ typed by the user are not wildcards. An empty
    query filters nothing; a NULL column matches nothing."""
    term = query.strip()
    if not term:
        return []
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return [or_(*(column.ilike(pattern, escape="\\") for column in columns))]
