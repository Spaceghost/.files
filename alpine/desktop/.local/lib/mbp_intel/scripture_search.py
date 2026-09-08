"""Bounded offline results for the desktop Scripture entry."""
import scripture


class SearchIndex:
    def __init__(self, bible, studies=(), scope='bible'):
        if scope not in ('bible', 'all', 'reflections'):
            raise ValueError('Unknown search scope: ' + scope)
        self.scope = scope
        verses = [record for record in bible.verses
                  if scope == 'all' or (scope == 'bible' and
                     not record['book'].startswith(('Torah ', 'Talmud ')))]
        self.bible = scripture.Bible(verses)
        bible_rows, torah_rows, talmud_rows = [], [], []
        for record in verses:
            row = self.passage([record])
            target = (torah_rows if record['book'].startswith('Torah ') else
                      talmud_rows if record['book'].startswith('Talmud ') else bible_rows)
            target.append(row)
        study_rows = []
        if scope != 'bible':
            for entry in studies:
                title = ' · '.join(part for part in (entry.get('figure'), entry['title']) if part)
                study_rows.append({'action': 'select-reflection', 'query': entry['id'],
                    'reference': entry['reference'], 'title': title,
                    'text': entry.get('reflection') or entry.get('text') or entry['reference']})
        self.rows = torah_rows + talmud_rows + study_rows + bible_rows
        self.searchable = [(' '.join((item['reference'], item['title'], item['text'])).casefold(), item)
                           for item in self.rows]

    @staticmethod
    def passage(records):
        reference = scripture.format_reference(records)
        return {'action': 'select', 'query': reference, 'reference': reference,
                'title': reference, 'text': scripture.passage_text(records)}

    def search(self, query, limit=6):
        if limit <= 0:
            return []
        query = query.strip()
        direct = self.bible.lookup(query) if query else []
        if direct and self.scope == 'bible':
            return [self.passage(direct)]
        words = query.casefold().split()
        matches = []
        for text, item in self.searchable:
            if all(word in text for word in words):
                matches.append(item)
                if len(matches) >= limit:
                    break
        if direct and len(matches) < limit:
            passage = self.passage(direct)
            if not any(item['action'] == 'select' and item['query'] == passage['query']
                       for item in matches):
                matches.append(passage)
        return matches
