# -*- coding: utf-8 -*-
"""Where things are on THIS computer: the game (Steam or GOG or anything else), the saves, our data folder.
Works the same from the scripts and from the packed TQTogether.exe."""
import os, sys, re, glob

APP = 'TQ Together'
VERSION = '1.0.1'
STEAM_APPID = '475150'
BASE_SUFFIX = '.tqtogether-base'     # untouched copy of every game file we replace


def frozen():
    return getattr(sys, 'frozen', False)


def app_dir():
    return os.path.dirname(sys.executable) if frozen() else os.path.dirname(os.path.abspath(__file__))


def documents():
    """the real Documents folder (also when Windows moved it to OneDrive)"""
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:   # CSIDL_PERSONAL
            return buf.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def tq_user_dir():
    return os.path.join(documents(), 'My Games', 'Titan Quest - Immortal Throne')


def saves_dir():
    return os.path.join(tq_user_dir(), 'SaveData', 'Main')


def data_dir():
    """registry of companions, install state, build cache, report - survives updates of the tool itself"""
    d = os.path.join(tq_user_dir(), 'TQ Together')
    os.makedirs(d, exist_ok=True)
    return d


def settings():
    """optional TQTogether.ini next to the exe:  GamePath=D:\\Games\\Titan Quest Anniversary Edition"""
    out = {}
    for p in (os.path.join(data_dir(), 'TQTogether.ini'), os.path.join(app_dir(), 'TQTogether.ini')):
        if os.path.exists(p):                   # the one next to the exe wins
            for line in open(p, encoding='utf-8-sig', errors='replace'):
                if '=' in line and not line.strip().startswith((';', '#')):
                    k, v = line.split('=', 1)
                    out[k.strip().lower()] = v.strip().strip('"')
    return out


def has_dlc(game):
    """Eternal Embers (electrum orbs; also the newest records we reference)"""
    r = os.path.join(game, 'Resources')
    return os.path.isdir(os.path.join(r, 'XPack4')) or os.path.isfile(os.path.join(r, 'XPack4.arc'))


def is_game(d):
    return bool(d) and os.path.isfile(os.path.join(d, 'TQ.exe')) and \
        os.path.isfile(os.path.join(d, 'Database', 'database.arz'))


def _reg(root, key, name):
    try:
        import winreg
        with winreg.OpenKey(root, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


def _steam_game():
    import winreg
    steam = _reg(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath') or \
        _reg(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')
    if not steam:
        return None
    libs = [steam]
    vdf = os.path.join(steam, 'steamapps', 'libraryfolders.vdf')
    if os.path.exists(vdf):
        libs += [p.replace('\\\\', '\\') for p in re.findall(r'"path"\s+"([^"]+)"', open(vdf, encoding='utf-8', errors='replace').read())]
    for lib in libs:
        acf = os.path.join(lib, 'steamapps', 'appmanifest_%s.acf' % STEAM_APPID)
        if os.path.exists(acf):
            m = re.search(r'"installdir"\s+"([^"]+)"', open(acf, encoding='utf-8', errors='replace').read())
            d = os.path.join(lib, 'steamapps', 'common', m.group(1) if m else 'Titan Quest Anniversary Edition')
            if is_game(d):
                return d
    return None


def _gog_game():
    try:
        import winreg
        base = r'SOFTWARE\WOW6432Node\GOG.com\Games'
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                name = _reg(winreg.HKEY_LOCAL_MACHINE, base + '\\' + sub, 'gameName') or ''
                path = _reg(winreg.HKEY_LOCAL_MACHINE, base + '\\' + sub, 'path') or ''
                if 'titan quest' in name.lower() and is_game(path):
                    return path
    except Exception:
        pass
    return None


def find_game():
    d = _find_game()
    return os.path.normpath(d) if d else None


def _find_game():
    """-> game folder or None. Order: TQTogether.ini, the exe's own folder / its parent, Steam, GOG, usual places"""
    s = settings().get('gamepath')
    if s:
        return s if is_game(s) else None
    here = app_dir()
    for d in (here, os.path.dirname(here)):
        if is_game(d):
            return d
    for f in (_steam_game, _gog_game):
        try:
            d = f()
        except Exception:
            d = None
        if d:
            return d
    for pat in (r'?:\Program Files*\Steam\steamapps\common\Titan Quest Anniversary Edition',
                r'?:\SteamLibrary\steamapps\common\Titan Quest Anniversary Edition',
                r'?:\Steam\steamapps\common\Titan Quest Anniversary Edition',
                r'?:\GOG Games\Titan Quest*', r'?:\Games\Titan Quest*', r'?:\Program Files*\GOG Galaxy\Games\Titan Quest*'):
        for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            for d in glob.glob(drive + pat[1:]):
                if is_game(d):
                    return d
    return None


def is_steam(game):
    return 'steamapps' in game.lower()
