"""Pure full-text search of the provider's bounded contextual snapshot.

Whitespace-separated tokens use Unicode casefolded substring AND matching.
Results retain source order and split alternative shortcuts into independent
choices, so selecting a result always identifies exactly one native action.
"""


def _text(value):
    return value if isinstance(value, str) else ''


def search_shortcuts(snapshot, query=''):
    """Return matching choices with source metadata, without altering snapshot."""
    if not isinstance(snapshot, dict) or not isinstance(query, str):
        return []
    sections = snapshot.get('sections')
    if not isinstance(sections, list):
        return []
    tokens = query.casefold().split()
    app = _text(snapshot.get('app'))
    results = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict) or not isinstance(section.get('rows'), list):
            continue
        title = _text(section.get('title'))
        coverage = _text(section.get('coverage'))
        for row_index, row in enumerate(section['rows']):
            if not isinstance(row, dict):
                continue
            source_key = _text(row.get('key'))
            description = _text(row.get('description'))
            actions = row.get('actions')
            actions = ([action for action in actions if isinstance(action, dict)]
                       if isinstance(actions, list) else [])
            for action in actions or [None]:
                key = _text(action.get('label')) if action else source_key
                searchable = ' '.join((app, title, coverage, key, description)).casefold()
                if any(token not in searchable for token in tokens):
                    continue
                results.append({
                    'section': title,
                    'coverage': coverage,
                    'app': app,
                    'key': key,
                    'source_key': source_key,
                    'description': description,
                    'action': action,
                    'unavailable_reason': (_text(row.get('unavailable_reason')) if action is None else ''),
                    'section_index': section_index,
                    'row_index': row_index,
                })
    return results
