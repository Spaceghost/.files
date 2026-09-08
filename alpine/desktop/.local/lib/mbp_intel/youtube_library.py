"""On-demand YouTube library browsing using a selected browser session."""
import configparser
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ACCOUNT = Path.home() / '.config/mbp-intel/youtube-account.json'
FEEDS = {'history': 'https://www.youtube.com/feed/history',
         'watchlist': 'https://www.youtube.com/playlist?list=WL',
         'playlists': 'https://www.youtube.com/feed/playlists'}
PAGE_SIZE = 50


def youtube_url(source):
    url = urlsplit(source)
    return (url.scheme == 'https' and not url.username and not url.password
            and url.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com',
                                 'music.youtube.com', 'youtu.be') and url.port in (None, 443))


def browser_reference(value):
    if (not isinstance(value, str) or not re.match(r'^(firefox|chromium|chrome|brave)(:|$)', value)
            or any(c in value for c in ',\n\r\x00') or len(value) > 1000):
        raise ValueError('Choose a supported browser profile')
    return value


def read_account():
    try:
        value = json.loads(ACCOUNT.read_text()).get('browser')
    except FileNotFoundError:
        return None
    return browser_reference(value) if value else None


def save_account(browser):
    browser = browser_reference(browser) if browser else None
    ACCOUNT.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = ACCOUNT.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump({'browser': browser}, output)
        output.write('\n')
    temporary.replace(ACCOUNT)


def firefox_profiles():
    found = {}
    for root in (Path.home() / '.config/mozilla/firefox', Path.home() / '.mozilla/firefox'):
        ini = configparser.ConfigParser(interpolation=None)
        ini.read(root / 'profiles.ini')
        for section in ini.sections():
            if not section.startswith('Profile') or not ini.has_option(section, 'Path'):
                continue
            path = Path(ini[section]['Path'])
            if ini[section].get('IsRelative') == '1':
                path = root / path
            if (path / 'cookies.sqlite').is_file():
                found['Firefox · ' + ini[section].get('Name', path.name)] = 'firefox:' + str(path)
    return found


def playback_options(source):
    # Local test clips and non-YouTube media never receive browser authentication.
    if not youtube_url(source):
        return []
    browser = read_account()
    return ['ytdl-raw-options=cookies-from-browser=' + browser] if browser else []


def fetch(source, *, private=False, page=1, limit=PAGE_SIZE):
    is_search = re.match(r'^ytsearch\d+:', source) is not None
    if not is_search and not youtube_url(source):
        raise ValueError('Enter a YouTube HTTPS URL')
    browser = read_account()
    if private and not browser:
        raise RuntimeError('Choose your account in YouTube → Account / sign in first')
    first = (max(1, page) - 1) * limit + 1
    if is_search:
        source = re.sub(r'^ytsearch\d+:', f'ytsearch{first + limit}:', source)
    command = ['yt-dlp', '--ignore-config', '--flat-playlist', '--dump-single-json',
               '--playlist-items', f'{first}:{first + limit}', '--socket-timeout', '15',
               '--retries', '1', '--extractor-retries', '1']
    if browser and not is_search:
        command += ['--cookies-from-browser', browser]
    result = subprocess.run(command + ['--', source], text=True, capture_output=True, timeout=120)
    if result.returncode:
        # Never relay extractor diagnostics containing account data to notifications/logs.
        if any(text in result.stderr.lower() for text in ('sign in', 'log in', 'private playlist', 'login')):
            raise RuntimeError('Sign in to YouTube in the selected browser, then retry from the launcher')
        if any(text in result.stderr.lower() for text in ('name resolution', 'errno -3', 'network is unreachable', 'timed out')):
            raise RuntimeError('YouTube is unreachable. Check the network/DNS connection, then retry.')
        raise RuntimeError('YouTube could not load this list. Retry, or open it in your browser from Account / sign in.')
    data = json.loads(result.stdout)
    raw = (data.get('entries') or []) if 'entries' in data else [data]
    entries = []
    for entry in raw[:limit]:
        if not isinstance(entry, dict):
            continue
        address = entry.get('webpage_url') or entry.get('url')
        if not isinstance(address, str) or not youtube_url(address):
            continue
        parsed = urlsplit(address)
        kind = 'playlist' if parsed.path == '/playlist' else 'video'
        if kind == 'video' and not (parsed.hostname == 'youtu.be' or parsed.path == '/watch' or parsed.path.startswith(('/shorts/', '/live/'))):
            continue
        entries.append({'url': address, 'title': ' '.join(str(entry.get('title') or 'Untitled').split()),
                        'channel': ' '.join(str(entry.get('channel') or entry.get('uploader') or '').split()),
                        'kind': kind})
    return {'entries': entries, 'more': len(raw) > limit}
