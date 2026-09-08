"""Persistent local review decisions; never edits a remote YouTube playlist."""


class Queue:
    def __init__(self, data=None):
        self.data = {'entries': [], 'index': 0, 'position': 0, 'paused': False,
                     'awaiting': False, 'mode': 'desktop', 'enabled': False}
        self.data.update(data or {})

    def current(self):
        index = self.data['index']
        entries = self.data['entries']
        return entries[index] if 0 <= index < len(entries) else None

    def end(self):
        self.data.update(awaiting=True, paused=True)

    def decide(self, decision):
        if decision not in ('rewatch', 'keep', 'remove'):
            raise ValueError('unknown review decision')
        current = self.current()
        if current is None:
            return
        if decision != 'rewatch':
            current['decision'] = decision
            self.data['index'] += 1
        self.data.update(position=0, paused=False, awaiting=False)


def output_for_mode(mode, workspaces):
    if mode == 'pip':
        return 'pip'
    return next((ws['output'] for ws in workspaces
                 if ws.get('num') == 1 and ws.get('visible')), None)
