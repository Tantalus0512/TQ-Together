# -*- coding: utf-8 -*-
"""Declarative database tweaks: <data folder>\\tweaks\\*.json, applied to the clean base before the companions
are built, so TQ Together stays the only program that writes database.arz and nothing overwrites anything.

A tweak file is data, never code:
  {"name": "What it does", "ops": [
     {"op": "clone", "from": "records\\\\...\\\\a.dbr", "to": "records\\\\tqmod\\\\tweaks\\\\b.dbr"},
     {"op": "set", "record": "records\\\\...\\\\b.dbr", "field": "lootName7", "type": "string", "values": ["..."]},
     {"op": "del", "record": "records\\\\...\\\\b.dbr", "field": "lootWeight9"}]}
type: int | real | string | bool (the game's own field types; the self-check compares them with vanilla).
Record names are stored lowercase (the game looks records up by the lowercased path). A clone must not
overwrite an existing record, and nothing may be written under records\\tqmod\\companions (ours).
"""
import glob, hashlib, json, os

import paths

TYPES = {'int': 0, 'real': 1, 'string': 2, 'bool': 3}
RESERVED = 'records\\tqmod\\companions\\'


def tweaks_dir():
    return os.path.join(paths.data_dir(), 'tweaks')


def files(folder=None):
    return sorted(glob.glob(os.path.join(glob.escape(folder or tweaks_dir()), '*.json')))   # 1.8.1: [ ] in a path


def fingerprint(folder=None):
    h = hashlib.md5()
    for p in files(folder):
        h.update(os.path.basename(p).lower().encode('utf-8'))
        with open(p, 'rb') as f:
            h.update(f.read())
    return h.hexdigest()


def _key(name):
    return name.replace('/', '\\').lower()


def _cast(v, t):
    if t == 1:
        return float(v)
    if t == 2:
        return str(v)
    return int(v)


class TweakError(Exception):
    pass


def apply(db, log=print, folder=None):
    """-> (set of record keys created or changed, [(tweak name, file, number of ops)])"""
    touched, done = set(), []
    R = db.arz.records
    for p in files(folder):
        try:
            with open(p, encoding='utf-8-sig') as f:
                t = json.load(f)
        except ValueError as e:
            raise TweakError('%s: not valid JSON (%s)' % (os.path.basename(p), e))
        if not isinstance(t, dict) or not isinstance(t.get('ops', []), list):
            raise TweakError('%s: want {"name": ..., "ops": [...]}' % os.path.basename(p))
        name = t.get('name') or os.path.basename(p)
        for i, op in enumerate(t.get('ops', []), 1):
            where = '%s op %d' % (os.path.basename(p), i)
            try:
                _apply_op(db, R, op, where, touched)
            except TweakError:
                raise
            except (KeyError, ValueError, TypeError, AttributeError) as e:    # 1.8.1: a missing key, "true" as int
                raise TweakError('%s: %s %r' % (where, type(e).__name__, e))
        done.append((name, os.path.basename(p), len(t.get('ops', []))))
        log('  tweak: %s (%s, %d changes)' % (name, os.path.basename(p), len(t.get('ops', []))))
    return touched, done


def _apply_op(db, R, op, where, touched):
    kind = op.get('op')
    if kind == 'clone':
        src, dst = _key(op['from']), _key(op['to'])
        if dst.startswith(RESERVED):
            raise TweakError('%s: %s is reserved for TQ Together' % (where, dst))
        if R.get(src) is None:
            raise TweakError('%s: source record %s does not exist' % (where, src))
        if R.get(dst) is not None:
            raise TweakError('%s: %s already exists' % (where, dst))
        db.clone(src, dst)
        touched.add(dst)
    elif kind in ('set', 'del'):
        k = _key(op['record'])
        if k.startswith(RESERVED):
            raise TweakError('%s: %s is reserved for TQ Together' % (where, k))
        r = R.get(k)
        if r is None:
            raise TweakError('%s: record %s does not exist' % (where, k))
        fl = op['field'].lower()
        keep = [v for v in r['vars'] if v[0].lower() != fl]
        if kind == 'set':
            if op.get('type') not in TYPES:
                raise TweakError('%s: type must be one of %s' % (where, ', '.join(TYPES)))
            vt = TYPES[op['type']]
            vals = op['values'] if isinstance(op['values'], list) else [op['values']]
            old = [v for v in r['vars'] if v[0].lower() == fl]
            keep.append((old[0][0] if old else op['field'], vt, [_cast(v, vt) for v in vals]))
        r['vars'] = keep
        R[k] = r
        db.mark(k)
        touched.add(k)
    else:
        raise TweakError('%s: unknown op %r' % (where, kind))
