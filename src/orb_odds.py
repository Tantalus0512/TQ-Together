# -*- coding: utf-8 -*-
"""Expected number of a given item per electrum orb, walking the orb's loot definition exactly:
FixedItemLoot (independent slots: chance x weighted pick) -> LootMasterTable / FixedWeight tables (weighted pick).
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
        if tpl.endswith('fixeditemloot.tpl'):
            tot = 0.0
            for n in range(1, 40):
                ch = (f.get('loot%dChance' % n) or [0])[0]
                pairs = [(key(f['loot%dName%d' % (n, j)][0]), float((f.get('loot%dWeight%d' % (n, j)) or [0])[0]))
                         for j in range(1, 40) if (f.get('loot%dName%d' % (n, j)) or [''])[0]]
                W = sum(w for _, w in pairs)
                if ch and W:
                    tot += ch / 100.0 * sum(w / W * p(x) for x, w in pairs)
            return tot
        if cls in ('LootMasterTable', 'LootItemTable_FixedWeight'):
            pairs = [(key(f['lootName%d' % j][0]), float((f.get('lootWeight%d' % j) or [0])[0]))
                     for j in range(1, 60) if (f.get('lootName%d' % j) or [''])[0]]
            W = sum(w for _, w in pairs)
            return sum(w / W * p(x) for x, w in pairs) if W else 0.0
        return 0.0
    return p


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
