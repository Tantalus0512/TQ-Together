# -*- coding: utf-8 -*-
"""Atelier (1.9.0): an item keeps everything it is - stats, affixes, relics, set, weapon damage - and takes the look
of another item of the same kind. Instead of carrying stats onto a pretty item in TQVault's God mode forge.

How: a look is a set of fields of the item's RECORD (mesh, textures, weapon trail, icon); an item in a save or a
vault is only baseName + affixes + relics + seed. So "this axe with that look" is a clone of the axe's record with
the look fields of the other one, under records\\tqmod\\transmog\\, and the item's baseName points at the clone
(atelier.py does that in a TQVault vault).

Clones are tombstones from birth: a clone record is never removed - an item whose record is gone vanishes from
the save. The registry (<data>\\transmog.json, a second copy in <data>\\atelier\\) only grows; the clone record
carries its own recipe in FileDescription, so a lost registry is recovered from the installed database. If items
still refer to clones nobody can rebuild, the build stops instead of installing a database that would eat them.

Built right after the tweaks (build_companions.Builder.run, hero_power.db): companions bake the gear their heroes
wear and hero_power measures it, so a worn clone must exist by then."""
import os, re, json, hashlib, struct, time, zlib

import paths

BS = chr(92)
NS = 'records' + BS + 'tqmod' + BS + 'transmog' + BS
REGISTRY = os.path.join(paths.data_dir(), 'transmog.json')
VERSION = 1
# the look: what the game draws in the hand, on the body and on the ground. Kept from the item itself: every stat,
# basicProjectileName (a staff's bolt goes with its damage), sounds, and the monster races' armour fields (armorSatyr...,
# armorJackalMan..., armorTigerman..., armorNative..., armorBandit...) - those dress monsters, not heroes.
LOOK = ('mesh', 'baseTexture', 'bumpTexture', 'dropMeshOverride', 'weaponTrail',
        'armorMaleMesh', 'armorFemaleMesh', 'armorMaleBaseTexture', 'armorMaleBumpTexture',
        'armorFemaleBaseTexture', 'armorFemaleBumpTexture')
ICON = ('bitmap', 'bitmapFemale')       # the inventory size IS the icon size: taken only when the cells match
CLASSES = ('ArmorProtective_Head', 'ArmorProtective_UpperBody', 'ArmorProtective_LowerBody', 'ArmorProtective_Forearm',
           'WeaponArmor_Shield', 'WeaponMelee_Sword', 'WeaponMelee_Axe', 'WeaponMelee_Mace', 'WeaponHunting_Spear',
           'WeaponHunting_Bow', 'WeaponHunting_RangedOneHand', 'WeaponMagical_Staff')
RECIPE = re.compile(r'^TQ Together atelier: item=(.+?) look=(.+?) icon=([01])$')
# our clones as items hold them: backslashes in saves, doubled in TQVault's JSON, maybe forward slashes
REF_PAT = re.compile(rb'records(?:\\\\|\\|/)+tqmod(?:\\\\|\\|/)+transmog(?:\\\\|\\|/)+(tm_[0-9a-f]{16})\.dbr', re.I)


class TransmogError(Exception):
    pass


def key(name):
    return (name or '').replace('/', BS).lower()


def clone_key(item, look):
    return NS + 'tm_' + hashlib.md5((key(item) + '|' + key(look)).encode('utf-8')).hexdigest()[:16] + '.dbr'


def backup_path(path=None):
    p = path or REGISTRY
    return os.path.join(os.path.dirname(p), 'atelier', os.path.basename(p))


def load(path=None):
    """-> {'version': 1, 'clones': {clone key: {'item', 'look', 'icon', 'made', 'note'}}}. An unreadable registry
    falls back to its second copy; both unreadable is an error, never "no clones" (that would eat the items)."""
    p = path or REGISTRY
    errors = []
    for f in (p, backup_path(p)):
        try:
            with open(f, encoding='utf-8') as h:
                d = json.load(h)
            if not isinstance(d, dict) or not isinstance(d.get('clones'), dict):
                raise ValueError('not an atelier registry')
            return {'version': VERSION, 'clones': {key(k): v for k, v in d['clones'].items()}}
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as e:
            errors.append('%s: %s' % (f, e))
    if errors:
        raise TransmogError('the atelier registry is unreadable (%s) - restore it from a backup. Items with a new look '
                            'need it. / Реестр ателье не читается - восстановите его из копии.' % '; '.join(errors))
    return {'version': VERSION, 'clones': {}}


def write_checked(f, data):
    """data (bytes) into f: written aside, flushed to disk, swapped in, read back (1.9.1); a mismatch puts the
    previous content back and raises OSError"""
    old = None
    if os.path.exists(f):
        with open(f, 'rb') as h:
            old = h.read()
    os.makedirs(os.path.dirname(f) or '.', exist_ok=True)
    for blob in (data,) if old is None else (data, old):
        with open(f + '.tmp', 'wb') as h:
            h.write(blob)
            h.flush()
            os.fsync(h.fileno())
        os.replace(f + '.tmp', f)
        with open(f, 'rb') as h:
            if h.read() == blob:
                if blob is data:
                    return
                break
    raise OSError('%s: the file read back differs from what was written - %s' % (
        f, 'the previous content is back' if old is not None else 'nothing was there before'))


def save(reg, path=None):
    p = path or REGISTRY
    data = json.dumps({'version': VERSION, 'clones': reg['clones']}, ensure_ascii=False, indent=1,
                      sort_keys=True).encode('utf-8')
    for f in (p, backup_path(p)):
        try:
            write_checked(f, data)
        except OSError as e:
            raise TransmogError('the atelier registry could not be saved (%s) / реестр ателье не записался' % e)


def fingerprint(path=None):
    p = path or REGISTRY
    try:
        with open(p, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return ''


def _read(R, k):
    """a record for reading (lazy database: not cached, so save() does not re-encode it)"""
    peek = getattr(R, 'peek', None)
    if peek is not None:
        return peek(k) if k in R else None
    return R.get(k)


def fields(rec):
    return {vn.lower(): (vn, vt, list(vals)) for vn, vt, vals in rec['vars']}


def value(rec, name):
    f = fields(rec).get(name.lower()) if rec else None
    return f[2][0] if f and f[2] else ''


def make(db, ck, item, look, icon, log=print):
    """the clone record: the item's record with the look's LOOK fields (and ICON fields if icon)"""
    R = db.arz.records
    src = _read(R, look) if look != item else None
    if look != item and src is None:
        log('  ! atelier: the look %s is gone from the game - %s keeps its own look' % (look, ck.split(BS)[-1]))
    c = db.clone(item, ck)
    names = LOOK + (ICON if icon else ())
    if src is not None:
        have = fields(src)
        want = {n.lower() for n in names}
        c['vars'] = [v for v in c['vars'] if v[0].lower() not in want]
        for n in names:
            if n.lower() in have:
                vn, vt, vals = have[n.lower()]
                c['vars'].append((vn, vt, list(vals)))
    c['vars'] = [v for v in c['vars'] if v[0].lower() != 'filedescription']
    c['vars'].append(('FileDescription', 2, ['TQ Together atelier: item=%s look=%s icon=%d' % (item, look, int(bool(icon)))]))
    db.mark(ck)
    return c


def referenced(roots=None):
    """{clone key: first file that refers to it}: saves, stashes, TQVault vaults, backups (build_companions.scan_roots)"""
    import build_companions as B
    out = {}
    for root in (B.scan_roots() if roots is None else roots):
        for dp, dn, fns in os.walk(root):
            for fn in fns:
                if not fn.lower().endswith(B.SCAN_EXT):
                    continue
                p = os.path.join(dp, fn)
                try:
                    with open(p, 'rb') as f:
                        data = f.read()
                except OSError:
                    continue
                for m in REF_PAT.finditer(data):
                    out.setdefault(NS + m.group(1).decode().lower() + '.dbr', p)
    return out


def recover(missing, installed_arz, log=print):
    """{clone key: entry} for the clones the registry lost, read back from their FileDescription in the installed
    database (the last TQ Together build)"""
    got = {}
    if not missing or not installed_arz or not os.path.isfile(installed_arz):
        return got
    from arz_lazy import LazyArz
    try:
        R = LazyArz.load(installed_arz).records
    except Exception as e:
        log('  ! atelier: cannot read %s (%s)' % (installed_arz, e))
        return got
    for ck in missing:
        if ck in R:
            m = RECIPE.match(value(R.peek(ck), 'FileDescription'))
            if m:
                got[ck] = {'item': m.group(1), 'look': m.group(2), 'icon': m.group(3) == '1',
                           'made': time.strftime('%Y-%m-%d'), 'note': 'recovered from the installed database'}
    return got


def apply(db, log=print, path=None, installed_arz=None, roots=None):
    """build every clone of the registry into db (right after the tweaks) -> set of clone keys made.
    installed_arz (the build only): where lost registry entries are recovered from; items that refer to clones
    nobody can rebuild stop the build."""
    reg = load(path)
    if installed_arz is not None:
        refs = referenced(roots)
        missing = sorted(set(refs) - set(reg['clones']))
        if missing:
            got = recover(missing, installed_arz, log)
            if got:
                reg['clones'].update(got)
                save(reg, path)
                log('  atelier: %d clone(s) recovered into the registry from the installed database' % len(got))
            lost = [ck for ck in missing if ck not in got]
            if lost:
                raise TransmogError('items with a new look refer to %d record(s) TQ Together cannot rebuild (the atelier '
                                    'registry was lost): %s, e.g. in %s. Nothing was installed - restore transmog.json '
                                    'from a backup. / Вещи с новым обликом ссылаются на записи, которые не восстановить '
                                    '(потерян реестр ателье). Ничего не установлено - верните transmog.json из копии.'
                                    % (len(lost), ', '.join(ck.split(BS)[-1] for ck in lost[:5]), refs[lost[0]]))
    R = db.arz.records
    made = set()
    for ck, e in sorted(reg['clones'].items()):
        item, look = key(e.get('item')), key(e.get('look'))
        if not ck.startswith(NS) or not item:
            log('  ! atelier: bad registry entry %s - skipped' % ck)
            continue
        if _read(R, item) is None:
            log('  ! atelier: %s - its item %s is gone from the game, not built' % (ck.split(BS)[-1], item))
            continue
        if ck in R and ck not in made:
            raise TransmogError('%s already exists in the database' % ck)
        make(db, ck, item, look or item, bool(e.get('icon')), log)
        made.add(ck)
    if made:
        log('  atelier: %d item look(s)' % len(made))
    return made


def check(R, path=None, log=print):
    """-> problems: every clone of the registry is there, of its item's Class, with exactly its item's fields except
    the look (and the icon when taken), and the look's look fields"""
    try:
        reg = load(path)
    except TransmogError as e:
        return [str(e)]
    bad = []
    names = {n.lower() for n in LOOK + ICON} | {'filedescription'}
    for ck, e in sorted(reg['clones'].items()):
        item, look, icon = key(e.get('item')), key(e.get('look')), bool(e.get('icon'))
        src = _read(R, item)
        if src is None:
            continue            # the game lost the item itself: nothing to check (apply said so)
        c = _read(R, ck)
        leaf = ck.split(BS)[-1]
        if c is None:
            bad.append('atelier: clone %s of %s is missing' % (leaf, item))
            continue
        if c['name'] != c['name'].lower():
            bad.append('atelier: uppercase record name ' + c['name'])
        fc, fs = fields(c), fields(src)
        if value(c, 'Class') != value(src, 'Class') or value(c, 'Class') not in CLASSES:
            bad.append('atelier: %s: Class %s, its item %s' % (leaf, value(c, 'Class'), value(src, 'Class')))
        for n in set(fc) | set(fs):
            if n in names:
                continue
            if fc.get(n) != fs.get(n):
                bad.append('atelier: %s: field %s differs from its item %s' % (leaf, n, item))
        lk = _read(R, look) if look and look != item else src
        lk = lk if lk is not None else src
        fl = fields(lk)
        for n in LOOK + (ICON if icon else ()):
            want = fl.get(n.lower()) if lk is not src else fs.get(n.lower())
            got = fc.get(n.lower())
            if (want and want[2]) != (got and got[2]):
                bad.append('atelier: %s: look field %s is not the look\'s' % (leaf, n))
        if not icon:
            for n in ICON:
                if fc.get(n.lower()) != fs.get(n.lower()):
                    bad.append('atelier: %s: icon %s changed although the cells differ' % (leaf, n))
        if not RECIPE.match(value(c, 'FileDescription')):
            bad.append('atelier: %s: no recipe in FileDescription' % leaf)
    if reg['clones']:
        log('atelier: %d item look(s) checked' % len(reg['clones']))
    return bad


# ------------------------------------------------------------ game archives (read-only): icons and texts
class Arc(object):
    """TQ .arc: table of contents + zlib parts; read only"""
    REC = struct.Struct('<5I8s4I')

    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            magic, ver, nfiles, nparts, parts_sz, names_sz, toc_off = struct.unpack('<4s6I', f.read(28))
            if magic != b'ARC\x00':
                raise ValueError('not an ARC: %s' % path)
            f.seek(toc_off)
            toc = f.read(parts_sz + names_sz + nfiles * self.REC.size)
        parts, names, recs = toc[:parts_sz], toc[parts_sz:parts_sz + names_sz], toc[parts_sz + names_sz:]
        self.parts = [struct.unpack_from('<3I', parts, i * 12) for i in range(nparts)]
        self.entries = {}
        for i in range(nfiles):
            t, off, comp, real, adler, ft, np_, fp, nl, no = self.REC.unpack_from(recs, i * self.REC.size)
            name = names[no:no + nl].decode('cp1252', 'replace')
            self.entries[name.lower().replace(BS, '/')] = (t, off, comp, real, np_, fp)

    def read(self, name):
        e = self.entries.get(name.lower().replace(BS, '/'))
        if e is None:
            return None
        t, off, comp, real, np_, fp = e
        with open(self.path, 'rb') as f:
            if t == 1 or (np_ <= 1 and comp == real):
                f.seek(off)
                return f.read(real)
            out = []
            for i in range(np_):
                po, pc, pr = self.parts[fp + i]
                f.seek(po)
                raw = f.read(pc)
                out.append(zlib.decompress(raw) if pc != pr else raw)
            return b''.join(out)


class Resources(object):
    """game file path (Items\\...\\x.tex, XPack2\\...) -> bytes from Resources\\*.arc"""
    def __init__(self, game):
        self.res = os.path.join(game, 'Resources')
        self.arcs = {}

    def _arc(self, folder, name):
        k = (folder.lower(), name.lower())
        if k not in self.arcs:
            self.arcs[k] = None
            if os.path.isdir(folder):
                real = [f for f in os.listdir(folder) if f.lower() == name.lower()]
                if real:
                    try:
                        self.arcs[k] = Arc(os.path.join(folder, real[0]))
                    except (OSError, ValueError, struct.error):
                        pass
        return self.arcs[k]

    def read(self, rel):
        parts = [p for p in (rel or '').replace('/', BS).split(BS) if p]
        if len(parts) < 2:
            return None
        if parts[0].lower().startswith('xpack') and len(parts) > 2 and os.path.isdir(self.res):
            sub = [d for d in os.listdir(self.res) if d.lower() == parts[0].lower()]
            if not sub:
                return None
            arc = self._arc(os.path.join(self.res, sub[0]), parts[1] + '.arc')
            inner = parts[2:]
        else:
            arc = self._arc(self.res, parts[0] + '.arc')
            inner = parts[1:]
        return arc.read('/'.join(inner)) if arc else None

    def tex_size(self, rel):
        """(width, height) in pixels of a .tex, or None (TEX v1: 12-byte header, v2 (Eternal Embers): 13)"""
        raw = self.read(rel)
        if not raw or raw[:3] != b'TEX' or len(raw) < 40:
            return None
        dds = raw[13:] if raw[3] == 2 else raw[12:]
        h, w = struct.unpack_from('<2I', dds, 12)
        return w, h


def cells(size):
    """inventory cells of an icon (32 px each, rounded up - Game.dll InventorySack::AdjustSizeForCell)"""
    return (-(-size[0] // 32), -(-size[1] // 32)) if size else None


def icon_fits(res, item_rec, look_rec):
    """the look's icons take the item's place only if both (and the female ones) occupy the same cells"""
    for n in ('bitmap', 'bitmapFemale'):
        a = value(item_rec, n) or value(item_rec, 'bitmap')
        b = value(look_rec, n) or value(look_rec, 'bitmap')
        ca, cb = cells(res.tex_size(a)), cells(res.tex_size(b))
        if not ca or ca != cb:
            return False
    return True
