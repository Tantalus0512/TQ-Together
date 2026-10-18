# -*- coding: utf-8 -*-
"""Odds of a given item from a container (electrum orb, boss chest), walking the loot definition as the engine does
(1.5.0, Game.dll): FixedItemController::PickLootRecord 0x10181280 takes ONE record of the container's `tables` (by
difficulty / level index); SelectLootNumber 0x10181da0 draws the number of items from numSpawnMin/MaxEquation
(numberOfPlayers); SelectLoot 0x10181530 picks, for EACH item, one slot with probability lootNChance / (sum of the six
chances) - a running total, not 100 - then a weighted pick inside the slot. Nested LootMasterTable / FixedWeight tables
are weighted picks. (Before 1.5.0 this model counted one item per orb; an orb gives 7-8.)
  py -3 orb_odds.py [build|vanilla] [record substring]"""
import sys, re, functools
sys.path.insert(0, r'D:\TQMod\tools')
from arz import Arz
BS = chr(92)
SRC = {'build': r'D:\TQMod\companions\build\database.arz',
       'vanilla': r'D:\Steam\steamapps\common\Titan Quest Anniversary Edition\Database\database.arz.tqmod-backup'}


def load(which):
    return Arz.load(SRC[which]).records


def key(x):
    return x.lower().replace('/', BS)


def fields(r):
    return {vn: vals for vn, vt, vals in r['vars']}


LOOT_WORDS = ('loot', 'container', 'proxies', 'pool', 'electrum', 'tqmod')
# 1.7.8 (owner 18.10: "a heap of electrum orbs, eidolon shards, not one soul shard"): the engine reads SIX entries per
# FixedItemLoot slot (lootNName1..6: the untouched game never names a 7th in 583 records) and 30 per LootMasterTable /
# FixedWeight table. This model read 39 / 59, so the soul at entry 7 or 8 counted though the game never rolled it
SLOT_MAX = 6
TABLE_MAX = 30


def slot_pairs(f, n):
    """[(entry key, weight)] the engine reads in slot n of a FixedItemLoot record (field dict)"""
    return [(key(f['loot%dName%d' % (n, j)][0]), float((f.get('loot%dWeight%d' % (n, j)) or [0])[0]))
            for j in range(1, SLOT_MAX + 1) if (f.get('loot%dName%d' % (n, j)) or [''])[0]]


def past_slot_max(f):
    """[(slot, entry)] named past SLOT_MAX in a FixedItemLoot record (field dict): the engine never rolls them"""
    return [(n, j) for n in range(1, 7) for j in range(SLOT_MAX + 1, 40) if (f.get('loot%dName%d' % (n, j)) or [''])[0]]


def kept_share(R, f, n, x):
    """chance x the weight share of table x in slot n - x itself, or x inside one of our wrapper tables (1.7.8: when a
    slot had no free entry, ours went in together with one vanilla entry): what every vanilla entry must keep"""
    ch = float((f.get('loot%dChance' % n) or [0])[0])
    pairs = slot_pairs(f, n)
    W = sum(w for _, w in pairs)
    if not (ch and W):
        return 0.0
    x = key(x)
    share = 0.0
    for k, w in pairs:
        if k == x:
            share += w / W
        elif 'tqmod' in k and R.get(k) is not None:
            g = fields(R[k])
            sub = [(key(g['lootName%d' % i][0]), float((g.get('lootWeight%d' % i) or [0])[0]))
                   for i in range(1, TABLE_MAX + 1) if (g.get('lootName%d' % i) or [''])[0]]
            Ws = sum(v for _, v in sub)
            share += w / W * sum(v / Ws for s, v in sub if s == x) if Ws else 0.0
    return ch * share


def lootish(k):
    """records that can hold/lead to other loot: tables, pools, containers, proxies (items and relics never do)"""
    return any(w in k for w in LOOT_WORDS)


def odds(R, targets):
    """-> function(record key) = expected count of any of `targets` produced by one roll of that record"""
    @functools.lru_cache(maxsize=None)
    def p(k):
        if k in targets:
            return 1.0
        if not lootish(k):
            return 0.0
        r = R.get(k)
        if r is None:
            return 0.0
        f = fields(r)
        cls = (f.get('Class') or [''])[0]
        tpl = (f.get('templateName') or [''])[0].lower()
        # ONE item: slot by chance / running total, then by weight. 1.6.3: FixedItemLootTartarus.tpl (the Tartarus orb)
        # has the same loot slots, no count equations
        if tpl.endswith(('fixeditemloot.tpl', 'fixeditemloottartarus.tpl')):
            tot, total = 0.0, sum(float((f.get('loot%dChance' % n) or [0])[0]) for n in range(1, 7))
            for n in range(1, 7):
                ch = float((f.get('loot%dChance' % n) or [0])[0])
                pairs = slot_pairs(f, n)
                W = sum(w for _, w in pairs)
                if ch and W and total:
                    tot += ch / total * sum(w / W * p(x) for x, w in pairs)
            return tot
        if cls in ('LootMasterTable', 'LootItemTable_FixedWeight'):
            pairs = [(key(f['lootName%d' % j][0]), float((f.get('lootWeight%d' % j) or [0])[0]))
                     for j in range(1, TABLE_MAX + 1) if (f.get('lootName%d' % j) or [''])[0]]
            W = sum(w for _, w in pairs)
            return sum(w / W * p(x) for x, w in pairs) if W else 0.0
        return 0.0
    return p


def spawn_counts(f):
    """FixedItemController::SelectLootNumber: the item count lies between the two equations (one player)"""
    def ev(name, d):
        e = (f.get(name) or [''])[0]
        if not e:
            return d
        try:
            return float(eval(e.replace('^', '**'), {'__builtins__': {}}, {'numberOfPlayers': 1}))
        except Exception:
            return d
    lo = ev('numSpawnMinEquation', 1.0)
    hi = ev('numSpawnMaxEquation', lo)
    lo, hi = int(min(lo, hi)), int(max(lo, hi))
    return list(range(max(1, lo), max(1, hi) + 1))


def per_container(R, table, targets, p=None):
    """chance that ONE opening of a container rolling `table` gives at least one of `targets`"""
    p = p or odds(R, targets)
    q = min(1.0, p(table))
    ns = spawn_counts(fields(R[table]))
    return sum(1 - (1 - q) ** n for n in ns) / len(ns)


def orbs(R):
    out = []
    for k in R:
        if 'casino' not in k:
            continue
        f = fields(R[k])
        if (f.get('Class') or [''])[0] != 'NpcCasinoMerchant' or not f.get('altOrbs'):
            continue
        for i, px in enumerate(f.get('altOrbs') or []):
            price = (f.get('altOrbsPrices') or [0] * 40)[i]
            pf = fields(R[key(px)])
            pool = fields(R[key(pf['accessoryLegendary1'][0])])
            cont = fields(R[key(pool['fixedItemName1'][0])])
            out.append((px.split(BS)[-1].replace('_Loot_Proxy.dbr', ''), price, key(cont['tables'][0])))
        break
    return out


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'build'
    sub = sys.argv[2].lower() if len(sys.argv) > 2 else 'companions' + BS + 'immortal_relic.dbr'
    R = load(which)
    tg = frozenset(k for k in R if sub in k)
    allrel = frozenset(k for k in R if (fields(R[k]).get('Class') or [''])[0] in ('ItemRelic', 'ItemCharm'))
    p, pr = odds(R, tg), odds(R, allrel)
    print('target:', sorted(tg))
    print('%-30s %8s %10s %12s %12s' % ('orb', 'price', 'E[target]', '1 in N orbs', 'E[any relic]'))
    for name, price, t in orbs(R):
        e = p(t)
        print('%-30s %8s %10.5f %12s %12.3f' % (name, price, e, ('%.0f' % (1 / e)) if e else '-', pr(t)))
