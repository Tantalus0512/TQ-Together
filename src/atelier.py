# -*- coding: utf-8 -*-
"""TQTogether.exe --atelier (Atelier.bat), 1.9.0: a new look for an item - it keeps its stats, affixes, relics, set
and weapon damage (transmog.py builds the clone records).

The choice is made in TQVault, with items the player already has: a vault named "Ателье" (or "Atelier").
  bags 1-11: the item on the LEFT gets the look of the item on its RIGHT (the sample stays as it is);
  the last bag: items there get their own look back.
Items of the same kind only (sword - sword, helmet - helmet). The icon changes too when both take the same cells
in the inventory, otherwise the item keeps its own icon (its size in the bags must not change).

Order of work (TQVault must stay closed, it would write its own copy of the vault over ours):
  1. read the vault, show the plan, ask;
  2. new clones go into the registry, TQ Together rebuilds and installs the database (the self-check included);
  3. only when the installed database holds every clone: a read-only backup of the vault, then baseName of each
     item is replaced in the vault file - nothing else in it changes;
  4. the player opens TQVault and takes the item to a hero."""
import os, re, json, time, stat, subprocess

import paths
import transmog as T

BS = chr(92)
VAULT_NAMES = ('Ателье', 'Atelier')
TQVAULT_EXE = ('TQVaultAE.exe', 'TQVault.exe')
BASENAME = re.compile(r'("baseName"\s*:\s*")((?:[^"\\]|\\.)*)(")')


def vault_dir():
    v = (paths.settings().get('vaultpath') or '').strip()
    if v and os.path.isdir(v):
        return v
    mg = os.path.dirname(paths.tq_user_dir())
    for d in (os.path.join(mg, 'Titan Quest', 'TQVaultData'), os.path.join(mg, 'TQVaultData')):
        if os.path.isdir(d):
            return d
    return os.path.join(mg, 'Titan Quest', 'TQVaultData')


def find_vault(folder=None):
    folder = folder or vault_dir()
    if os.path.isdir(folder):
        files = {f.lower(): f for f in os.listdir(folder)}
        for n in VAULT_NAMES:
            f = files.get((n + '.vault.json').lower())
            if f:
                return os.path.join(folder, f)
    return None


class AtelierError(Exception):
    pass


def tqvault_running():
    """True / False, None when it cannot be told (1.9.1: tasklist read as bytes - as text a localized Windows line
    raised UnicodeDecodeError and TQVault counted as closed)"""
    try:
        out = subprocess.run(['tasklist'], capture_output=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        if not out:
            return None
        out = out.lower()
        return any(x.lower().encode('ascii') in out for x in TQVAULT_EXE)
    except Exception:
        return None


def tqvault_closed(log, pause):
    """-> True once TQVault is closed (or, when that cannot be checked, the player says so); False = given up"""
    while True:
        st = tqvault_running()
        if st is False:
            return True
        if st is None:
            log('Could not check whether TQVault is running - make sure it is closed (it would write its own copy over '
                'the vault). / Не удалось проверить, закрыт ли TQVault - убедитесь, что он закрыт.')
            a = ask('Enter = TQVault is closed, N = cancel / Enter - TQVault закрыт, N - отмена: ')
            return a is not None and not a.startswith(('n', 'н'))
        log('TQVault is running - close it first (it would write its own copy over the vault). / TQVault открыт - '
            'закройте его.')
        if not pause('Press Enter when TQVault is closed / Нажмите Enter, когда TQVault закрыт'):
            return False


def game_language():
    """'ru' when the game runs in Russian (Settings\\options.txt), else 'en' - for item names"""
    try:
        with open(os.path.join(paths.tq_user_dir(), 'Settings', 'options.txt'), encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.strip().lower().startswith('language'):
                    return 'ru' if 'russian' in line.lower() else 'en'
    except OSError:
        pass
    return 'en'


def game_names(game, lang):
    """tag -> text from the INSTALLED Text_XX.arc (the game's texts and ours)"""
    out = {}
    p = os.path.join(game, 'Text', 'Text_%s.arc' % lang.upper())
    try:
        arc = T.Arc(p)
    except (OSError, ValueError):
        return out
    for name in arc.entries:
        if not name.endswith('.txt'):
            continue
        raw = arc.read(name) or b''
        txt = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8', 'replace')
        for line in txt.splitlines():
            if '=' in line and not line.startswith('/'):
                k, v = line.split('=', 1)
                out.setdefault(k.strip(), v.strip())
    return out


def label(rec, texts):
    """the in-game name of a record ('[ms]x[fs]y' gendered texts -> the masculine form), else its file name"""
    t = texts.get(T.value(rec, 'itemNameTag')) or texts.get(T.value(rec, 'description')) if rec else ''
    if t:
        forms = dict(re.findall(r'\[(\w\w)\]([^\[]*)', t))
        t = (forms.get('ms') or next(iter(forms.values()), '') or t).strip() if forms else t
        return re.sub(r'\{\^.\}|\^.', '', t).strip()
    return rec['name'].split(BS)[-1] if rec else '?'


def read_vault(path):
    """-> (text, data, [(bag index, item dict)] in file order)"""
    with open(path, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8-sig')
    data = json.loads(text)
    items = [(i, it) for i, sack in enumerate(data.get('sacks') or []) for it in (sack.get('items') or [])]
    return raw, text, data, items


def resolve(base, reg):
    """item's baseName -> (its own record, the record it looks like)"""
    k = T.key(base)
    e = reg['clones'].get(k) or {}
    item = T.key(e.get('item'))
    if item:
        return item, T.key(e.get('look')) or item
    return k, k


BAGS = 12          # a TQVault vault: "the last bag" is bag 12


def plan(items, R, reg, res, texts, bags, installed=None):
    """-> (orders, notes). An order: {'bag', 'index' (item number in the file), 'item', 'from', 'to', 'clone', 'icon',
    'text'}; notes: what is in the vault but cannot be done, said why. 1.9.1: a vault of fewer bags than TQVault's
    12 is refused; a clone of ours the registry does not know is recovered from the installed database (the clone
    record carries its recipe) - planned as it is it would become a clone of a clone; not recoverable = stop."""
    if bags < BAGS:
        raise AtelierError('The vault has %d bags, a TQVault vault has %d - nothing done. / В хранилище %d сумок '
                           'вместо %d - ничего не сделано.' % (bags, BAGS, bags, BAGS))
    unknown = sorted({T.key(it.get('baseName')) for _, it in items
                      if T.key(it.get('baseName')).startswith(T.NS) and T.key(it.get('baseName')) not in reg['clones']})
    if unknown:
        got = T.recover(unknown, installed) if installed else {}
        if got:
            reg['clones'].update(got)
            T.save(reg)
        lost = [k for k in unknown if k not in got]
        if lost:
            raise AtelierError('The vault holds item(s) with a look the atelier registry does not know and the installed '
                               'database cannot tell (%s) - nothing done. Restore transmog.json from a backup. / В '
                               'хранилище вещи с неизвестным реестру обликом - ничего не сделано. Верните transmog.json '
                               'из копии.' % ', '.join(k.split(BS)[-1] for k in lost))
    orders, notes = [], []
    by_bag = {}
    for n, (bag, it) in enumerate(items):
        own, look = resolve(it.get('baseName'), reg)
        rec = T._read(R, own)
        if rec is None or T.value(rec, 'Class') not in T.CLASSES:
            continue
        by_bag.setdefault(bag, []).append((n, it, own, look, rec))
    for bag in sorted(by_bag):
        eq = by_bag[bag]
        name = lambda r: '«%s»' % label(r, texts)
        if bag == bags - 1:                                        # the last bag: own look back
            for n, it, own, look, rec in eq:
                if look != own or T.key(it.get('baseName')) != own:
                    orders.append({'bag': bag + 1, 'index': n, 'item': own, 'from': it.get('baseName'), 'to': own,
                                   'clone': None, 'icon': False,
                                   'text': '%s -> own look / родной облик' % name(rec)})
            continue
        if len(eq) == 1:
            notes.append('bag %d: %s alone - put the sample to its RIGHT / сумка %d: %s одна - положите образец справа'
                         % (bag + 1, name(eq[0][4]), bag + 1, name(eq[0][4])))
            continue
        if len(eq) != 2:
            notes.append('bag %d: %d items - want two: the item on the left, the sample on the right / сумка %d: %d вещей '
                         '- нужно две: слева вещь, справа образец' % (bag + 1, len(eq), bag + 1, len(eq)))
            continue
        eq.sort(key=lambda x: (int(x[1].get('pointX', 0)), int(x[1].get('pointY', 0))))
        (n, it, own, cur, rec), (_, s_it, s_own, s_look, s_rec) = eq
        look_rec = T._read(R, s_look)
        if T.value(rec, 'Class') != T.value(s_rec, 'Class') or look_rec is None:
            notes.append('bag %d: %s and %s are not of one kind - a look comes from the same kind of item / сумка %d: '
                         'разные виды вещей, облик берётся у вещи того же вида' % (bag + 1, name(rec), name(s_rec), bag + 1))
            continue
        if s_look == own:
            target, ck, icon = own, None, False
        else:
            ck = T.clone_key(own, s_look)
            known = reg['clones'].get(ck)
            icon = bool(known.get('icon')) if known else T.icon_fits(res, rec, look_rec)
            target = ck
        if T.key(it.get('baseName')) == target:
            notes.append('bag %d: %s already has this look / сумка %d: у вещи уже этот облик' % (bag + 1, name(rec), bag + 1))
            continue
        orders.append({'bag': bag + 1, 'index': n, 'item': own, 'look': s_look, 'from': it.get('baseName'), 'to': target,
                       'clone': ck, 'icon': icon,
                       'text': '%s -> look of / облик %s%s' % (
                           name(rec), name(look_rec) if s_look != own else '(own / родной)',
                           '' if ck is None else (', icon too / иконка тоже' if icon else
                                                  ', own icon: other size / иконка своя: другой размер'))})
    return orders, notes


def rewrite(text, changes):
    """text with baseName of item number n (file order) replaced: {n: (old, new)}; nothing else moves"""
    out, pos, seen = [], 0, 0
    for n, m in enumerate(BASENAME.finditer(text)):
        seen += 1
        if n in changes:
            old, new = changes[n]
            if json.loads('"%s"' % m.group(2)) != old:
                raise ValueError('item %d of the vault is %s, not %s' % (n, json.loads('"%s"' % m.group(2)), old))
            out.append(text[pos:m.start(2)])
            out.append(json.dumps(new, ensure_ascii=False)[1:-1])
            pos = m.end(2)
    out.append(text[pos:])
    return ''.join(out), seen


def backup(path):
    d = os.path.join(paths.data_dir(), 'atelier', 'backup')
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, '%s %s' % (time.strftime('%Y%m%d_%H%M%S'), os.path.basename(path)))
    with open(path, 'rb') as f, open(dst, 'wb') as g:
        g.write(f.read())
    os.chmod(dst, stat.S_IREAD)
    return dst


def write_vault(path, raw, items, orders):
    """the vault with the orders' baseNames; checked by reading it back. -> backup path"""
    text = raw.decode('utf-8-sig')
    bom = raw[:3] == b'\xef\xbb\xbf'
    new, seen = rewrite(text, {o['index']: (o['from'], o['to']) for o in orders})
    if seen != len(items):
        raise ValueError('the vault has %d baseName entries for %d items' % (seen, len(items)))
    data = json.loads(new)
    got = [it for sack in data.get('sacks') or [] for it in (sack.get('items') or [])]
    want = {o['index']: o['to'] for o in orders}
    for n, ((bag, it), it2) in enumerate(zip(items, got)):
        exp = dict(it, baseName=want[n]) if n in want else it
        if exp != it2:
            raise ValueError('item %d would change beyond its baseName' % n)
    b = backup(path)
    # 1.9.1: flushed to disk before the swap, read back after it; a mismatch puts the vault's previous content back
    T.write_checked(path, (b'\xef\xbb\xbf' if bom else b'') + new.encode('utf-8'))
    return b


def note(line):
    try:
        d = os.path.join(paths.data_dir(), 'atelier')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'atelier.log'), 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), line))
    except OSError:
        pass


def ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return None


STEAM_NOTE = ('If Steam verified or updated the game files, start the game only through TQ Together, otherwise items '
              'with a new look disappear. / Если Steam проверил или обновил файлы игры, запускайте игру только через '
              'TQ Together, иначе вещи с новым обликом пропадут.')


def run(game, inst, build, log=print, pause=lambda *a: True):
    """build(): rebuild + install with the registry as it is now -> True when installed. 1.9.1: no traceback - any
    error says whether the vault was changed (it is written last, in one checked step)"""
    state = {'written': False}
    try:
        return _run(game, inst, build, log, pause, state)
    except AtelierError as e:
        log(str(e))
        return False
    except Exception as e:
        import traceback
        note('ERROR %s' % traceback.format_exc().replace('\n', ' | '))
        if state['written']:
            log('Atelier stopped after writing the vault (%s) - see atelier.log in the data folder. / Ателье '
                'остановилось после записи хранилища (%s) - см. atelier.log.' % (e, e))
        else:
            log('Atelier stopped (%s). The vault was not changed - run Atelier.bat again. / Ателье остановилось (%s). '
                'Хранилище не изменено, запустите Atelier.bat ещё раз.' % (e, e))
        return False


def _run(game, inst, build, log, pause, state):
    from arz_lazy import LazyArz
    import installer
    path = find_vault()
    log('\nAtelier / Ателье')
    if not path:
        log('No vault named "Ателье" (or "Atelier") in %s.' % vault_dir())
        log('Create one in TQVault (the vault list - New vault), put the item on the left and the sample to its right in '
            'one bag, close TQVault and run Atelier.bat again.')
        log('В TQVault нет хранилища «Ателье». Создайте его (список хранилищ - новое), положите в одну сумку вещь слева '
            'и образец справа, закройте TQVault и снова запустите Atelier.bat.')
        return False
    if not tqvault_closed(log, pause):
        return False
    installed = os.path.join(game, 'Database', 'database.arz')
    reg = T.load()
    R = LazyArz.load(installed).records
    res = T.Resources(game)
    texts = game_names(game, game_language())
    raw, text, data, items = read_vault(path)
    orders, notes = plan(items, R, reg, res, texts, len(data.get('sacks') or []), installed=installed)
    log('Vault / Хранилище: %s' % path)
    for n in notes:
        log('  ' + n)
    if not orders:
        log('Nothing to do. Bags 1-11: the item on the LEFT takes the look of the item on its RIGHT; the last bag: '
            'own look back.')
        log('Делать нечего. Сумки 1-11: вещь СЛЕВА получает облик вещи справа от неё; последняя сумка - родной облик.')
        return False
    for o in orders:
        log('  bag / сумка %d: %s' % (o['bag'], o['text']))
    a = ask('Apply? Enter = yes, N = no / Применить? Enter - да, N - нет: ')
    if a is None or a.startswith(('n', 'н')):
        log('Cancelled. / Отменено.')
        return False
    new = [o for o in orders if o['clone'] and o['clone'] not in reg['clones']]
    for o in new:
        reg['clones'][o['clone']] = {'item': o['item'], 'look': o['look'], 'icon': o['icon'],
                                     'made': time.strftime('%Y-%m-%d'), 'note': o['text']}
    if new:                                   # 1.9.1: always, also when the installed database has them already
        T.save(reg)
    need = {o['clone'] for o in orders if o['clone']}
    if any(c not in R for c in need):
        log('Rebuilding the database with the new looks ... / Пересобираю базу с новыми обликами ...')
        ok = False
        try:
            ok = build()
        except SystemExit as e:               # the self-check stopped the install
            log(str(e))
        finally:
            if not ok and new:                # nothing refers to them yet; what the build recovered stays
                cur = T.load()
                for o in new:
                    cur['clones'].pop(o['clone'], None)
                T.save(cur)
        if not ok:
            log('The build did not install - the vault was not changed. / Сборка не установилась, хранилище не '
                'изменено.')
            return False
        R = LazyArz.load(installed).records
    lost = sorted(c for c in need if c not in R)
    if lost:
        log('The installed database lacks %s - the vault was not changed. / В базе игры нет клонов, хранилище не '
            'изменено.' % ', '.join(x.split(BS)[-1] for x in lost))
        return False
    if not tqvault_closed(log, pause):
        return False
    raw2 = open(path, 'rb').read()
    if raw2 != raw:                                           # TQVault saved meanwhile: plan again from scratch
        log('The vault changed meanwhile - run Atelier.bat again. / Хранилище изменилось, запустите Atelier.bat снова.')
        return False
    try:
        installer.backup_saves(log, 'atelier')            # 1.9.1: the heroes and the stash first
    except SystemExit as e:
        log(str(e))
        log('The vault was not changed. / Хранилище не изменено.')
        return False
    b = write_vault(path, raw, items, orders)
    state['written'] = True
    for o in orders:
        note('%s | bag %d | %s | %s -> %s' % (os.path.basename(path), o['bag'], o['text'], o['from'], o['to']))
    log('Done: %d item(s). Backup of the vault / копия хранилища: %s' % (len(orders), b))
    log('Open TQVault and take the item to your hero. / Откройте TQVault и заберите вещь герою.')
    log(STEAM_NOTE)
    return True
