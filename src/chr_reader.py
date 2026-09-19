# -*- coding: utf-8 -*-
"""Very tolerant reader for Titan Quest Player.chr saves.

The file is a flat stream of length-prefixed ASCII keys followed by
key-dependent payloads.  We do not need the full schema: we scan for
length-prefixed strings and pick up the fields we care about.
"""
import struct, sys, os, re

KEY_RE = re.compile(rb'^[A-Za-z_][A-Za-z0-9_ ]*$')
PATH_RE = re.compile(rb'^[A-Za-z0-9_ ()\'\-.%\\/]+$')


def scan(path):
    with open(path, 'rb') as f:
        raw = f.read()
    out = []          # (offset, kind, value)   kind: 'a' ascii, 'u' utf16
    i = 0
    n = len(raw)
    while i + 4 <= n:
        l = struct.unpack_from('<i', raw, i)[0]
        if 1 <= l <= 300 and i + 4 + l <= n:
            b = raw[i + 4:i + 4 + l]
            if KEY_RE.match(b) or (b.count(b'\\') and PATH_RE.match(b)):
                out.append((i, 'a', b.decode('cp1252', 'replace')))
                i += 4 + l
                continue
        if i + 4 + 2 <= n:
            l2 = l
            if 1 <= l2 <= 100 and i + 4 + 2 * l2 <= n:
                b = raw[i + 4:i + 4 + 2 * l2]
                if all(b[k * 2 + 1] == 0 and 32 <= b[k * 2] < 127 for k in range(l2)):
                    out.append((i, 'u', b.decode('utf-16-le', 'replace')))
                    i += 4 + 2 * l2
                    continue
        i += 1
    return raw, out


def i32(raw, off):
    return struct.unpack_from('<i', raw, off)[0]


def read_char(path):
    raw, toks = scan(path)
    info = {'path': path, 'name': os.path.basename(os.path.dirname(path)).lstrip('_'),
            'level': 1, 'class': '', 'skills': [], 'items': [], 'masteries': []}
    for idx, (off, kind, val) in enumerate(toks):
        end = off + 4 + (len(val) * (2 if kind == 'u' else 1))
        if val == 'playerLevel':
            info['level'] = i32(raw, end)
        elif val == 'playerCharacterClass':
            nxt = toks[idx + 1] if idx + 1 < len(toks) else None
            if nxt:
                info['class'] = nxt[2]
        elif val == 'myPlayerName':
            nxt = toks[idx + 1] if idx + 1 < len(toks) else None
            if nxt and nxt[1] == 'u':
                info['name'] = nxt[2]
        elif val == 'skillName':
            nxt = toks[idx + 1] if idx + 1 < len(toks) else None
            if nxt and BSLASH in nxt[2]:
                lvl = 1
                for j in range(idx + 2, min(idx + 8, len(toks))):
                    if toks[j][2] == 'skillLevel':
                        e2 = toks[j][0] + 4 + len(toks[j][2])
                        lvl = i32(raw, e2)
                        break
                info['skills'].append((nxt[2], lvl))
        elif val == 'baseName':
            nxt = toks[idx + 1] if idx + 1 < len(toks) else None
            if nxt and nxt[1] == 'a' and nxt[2].lower().endswith('.dbr'):
                pfx = sfx = ''
                for j in range(idx + 2, min(idx + 10, len(toks))):
                    if toks[j][2] == 'prefixName' and j + 1 < len(toks) and toks[j + 1][2].lower().endswith('.dbr'):
                        pfx = toks[j + 1][2]
                    if toks[j][2] == 'suffixName' and j + 1 < len(toks) and toks[j + 1][2].lower().endswith('.dbr'):
                        sfx = toks[j + 1][2]
                    if toks[j][2] == 'baseName':
                        break
                info['items'].append({'base': nxt[2], 'prefix': pfx, 'suffix': sfx, 'off': off})
        elif val == 'equipmentCtrlIOStreamVersion':
            info['equip_off'] = off
    eo = info.get('equip_off')
    info['equipped'] = [it for it in info['items'] if eo and it['off'] > eo] if eo else []
    seen = set()
    for s, l in info['skills']:
        sl = s.lower()
        if 'mastery' in sl and sl not in seen:
            seen.add(sl)
            info['masteries'].append((s, l))
    return info


BSLASH = chr(92)


if __name__ == '__main__':
    for p in sys.argv[1:]:
        c = read_char(p)
        print('%-20s lvl %-4d class=%-12s skills=%d items=%d' %
              (c['name'], c['level'], c['class'], len(c['skills']), len(c['items'])))
        for m in c['masteries']:
            print('   mastery:', m)
        for s in c['skills'][:12]:
            print('   skill  :', s)
        for it in c['items'][:12]:
            print('   item   :', it['base'])
