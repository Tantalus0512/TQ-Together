# -*- coding: utf-8 -*-
"""Lazy .arz database: records are decoded only when touched; untouched records are written back byte-for-byte
(their compressed blobs are reused, the original string table stays a prefix of the new one).
Memory: the raw file + an index, instead of ~100k decoded records (several GB in Python objects).
Same record shape as arz.Arz: {'name', 'type', 'vars': [(name, vtype, [values])]}, keys lowercase with backslashes."""
import struct, zlib
from collections.abc import MutableMapping

BS = chr(92)
HDR = struct.Struct('<2H5i')      # magic(2) version(2) rt_start rt_size rt_entries st_start st_size
FILETIME = 0


class OrderList(list):
    """record order without duplicates: DB.put and LazyRecords both append new keys"""
    def __init__(self, *a):
        super().__init__(*a)
        self._set = set(self)

    def append(self, k):
        if k not in self._set:
            self._set.add(k)
            super().append(k)


class LazyRecords(MutableMapping):
    def __init__(self, arz):
        self._a = arz
        self._cache = {}

    def __getitem__(self, k):
        r = self._cache.get(k)
        if r is None:
            if k not in self._a.index:
                raise KeyError(k)
            r = self._a.decode(k)
            self._cache[k] = r
        return r

    def __setitem__(self, k, rec):
        if k not in self._cache and k not in self._a.index:
            self._a.order.append(k)
        self._cache[k] = rec

    def __delitem__(self, k):
        raise NotImplementedError('records are never deleted from a game database here')

    def __contains__(self, k):
        return k in self._cache or k in self._a.index

    def __iter__(self):
        return iter(self._a.order)

    def __len__(self):
        return len(self._a.order)

    def decoded(self):
        return self._cache

    def stream(self):
        """(key, record) for every record WITHOUT keeping them in memory (for one-off full scans)"""
        for k in self._a.order:
            yield k, (self._cache[k] if k in self._cache else self._a.decode(k))


class LazyArz(object):
    def __init__(self):
        self.raw = b''
        self.strings = []
        self.index = {}      # key -> (name_idx, rtype, off, csize)
        self.order = OrderList()
        self.tail0 = 0
        self.head = 0
        self.records = LazyRecords(self)

    @classmethod
    def load(cls, path):
        a = cls()
        with open(path, 'rb') as f:
            raw = f.read()
        a.raw = raw
        magic, ver, rt_start, rt_size, rt_entries, st_start, st_size = HDR.unpack_from(raw, 0)
        a.head = (magic, ver)
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
            key = strs[si].lower().replace('/', BS)
            if key not in a.index:
                a.order.append(key)
            a.index[key] = (si, rtype, off, csize)
        return a

    def decode(self, key):
        si, rtype, off, csize = self.index[key]
        strs, raw = self.strings, self.raw
        data = zlib.decompress(raw[24 + off:24 + off + csize])
        rec = {'name': strs[si], 'type': rtype, 'vars': []}
        q, L = 0, len(data)
        while q < L:
            vt, cnt = struct.unpack_from('<2h', data, q); q += 4
            nidx = struct.unpack_from('<i', data, q)[0]; q += 4
            if vt == 1:
                vals = list(struct.unpack_from('<%df' % cnt, data, q))
            elif vt == 2:
                vals = [strs[i] for i in struct.unpack_from('<%di' % cnt, data, q)]
            else:
                vals = list(struct.unpack_from('<%di' % cnt, data, q))
            q += 4 * cnt
            rec['vars'].append((strs[nidx], vt, vals))
        return rec

    def save(self, path, level=1):
        pool = {}
        order = list(self.strings)                     # original ids stay valid for reused blobs
        for i, s in enumerate(order):
            pool.setdefault(s, i)

        def sid(s):
            i = pool.get(s)
            if i is None:
                i = len(order)
                pool[s] = i
                order.append(s)
            return i

        cache = self.records.decoded()
        blobs, entries, offset = [], [], 0
        for key in self.order:
            if key in cache:
                rec = cache[key]
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
                blob = zlib.compress(bytes(buf), level)
                name_idx, rtype = sid(rec['name']), rec['type']
            else:
                si, rtype, off, csize = self.index[key]
                blob = self.raw[24 + off:24 + off + csize]
                name_idx = si
            blobs.append(blob)
            entries.append((name_idx, rtype, offset, len(blob)))
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
        hdr = HDR.pack(self.head[0], self.head[1], rt_start, len(rt), len(entries), st_start, len(st))
        tail = struct.pack('<4I', self.tail0 or 0, zlib.adler32(st) & 0xffffffff,
                           zlib.adler32(data) & 0xffffffff, zlib.adler32(rt) & 0xffffffff)
        with open(path, 'wb') as f:
            f.write(hdr); f.write(data); f.write(rt); f.write(st); f.write(tail)


def valid_arz(path):
    """cheap structural check (a half-written copy fails it): the tables described by the header fit the file"""
    import os
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            h = f.read(24)
        magic, ver, rt_start, rt_size, rt_entries, st_start, st_size = HDR.unpack(h)
        return rt_start > 24 and rt_entries > 0 and st_start >= rt_start + rt_size and st_start + st_size + 16 == size
    except Exception:
        return False
