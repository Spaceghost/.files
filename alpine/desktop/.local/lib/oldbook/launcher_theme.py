"""Derive Fuzzel roles from even the gallery's minimal three-color themes."""


def blend(color, target, amount):
    return '#' + ''.join(f'{round(int(color[i:i + 2], 16) * (1 - amount) + int(target[i:i + 2], 16) * amount):02x}'
                         for i in (1, 3, 5))


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(first, second):
    low, high = sorted((luminance(first), luminance(second)))
    return (high + .05) / (low + .05)


def readable(color, background, minimum=4.5):
    """Keep the hue when possible; move toward the readable endpoint if needed."""
    target = max(('#000000', '#ffffff'), key=lambda end: contrast(end, background))
    for step in range(101):
        candidate = blend(color, target, step / 100)
        if contrast(candidate, background) >= minimum:
            return candidate
    return target


def menu_colors(palette):
    background = palette['background']
    foreground = readable(palette['foreground'], background)
    accent = readable(palette['accent'], background)
    muted = readable(blend(background, foreground, .65), background)
    selection = readable(blend(background, accent, .20), background, 1.3)
    return {'background': background, 'text': foreground, 'input': foreground,
            'prompt': accent, 'placeholder': muted, 'message': muted, 'counter': muted,
            'match': accent, 'selection': selection,
            'selection-text': readable(foreground, selection),
            'selection-match': readable(accent, selection),
            'border': blend(background, accent, .5)}


def color_arguments(palette):
    # Opaque surfaces keep contrast independent of whichever wallpaper is behind them.
    return ['--' + role + '-color=' + color[1:] + 'ff'
            for role, color in menu_colors(palette).items()]
