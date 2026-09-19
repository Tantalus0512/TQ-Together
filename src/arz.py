# -*- coding: utf-8 -*-
"""Titan Quest .arz database reader/writer (pure python).

Record model:  rec = {'name': 'records\\...\\x.dbr', 'type': 'Monster',
                     'vars': [ (varname, vtype, [values...]), ... ] }
vtype: 0 = int, 1 = float, 2 = string, 3 = bool(int)
"""
import struct, zlib, os, sys

HDR = struct.Struct('<6i')
BS = chr(92)
FILETIME = 0x01D6E83B02515DF4   # any plausible constant; engine does not care


class Arz(object):
    def __init__(self):
        self.strings = []
        self.records = {}    # lowercase name -> rec
        self.order = []      # lowercase names in file order
        self.tail0 = 0

    # ------------------------------------------------------------------ read
    @classmethod
    def load(cls, path):
        a = cls()
        with open(path, 'rb') as f:
            raw = f.read()
        unk, rt_start, rt_size, rt_entries, st_start, st_size = HDR.unpack_from(raw, 0)
        a.tail0 = struct.unpack_from('<I', raw, st_start + st_size)[0]
        p = st_start
        n = struct.unpack_from('<i', raw, p)[0]; p += 4
        strs = []
        for _ in range(n):
            l = struct.unpack_from('<i', raw, p)[0]; p += 4
            strs.append(raw[p:p + l].decode('cp1252', 'replace')); p += l
        a.strings = strs
        p = rt_start
        for _ in range(rt_entries):
            si = struct.unpack_from('<i', raw, p)[0]; p += 4
            l = struct.unpack_from('<i', raw, p)[0]; p += 4
            rtype = raw[p:p + l].decode('cp1252', 'replace'); p += l
            off, csize = struct.unpack_from('<2i', raw, p); p += 16
            data = zlib.decompress(raw[24 + off:24 + off + csize])
            rec = {'name': strs[si], 'type': rtype, 'vars': []}
            q = 0; L = len(data)
            while q < L:
                vt, cnt = struct.unpack_from('<2h', data, q); q += 4
                nidx = struct.unpack_from('<i', data, q)[0]; q += 4
                vals = []
                for _k in range(cnt):
                    if vt == 1:
                        vals.append(struct.unpack_from('<f', data, q)[0])
                    elif vt == 2:
                        vals.append(strs[struct.unpack_from('<i', data, q)[0]])
                    else:
                        vals.append(struct.unpack_from('<i', data, q)[0])
                    q += 4
                rec['vars'].append((strs[nidx], vt, vals))
            key = rec['name'].lower().replace('/', BS)
            if key not in a.records:
                a.order.append(key)
            a.records[key] = rec
        return a

    # ----------------------------------------------------------------- write
    def save(self, path, level=9):
        pool = {}
        order = []

        def sid(s):
            i = pool.get(s)
            if i is None:
                i = len(order)
                pool[s] = i
                order.append(s)
            return i

        blobs = []
        entries = []
        offset = 0
        for key in self.order:
            rec = self.records[key]
            name_idx = sid(rec['name'])
            buf = bytearray()
            for vname, vt, vals in rec['vars']:
                buf += struct.pack('<2hi', vt, len(vals), sid(vname))
                for v in vals:
                    if vt == 1:
                        buf += struct.pack('<f', float(v))
                    elif vt == 2:
                        buf += struct.pack('<i', sid(v))
                    else:
                        buf += struct.pack('<i', int(v))
            blob = zlib.compress(bytes(buf), level)   # any level loads; 1 is ~5x faster than 9
            blobs.append(blob)
            entries.append((name_idx, rec['type'], offset, len(blob)))
            offset += len(blob)

        data = b''.join(blobs)
        rt = bytearray()
        for name_idx, rtype, off, csize in entries:
            tb = rtype.encode('cp1252', 'replace')
            rt += struct.pack('<i', name_idx)
            rt += struct.pack('<i', len(tb)) + tb
            rt += struct.pack('<2i', off, csize)
            rt += struct.pack('<Q', FILETIME)
        rt = bytes(rt)

        st = bytearray(struct.pack('<i', len(order)))
        for s in order:
            sb = s.encode('cp1252', 'replace')
            st += struct.pack('<i', len(sb)) + sb
        st = bytes(st)

        rt_start = 24 + len(data)
        st_start = rt_start + len(rt)
        hdr = HDR.pack(196612, rt_start, len(rt), len(entries), st_start, len(st))
        tail = struct.pack('<4I', self.tail0 or 0,
                           zlib.adler32(st) & 0xffffffff,
                           zlib.adler32(data) & 0xffffffff,
                           zlib.adler32(rt) & 0xffffffff)
        with open(path, 'wb') as f:
            f.write(hdr); f.write(data); f.write(rt); f.write(st); f.write(tail)

    # ------------------------------------------------------------- dbr <-> rec
    @staticmethod
    def rec_to_text(rec):
        out = []
        for name, vt, vals in rec['vars']:
            if vt == 1:
                s = ';'.join('%f' % v for v in vals)
            else:
                s = ';'.join(str(v) for v in vals)
            out.append('%s,%s,' % (name, s))
        return '\r\n'.join(out) + '\r\n'

    @staticmethod
    def text_to_rec(name, text, proto=None):
        """Parse a loose .dbr. `proto` (an existing rec) supplies var types."""
        types = {}
        if proto:
            for vn, vt, _v in proto['vars']:
                types[vn.lower()] = vt
        rec = {'name': name, 'type': proto['type'] if proto else '', 'vars': []}
        for line in text.replace('\r', '').split('\n'):
            if not line.strip():
                continue
            parts = line.split(',')
            if len(parts) < 2:
                continue
            k = parts[0]
            raw = ','.join(parts[1:])
            if raw.endswith(','):
                raw = raw[:-1]
            vt = types.get(k.lower())
            items = raw.split(';') if raw != '' else ['']
            if vt is None:
                vt = _infer(items)
            vals = []
            for it in items:
                if vt == 1:
                    vals.append(float(it) if it.strip() else 0.0)
                elif vt == 2:
                    vals.append(it)
                else:
                    try:
                        vals.append(int(float(it)) if it.strip() else 0)
                    except ValueError:
                        vt = 2
                        vals = list(items)
                        break
            rec['vars'].append((k, vt, vals))
        return rec


def _infer(items):
    allint = True
    allnum = True
    for it in items:
        s = it.strip()
        if s == '':
            return 2
        try:
            f = float(s)
        except ValueError:
            return 2
        if '.' in s or 'e' in s.lower():
            allint = False
    return 0 if allint else 1


def main():
    src, dst = sys.argv[1], sys.argv[2]
    a = Arz.load(src)
    sys.stderr.write('records: %d strings: %d\n' % (len(a.records), len(a.strings)))
    if dst != '-':
        for key in a.order:
            rec = a.records[key]
            p = os.path.join(dst, rec['name'].replace(BS, os.sep))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'wb') as f:
                f.write(Arz.rec_to_text(rec).encode('cp1252', 'replace'))


if __name__ == '__main__':
    main()
