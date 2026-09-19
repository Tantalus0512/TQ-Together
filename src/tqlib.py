# -*- coding: utf-8 -*-
"""Shared helpers for the TQ Eternal Embers mod toolkit."""
import os, sys, pickle, struct, copy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from arz import Arz

BS = chr(92)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = r'D:\Steam\steamapps\common\Titan Quest Anniversary Edition'
CACHE = os.path.join(ROOT, 'build', '_db.pickle')


# --------------------------------------------------------------------- record
def key_of(name):
    return name.lower().replace('/', BS)


def getv(rec, k):
    kl = k.lower()
    for vn, vt, vals in rec['vars']:
        if vn.lower() == kl:
            return vals
    return None


def get1(rec, k, default=None):
    v = getv(rec, k)
    if v is None or not v:
        return default
    return v[0]


def setv(rec, k, value, vtype=None):
    """value: scalar or list. Type inherited from the existing var when present."""
    if not isinstance(value, (list, tuple)):
        value = [value]
    kl = k.lower()
    for i, (vn, vt, vals) in enumerate(rec['vars']):
        if vn.lower() == kl:
            t = vtype if vtype is not None else vt
            rec['vars'][i] = (vn, t, [_cast(v, t) for v in value])
            return
    t = vtype if vtype is not None else _guess(value)
    rec['vars'].append((k, t, [_cast(v, t) for v in value]))


def delv(rec, k):
    kl = k.lower()
    rec['vars'] = [t for t in rec['vars'] if t[0].lower() != kl]


def _guess(value):
    if all(isinstance(v, bool) or isinstance(v, int) for v in value):
        return 0
    if all(isinstance(v, (int, float)) for v in value):
        return 1
    return 2


def _cast(v, t):
    if t == 1:
        return float(v)
    if t == 2:
        return str(v)
    return int(v)


def scale(rec, k, factor, minimum=None):
    v = getv(rec, k)
    if v is None:
        return False
    t = [vt for vn, vt, _ in rec['vars'] if vn.lower() == k.lower()][0]
    if t == 2:
        return False
    out = []
    for x in v:
        y = x * factor
        if minimum is not None and x > 0 and y < minimum:
            y = minimum
        out.append(y)
    setv(rec, k, out)
    return True


# ------------------------------------------------------------------------- db
class DB(object):
    def __init__(self, arz):
        self.arz = arz
        self.touched = set()      # keys we changed or created

    def get(self, name):
        return self.arz.records.get(key_of(name))

    def need(self, name):
        r = self.get(name)
        if r is None:
            raise KeyError(name)
        return r

    def mark(self, name):
        self.touched.add(key_of(name))

    def edit(self, name):
        r = self.need(name)
        self.mark(name)
        return r

    def clone(self, src, dst, mark=True):
        s = self.need(src)
        r = {'name': dst, 'type': s['type'],
             'vars': [(vn, vt, list(vals)) for vn, vt, vals in s['vars']]}
        self.put(r)
        return r

    def put(self, rec):
        k = key_of(rec['name'])
        if k not in self.arz.records:
            self.arz.order.append(k)
        self.arz.records[k] = rec
        self.touched.add(k)

    def find(self, pred):
        for k in self.arz.order:
            r = self.arz.records[k]
            if pred(r):
                yield r

    def by_template(self, tpl):
        t = tpl.lower()
        for k in self.arz.order:
            r = self.arz.records[k]
            tn = get1(r, 'templateName', '')
            if tn and tn.lower().replace('/', BS).endswith(t):
                yield r


def vanilla_arz():
    """Never read the live database.arz for building - once the mod is
    installed that file IS the mod, and a rebuild would compound on itself."""
    for p in (os.path.join(ROOT, 'vanilla', 'database.arz'),
              os.path.join(GAME, 'Database', 'database.arz.tqmod-backup'),
              os.path.join(GAME, 'Database', 'database.arz')):
        if os.path.exists(p):
            return p
    raise IOError('no database.arz found')


def load_db(use_cache=True):
    src = vanilla_arz()
    if use_cache and os.path.exists(CACHE) and os.path.getmtime(CACHE) > os.path.getmtime(src):
        with open(CACHE, 'rb') as f:
            a = pickle.load(f)
    else:
        a = Arz.load(src)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, 'wb') as f:
            pickle.dump(a, f, 4)
    return DB(a)


def overlay_loose(db, folder):
    """Merge loose .dbr overrides (e.g. the user's existing skills++ install)."""
    n = 0
    base = os.path.abspath(folder)
    for dirpath, _d, files in os.walk(base):
        for fn in files:
            if not fn.lower().endswith('.dbr'):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, base).replace(os.sep, BS)
            name = 'records' + BS + rel
            proto = db.get(name)
            with open(full, 'rb') as f:
                txt = f.read().decode('cp1252', 'replace')
            rec = Arz.text_to_rec(proto['name'] if proto else name, txt, proto)
            if proto:
                rec['type'] = proto['type']
                # ArtManager writes a blank line for every unset template field.
                # Keeping those adds fields vanilla never had (e.g. a STRING
                # 'experienceLevels' where the template wants an int array),
                # which the engine then reads as a broken table.
                have = {vn.lower() for vn, _t, _v in proto['vars']}
                rec['vars'] = [(vn, vt, vals) for vn, vt, vals in rec['vars']
                               if vn.lower() in have
                               or not (vt == 2 and all(str(x) == '' for x in vals))]
            db.arz.records[key_of(name)] = rec
            if key_of(name) not in db.arz.order:
                db.arz.order.append(key_of(name))
            n += 1
    return n


def write_loose(db, outdir):
    n = 0
    for k in sorted(db.touched):
        rec = db.arz.records[k]
        rel = rec['name']
        if rel.lower().startswith('records' + BS):
            rel = rel[len('records' + BS):]
        p = os.path.join(outdir, 'records', rel.replace(BS, os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(Arz.rec_to_text(rec).encode('cp1252', 'replace'))
        n += 1
    return n


# ------------------------------------------------------------------ tex tools
def read_tex(path):
    with open(path, 'rb') as f:
        raw = f.read()
    assert raw[:3] == b'TEX', path
    return raw[:12], raw[12:]


def write_tex(path, hdr, dds):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(hdr[:8] + struct.pack('<i', len(dds)))
        f.write(dds)


def _u565(c):
    return (((c >> 11) & 31) / 31.0, ((c >> 5) & 63) / 63.0, (c & 31) / 31.0)


def _p565(r, g, b):
    r = max(0.0, min(1.0, r)); g = max(0.0, min(1.0, g)); b = max(0.0, min(1.0, b))
    return (int(round(r * 31)) << 11) | (int(round(g * 63)) << 5) | int(round(b * 31))


def recolor_dds(dds, fn):
    """Apply fn(r,g,b)->(r,g,b) to every DXT1/3/5 colour endpoint. In-place-ish."""
    # Titan Quest stamps 'DDSR', not the standard 'DDS ' magic.
    if dds[:3] != b'DDS':
        return dds
    hsize = struct.unpack_from('<I', dds, 4)[0]
    fourcc = dds[84:88]
    if fourcc == b'DXT1':
        stride, coff = 8, 0
    elif fourcc in (b'DXT3', b'DXT5'):
        stride, coff = 16, 8
    else:
        return dds
    body = bytearray(dds[4 + hsize:])
    head = dds[:4 + hsize]
    for i in range(0, len(body) - stride + 1, stride):
        c0 = body[i + coff] | (body[i + coff + 1] << 8)
        c1 = body[i + coff + 2] | (body[i + coff + 3] << 8)
        n0 = _p565(*fn(*_u565(c0)))
        n1 = _p565(*fn(*_u565(c1)))
        # DXT1 switches to 3-colour+alpha mode when c0 <= c1; keep the original
        # ordering so a recolour never changes the block mode.
        # (nudging, never swapping: the 2-bit indices are tied to c0/c1 order)
        if stride == 8 and (c0 > c1) != (n0 > n1):
            n1 = max(0, n0 - 1) if c0 > c1 else min(0xFFFF, n0 + 1)
        body[i + coff] = n0 & 0xFF
        body[i + coff + 1] = (n0 >> 8) & 0xFF
        body[i + coff + 2] = n1 & 0xFF
        body[i + coff + 3] = (n1 >> 8) & 0xFF
    return head + bytes(body)


def tint_fn(tint, sat=1.0, gamma=1.0, boost=1.0):
    tr, tg, tb = tint

    def f(r, g, b):
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        lum = pow(max(lum, 0.0), gamma) * boost
        r2 = lum * tr + (r - lum) * sat
        g2 = lum * tg + (g - lum) * sat
        b2 = lum * tb + (b - lum) * sat
        return (r2, g2, b2)
    return f


# ----------------------------------------------------------------- text tools
def write_text_file(path, pairs):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ['// TQMod generated - do not edit by hand']
    for k, v in pairs:
        lines.append('%s=%s' % (k, v))
    data = ('\r\n'.join(lines) + '\r\n')
    with open(path, 'wb') as f:
        f.write(b'\xff\xfe')
        f.write(data.encode('utf-16-le'))


def read_text_file(path):
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:2] == b'\xff\xfe':
        raw = raw[2:]
    return raw.decode('utf-16-le', 'replace')


def load_game_text(lang):
    """tag -> localized string, from extract/text_<lang>/*.txt"""
    import glob
    d = os.path.join(ROOT, 'extract', 'text_' + lang)
    out = {}
    for p in glob.glob(os.path.join(d, '*.txt')):
        try:
            txt = read_text_file(p)
        except Exception:
            continue
        for line in txt.split('\n'):
            line = line.strip('\r').strip()
            if not line or line.startswith('/') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            if k and k not in out:
                out[k] = v
    return out
