"""Offline sun and moon arithmetic for an explicitly configured location.

Nothing here touches the network or infers where the machine is. The location
comes only from ``~/.config/oldbook/location.json``; without that file every
helper reports that no location is configured and the desktop stays quiet.

The solar equations follow the NOAA solar calculator (Meeus, Astronomical
Algorithms); the moon uses the low-precision ecliptic longitude series from the
Astronomical Almanac, which is accurate to a few tenths of a degree. That is
plenty for a reading card and a 3:1 rotation preference, and it keeps the
module dependency-free.
"""
import datetime as dt
import json
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LOCATION_FILE = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'oldbook/location.json'
SYNODIC_MONTH = 29.530588853
J2000 = 2451545.0
SUNRISE_ZENITH = 90.833   # apparent horizon including refraction
CIVIL_ZENITH = 96.0
# Nerd Font (Material Design) glyphs; JetBrainsMono Nerd Font carries them all.
SUNRISE_GLYPH = '\U000F059C'
SUNSET_GLYPH = '\U000F059B'
PHASE_NAMES = ('New moon', 'Waxing crescent', 'First quarter', 'Waxing gibbous',
               'Full moon', 'Waning gibbous', 'Last quarter', 'Waning crescent')
PHASE_GLYPHS = ('\U000F0F64', '\U000F0F67', '\U000F0F61', '\U000F0F68',
                '\U000F0F62', '\U000F0F66', '\U000F0F63', '\U000F0F65')
# Seen from the southern hemisphere the lit limb is mirrored, so waxing and
# waning trade glyphs while the names stay the same.
SOUTHERN_GLYPHS = ('\U000F0F64', '\U000F0F65', '\U000F0F63', '\U000F0F66',
                   '\U000F0F62', '\U000F0F68', '\U000F0F61', '\U000F0F67')


class Location:
    __slots__ = ('name', 'latitude', 'longitude', 'zone')

    def __init__(self, name, latitude, longitude, timezone):
        self.name = str(name)
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.zone = ZoneInfo(str(timezone))
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError('latitude must be within ±90 and longitude within ±180')

    @property
    def timezone(self):
        return self.zone.key


def load_location(path=None):
    """Return the configured Location, or None when there is no valid file."""
    path = Path(path) if path is not None else LOCATION_FILE
    try:
        if path.is_symlink() and not path.resolve().is_relative_to(Path.home()):
            return None
        document = json.loads(path.read_text())
        return Location(document.get('name', 'Here'), document['latitude'],
                        document['longitude'], document['timezone'])
    except (OSError, ValueError, KeyError, TypeError, ZoneInfoNotFoundError):
        return None


def julian_day(moment):
    """Julian day of an aware datetime."""
    utc = moment.astimezone(dt.timezone.utc)
    year, month, day = utc.year, utc.month, utc.day
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    number = day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    fraction = (utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3.6e9) / 24
    return number - 0.5 + fraction


def _solar_terms(julian):
    """Declination (deg), equation of time (min) and apparent longitude (deg)."""
    t = (julian - J2000) / 36525
    mean_longitude = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    mean_anomaly = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    anomaly = math.radians(mean_anomaly)
    centre = (math.sin(anomaly) * (1.914602 - t * (0.004817 + 0.000014 * t))
              + math.sin(2 * anomaly) * (0.019993 - 0.000101 * t)
              + math.sin(3 * anomaly) * 0.000289)
    true_longitude = mean_longitude + centre
    omega = math.radians(125.04 - 1934.136 * t)
    apparent = true_longitude - 0.00569 - 0.00478 * math.sin(omega)
    obliquity = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    obliquity += 0.00256 * math.cos(omega)
    obliquity_r = math.radians(obliquity)
    declination = math.degrees(math.asin(math.sin(obliquity_r) * math.sin(math.radians(apparent))))
    y = math.tan(obliquity_r / 2) ** 2
    l0 = math.radians(mean_longitude)
    equation = 4 * math.degrees(
        y * math.sin(2 * l0) - 2 * eccentricity * math.sin(anomaly)
        + 4 * eccentricity * y * math.sin(anomaly) * math.cos(2 * l0)
        - 0.5 * y * y * math.sin(4 * l0) - 1.25 * eccentricity ** 2 * math.sin(2 * anomaly))
    return declination, equation, apparent % 360


def _hour_angle(latitude, declination, zenith):
    """Half the daylight arc in degrees, or None when the sun never crosses."""
    lat, dec = math.radians(latitude), math.radians(declination)
    cosine = (math.cos(math.radians(zenith)) / (math.cos(lat) * math.cos(dec))
              - math.tan(lat) * math.tan(dec))
    if cosine < -1 or cosine > 1:
        return None
    return math.degrees(math.acos(cosine))


def solar_day(date, location):
    """Sunrise, solar noon, sunset and civil twilight for one local calendar date.

    Returns a dict of aware datetimes in the location's zone. Polar days and
    nights leave sunrise/sunset as None while noon is always present.
    """
    local_noon = dt.datetime.combine(date, dt.time(12), tzinfo=location.zone)
    utc_midnight = dt.datetime.combine(local_noon.astimezone(dt.timezone.utc).date(),
                                       dt.time(), tzinfo=dt.timezone.utc)
    declination, equation, _ = _solar_terms(julian_day(local_noon))
    noon = utc_midnight + dt.timedelta(minutes=720 - 4 * location.longitude - equation)
    # Anchor on the UTC day whose solar noon is nearest the local noon.
    while noon - local_noon > dt.timedelta(hours=12):
        noon -= dt.timedelta(days=1)
    while local_noon - noon > dt.timedelta(hours=12):
        noon += dt.timedelta(days=1)

    def crossing(zenith, sign):
        moment = noon
        for _ in range(2):  # refine with the terms at the event itself
            declination_now, equation_now, _ = _solar_terms(julian_day(moment))
            angle = _hour_angle(location.latitude, declination_now, zenith)
            if angle is None:
                return None
            anchor = noon + dt.timedelta(minutes=equation - equation_now)
            moment = anchor + sign * dt.timedelta(minutes=4 * angle)
        return moment.astimezone(location.zone)

    return {'date': date, 'noon': noon.astimezone(location.zone),
            'sunrise': crossing(SUNRISE_ZENITH, -1), 'sunset': crossing(SUNRISE_ZENITH, 1),
            'dawn': crossing(CIVIL_ZENITH, -1), 'dusk': crossing(CIVIL_ZENITH, 1)}


def is_night(moment, location):
    """True between sunset and the next sunrise at the location."""
    local = moment.astimezone(location.zone)
    today = solar_day(local.date(), location)
    if today['sunrise'] is None or today['sunset'] is None:
        declination, _, _ = _solar_terms(julian_day(local))
        # Polar: the sun stays up when it shares the hemisphere's summer sign.
        return (declination > 0) != (location.latitude > 0)
    return local < today['sunrise'] or local > today['sunset']


def moon_longitude(julian):
    """Geocentric ecliptic longitude of the moon in degrees (low precision)."""
    t = (julian - J2000) / 36525
    longitude = (218.32 + 481267.881 * t
                 + 6.29 * math.sin(math.radians(477198.87 * t + 135.0))
                 - 1.27 * math.sin(math.radians(413335.36 * t + 259.3))
                 + 0.66 * math.sin(math.radians(890534.22 * t + 235.7))
                 + 0.21 * math.sin(math.radians(954397.74 * t + 269.9))
                 - 0.19 * math.sin(math.radians(35999.05 * t + 357.5))
                 - 0.11 * math.sin(math.radians(966404.03 * t + 186.5)))
    return longitude % 360


def moon_phase(moment, latitude=0.0):
    """Elongation-based phase: age in days, lit fraction, name and glyph."""
    julian = julian_day(moment)
    _, _, sun = _solar_terms(julian)
    elongation = (moon_longitude(julian) - sun) % 360
    fraction = (1 - math.cos(math.radians(elongation))) / 2
    index = int(((elongation + 22.5) % 360) // 45)
    glyphs = SOUTHERN_GLYPHS if latitude < 0 else PHASE_GLYPHS
    return {'elongation': elongation, 'age_days': elongation / 360 * SYNODIC_MONTH,
            'illumination': fraction, 'phase': PHASE_NAMES[index], 'glyph': glyphs[index],
            'waxing': elongation < 180}


def next_phase_crossing(moment, target_elongation, step_hours=6):
    """First moment after ``moment`` when the elongation passes the target."""
    step = dt.timedelta(hours=step_hours)

    def offset(when):
        julian = julian_day(when)
        _, _, sun = _solar_terms(julian)
        return ((moon_longitude(julian) - sun - target_elongation + 180) % 360) - 180

    previous, current = moment, moment + step
    before = offset(previous)
    for _ in range(int(40 * 24 / step_hours)):
        after = offset(current)
        if before < 0 <= after:
            low, high = previous, current
            for _ in range(40):
                middle = low + (high - low) / 2
                if offset(middle) < 0:
                    low = middle
                else:
                    high = middle
            return low + (high - low) / 2
        previous, before, current = current, after, current + step
    raise ValueError('No phase crossing within forty days')


def status(moment, location):
    """Everything the desktop shows, with aware datetimes in the local zone."""
    local = moment.astimezone(location.zone)
    day = solar_day(local.date(), location)
    day_length = (day['sunset'] - day['sunrise']) if day['sunrise'] and day['sunset'] else None
    return {'location': location.name, 'timezone': location.timezone,
            'now': local, 'night': is_night(local, location), 'day_length': day_length,
            **day, 'moon': moon_phase(local, location.latitude)}


def clock(value):
    return value.strftime('%H:%M') if value is not None else '—'


def panel_line(report):
    """One quiet masthead line of Conky markup: sun times and the moon."""
    moon = report['moon']
    return (f"${{color1}}{SUNRISE_GLYPH}${{color}} {clock(report['sunrise'])}"
            f"  ${{color1}}{SUNSET_GLYPH}${{color}} {clock(report['sunset'])}"
            f"  ${{color1}}{moon['glyph']}${{color}} {moon['phase']}"
            f" ${{color2}}{round(moon['illumination'] * 100):d}%")


def serializable(report):
    def convert(value):
        if isinstance(value, dt.datetime):
            return value.isoformat(timespec='minutes')
        if isinstance(value, dt.date):
            return value.isoformat()
        if isinstance(value, dt.timedelta):
            return round(value.total_seconds())
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, float):
            return round(value, 4)
        return value
    return convert(report)
