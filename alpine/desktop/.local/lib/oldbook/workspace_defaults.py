"""One-time placement of designated instances and independent artwork choices.

Only Fossil keeps a default: it mirrors the static
`assign [app_id="^oldbook-strata$"] workspace number "10: Strata"` rule
already in sway config, so this dict and that rule agree. Every other name
that used to appear here silently relocated a window on first sight.
"""
DEFAULTS = {'Fossil': 10}


class Placement:
    def __init__(self, saved=None):
        saved = saved or {}
        self.seen = set(saved.get('seen', []))
        self.claims = saved.get('claims', {})

    def plan(self, windows, adopt=False, stay=()):
        live = {identifier for identifier, _ in windows}
        self.seen &= live
        self.claims = {name: identifier for name, identifier in self.claims.items()
                       if identifier in live}
        moves = []
        for identifier, name in windows:
            if identifier in stay:
                self.seen.add(identifier)
                continue
            if identifier in self.seen or name not in DEFAULTS:
                continue
            self.seen.add(identifier)
            if name not in self.claims:
                self.claims[name] = identifier
                if not adopt:
                    moves.append((identifier, DEFAULTS[name]))
        return moves

    def state(self):
        return {'seen': sorted(self.seen), 'claims': self.claims}


def choose_artwork(identifiers, current, direction, occupied):
    index = identifiers.index(current) if current in identifiers else (-1 if direction > 0 else 0)
    for step in range(1, len(identifiers) + 1):
        candidate = identifiers[(index + step * direction) % len(identifiers)]
        if candidate not in occupied:
            return candidate
    return identifiers[(index + direction) % len(identifiers)]
