# -*- coding: utf-8 -*-
"""Static checks of build\\database.arz (companions). Run after every build: must print ALL CHECKS PASSED.
Each check = a failure that already happened once or an audit finding (18.09)."""
import sys, re
sys.path.insert(0, r'D:\TQMod\tools')   # development only; the exe bundles these

from arz_lazy import LazyArz
import build_companions as B

BS = chr(92)


def v(r, n):
    for vn, vt, vals in r['vars']:
        if vn == n:
            return vals, vt
    return [], None


def g(r, n, d=''):
    vals, _ = v(r, n)
    return vals[0] if vals else d


def key(x):
    return x.lower().replace('/', BS)




def base_summary(base_arz):
    """what the checks need from the untouched database - value types per field name and the electrum orb loot
    records - cached once per base (loading the whole base again cost ~40 s per build)"""
    import os, pickle, collections, paths
    st = os.stat(base_arz)
    cache = os.path.join(paths.data_dir(), 'cache', 'summary_%d_%d.pickle' % (st.st_size, int(st.st_mtime)))
    if os.path.exists(cache):
        try:
            with open(cache, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    vt_of = collections.defaultdict(collections.Counter)
    orb_loot = {}
    for k, r in LazyArz.load(base_arz).records.stream():     # one pass, nothing kept in memory
        for vn, vt, vals in r['vars']:
            vt_of[vn][vt] += 1
        if 'electrumorbs' in k and k.endswith('_loot.dbr'):
            orb_loot[k] = r
    out = {'vt_of': {k: dict(c) for k, c in vt_of.items()}, 'orb_loot': orb_loot}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    import glob
    for old in glob.glob(os.path.join(os.path.dirname(cache), 'summary_*.pickle')):   # only the current base counts
        try:
            os.remove(old)
        except OSError:
            pass
    with open(cache, 'wb') as f:
        pickle.dump(out, f, 4)
    return out


def check(build, base_arz, log=print):
    """-> list of problems (empty = ALL CHECKS PASSED). build = built database path or its records dict,
    base_arz = the untouched game database."""
    import collections
    R = LazyArz.load(build).records if isinstance(build, str) else build
    NS = B.NS
    bad = []
    summary = base_summary(base_arz)
    keys = list(R)
    if len(keys) != len(set(keys)):
        bad.append('%d duplicate record entries in the database' % (len(keys) - len(set(keys))))
    mine = {k: R[k] for k in keys if k.startswith(NS)}
    # 1. names lowercase, every .dbr reference resolves (the game looks up lowercased paths)
    for k, r in mine.items():
        if r['name'] != r['name'].lower():
            bad.append('uppercase record name ' + r['name'])
        for vn, vt, vals in r['vars']:
            for x in vals:
                if isinstance(x, str) and x.lower().endswith('.dbr') and key(x) not in R:
                    bad.append('%s: %s -> missing %s' % (k.split(BS)[-1], vn, x))
    pets = {k: r for k, r in mine.items() if k.endswith('_pet.dbr')}
    if not pets:
        log('  no companions yet (a hero needs level 20 and a mastery) - installing the base only')
    for k, r in pets.items():
        leaf = k.split(BS)[-1]
        # 2. bools stored as bool, gear/skills from own lists
        # Class Pet = the pet panel (health/mana, stance, dismiss); never drops its gear
        if g(r, 'Class') != 'Pet' or not g(r, 'templateName').lower().endswith('pet.tpl'):
            bad.append('%s: Class %s / %s - the pet panel needs Class Pet' % (leaf, g(r, 'Class'), g(r, 'templateName')))
        # 19.09: without these (all 14 vanilla permanent pets have them) no pet panel and no health even on hover
        if g(r, 'showStatusWidgetWhenPet') != 1 or not g(r, 'StatusIcon') or not g(r, 'StatusIconRed'):
            bad.append('%s: pet panel fields missing (showStatusWidgetWhenPet/StatusIcon)' % leaf)
        if not (g(r, 'mediumRangeMin') and g(r, 'longRangeMin') and g(r, 'actorRadius')):
            bad.append('%s: AI range classes / actorRadius missing' % leaf)
        if g(r, 'distressCallGroup'):
            bad.append('%s: distressCallGroup %s left from the doppel' % (leaf, g(r, 'distressCallGroup')))
        vals, vt = v(r, 'dropItems')
        if vals != [0] or vt != 3:
            bad.append('%s: dropItems=%s type %s (want 0 as bool)' % (leaf, vals, vt))
        # 3. gender profile for gendered armor meshes
        if g(r, 'characterGenderProfile') not in ('Male', 'Female'):
            bad.append('%s: characterGenderProfile missing' % leaf)
        # 4. skills: AI fields only name skills the pet owns; modifiers right after a normal skill
        skills = [key(g(r, 'skillName%d' % i)) for i in range(1, 34)]
        own = {s for s in skills if s}
        for vn, vt, vals in r['vars']:
            if B.AI_FIELDS.match(vn) and vn.endswith('SkillName') and vals and vals[0]:
                if key(vals[0]) not in own:
                    bad.append('%s: %s=%s is not in the skill list (AI would skip it)' % (leaf, vn, vals[0].split(BS)[-1]))
        last = None
        for i, s in enumerate(skills, 1):
            if not s:
                continue
            c = g(R[s], 'Class')
            if B.MOD_CLASS.search(c):
                if last is None:
                    bad.append('%s: modifier %s in slot %d has no parent before it' % (leaf, s.split(BS)[-1], i))
            elif c != 'Skill_Mastery':
                last = s
        n = len(own)
        if not any(g(r, f) for f in ('attackSkillName', 'specialAttackSkillName', 'initialSkillName')):
            log('  note: %s has no active skill the AI can use - it fights with weapon attacks only' % leaf)
        # 5. old doppel wiring gone
        for f in ('specialAttackSkillName', 'specialAttack2SkillName'):
            if 'distortreality' in g(r, f).lower():
                bad.append('%s: vanilla doppel wiring left in %s' % (leaf, f))
        # 6. gear: every slot resolves to an item or a table that has a real bellSlope
        for slot in ('Head', 'Torso', 'LowerBody', 'Forearm', 'Finger1', 'Finger2', 'RightHand', 'LeftHand'):
            tabs, _ = v(r, 'loot%sItem1' % slot)
            for t in set(x for x in tabs if x):
                tr = R.get(key(t))
                if tr is None:
                    continue
                if g(tr, 'Class') == 'LootItemTable_DynWeight':
                    bell, _ = v(tr, 'bellSlope')
                    if not bell or min(bell) <= 0:
                        bad.append('%s: %s table %s has bellSlope %s' % (leaf, slot, t.split(BS)[-1], bell))
                    it = R.get(key(g(tr, 'itemNames')))
                    lvl = int(g(it, 'itemLevel', 0) or 0) if it else -1
                    lo, hi = int(g(tr, 'minItemLevelEquation', '0')), int(g(tr, 'maxItemLevelEquation', '0'))
                    if not lo <= lvl <= hi:
                        bad.append('%s: %s item level %d outside table window %d..%d' % (leaf, slot, lvl, lo, hi))
                elif not g(tr, 'Class').startswith(('Weapon', 'Armor')):
                    bad.append('%s: %s points at %s (%s)' % (leaf, slot, t.split(BS)[-1], g(tr, 'Class')))
            if tabs and v(r, 'chanceToEquip%sItem1' % slot)[0] != [100]:
                bad.append('%s: chanceToEquip%sItem1 not scalar 100' % (leaf, slot))
        log('%s: %d skills, AI: attack=%s initial=%s buffSelf=%s special=%s, gender %s, controller %s' % (
            leaf, n, g(r, 'attackSkillName').split(BS)[-1], g(r, 'initialSkillName').split(BS)[-1],
            g(r, 'buffSelfSkillName').split(BS)[-1],
            [g(r, 'specialAttack%sSkillName' % ('' if i == 1 else i)).split(BS)[-1] for i in range(1, 6)
             if g(r, 'specialAttack%sSkillName' % ('' if i == 1 else i))],
            g(r, 'characterGenderProfile'), g(r, 'controller').split(BS)[-1]))
    # 7b. shown level = save level on every difficulty (+5 Epic / +12 Legendary added by the game), fast controller
    gap = [int(x) for x in v(R[key(B.GAP_SRC)], 'monsterLevelGapFixer')[0]]
    for k, r in pets.items():
        lv, _ = v(r, 'charLevel')
        # Class Pet gets no difficulty level gap (tested 19.09): the save's level on every difficulty
        if len(lv) != 3 or len(set(lv)) != 1:
            bad.append('%s: charLevel %s is not the same on every difficulty' % (k.split(BS)[-1], lv))
        for ctl, want_map in (('controller', B.FAST_CONTROLLER), ('controllerAggressive', B.AGGR_CONTROLLER)):
            c = R.get(key(g(r, ctl)))
            for f, want in want_map.items():
                if c is None or abs(float(g(c, f, -1)) - want) > 1e-3:
                    bad.append('%s: %s %s=%s, want %s' % (k.split(BS)[-1], ctl, f, g(c, f) if c else None, want))
    # 7g. electrum orbs: legendary ones give exactly ORB_CHANCE % of one eidolon shard, others none,
    #     and every vanilla entry keeps its absolute probability (chance * weight / total weight)
    import orb_odds
    vanR = summary['orb_loot']
    live_rel = frozenset(k for k in mine if k.endswith('_relic.dbr') and k.split(BS)[-1][:-len('_relic.dbr')] in
                         {p.split(BS)[-1][:-len('_pet.dbr')] for p in pets})
    po = orb_odds.odds(R, live_rel)
    for name, price, t in orb_odds.orbs(R):
        e = po(t)
        want = B.ORB_CHANCE / 100.0 if (B.ORB_TIER.strip('_') in name.lower() and live_rel) else 0.0
        if abs(e - want) > 2e-4:
            bad.append('orb %s: eidolon shard odds %.4f, want %.4f' % (name, e, want))
        nf, of = orb_odds.fields(R[t]), orb_odds.fields(vanR[t])
        for s_ in range(1, 7):
            ch_n, ch_o = float((nf.get('loot%dChance' % s_) or [0])[0]), float((of.get('loot%dChance' % s_) or [0])[0])
            Wn = sum(float((nf.get('loot%dWeight%d' % (s_, j)) or [0])[0]) for j in range(1, 40))
            Wo = sum(float((of.get('loot%dWeight%d' % (s_, j)) or [0])[0]) for j in range(1, 40))
            for j in range(1, 40):
                x = (of.get('loot%dName%d' % (s_, j)) or [''])[0]
                if not x:
                    continue
                pn = ch_n * float((nf.get('loot%dWeight%d' % (s_, j)) or [0])[0]) / Wn if Wn else 0
                po_ = ch_o * float((of.get('loot%dWeight%d' % (s_, j)) or [0])[0]) / Wo if Wo else 0
                if abs(pn - po_) > 1e-6:
                    bad.append('orb %s slot %d: vanilla entry %s odds %.6f -> %.6f' % (name, s_, x.split(BS)[-1], po_, pn))
    log('orbs: legendary %.1f%% eidolon shard, vanilla entries unchanged' % B.ORB_CHANCE)
    # 7c. relic chain: relic -> bonus table -> affix -> itemSkillName -> summon skill -> spawnObjects -> pet
    live_cids = {k.split(BS)[-1][:-len('_pet.dbr')] for k in pets}
    relics = [k for k in mine if k.endswith('_relic.dbr') and k.split(BS)[-1][:-len('_relic.dbr')] in live_cids]
    if len(relics) != len(pets):
        bad.append('relics %d vs pets %d' % (len(relics), len(pets)))
    for k in relics:
        r = R[k]
        leaf = k.split(BS)[-1]
        # bonus is rolled only when adding shards completes the relic -> at least 2 shards; rings only
        if g(r, 'completedRelicLevel') != B.RELIC_SHARDS or B.RELIC_SHARDS < 2 or \
                any(g(r, q) != (1 if q in B.RELIC_FITS else 0) for q in B.RELIC_SLOTS) or v(r, 'ring')[1] != 3:
            bad.append('%s: shards %s / fit flags wrong (want %d shards, only %s, bool)' % (
                leaf, g(r, 'completedRelicLevel'), B.RELIC_SHARDS, sorted(B.RELIC_FITS)))
        t = R.get(key(g(r, 'bonusTableName')))
        bon = R.get(key(g(t, 'randomizerName1'))) if t else None
        sk = R.get(key(g(bon, 'itemSkillName'))) if bon else None
        pet = key((v(sk, 'spawnObjects')[0] or [''])[0]) if sk else ''
        if not (bon and g(bon, 'Class') == 'LootRandomizer' and sk and g(sk, 'Class') == 'Skill_SpawnPet' and pet in pets
                and pet.split(BS)[-1][:-8] == leaf[:-10]):
            bad.append('%s: broken chain relic->bonus->skill->pet (%s)' % (leaf, pet))
    # 7d. relics reachable from the electrum orbs of every casino merchant
    casino = [R[k] for k in R if 'casino' in k and g(R[k], 'Class') == 'NpcCasinoMerchant']
    seen, frontier = set(), [key(x) for r in casino for x in v(r, 'altOrbs')[0] if x]
    for depth in range(10):
        nxt = []
        for x in frontier:
            if x in seen or x not in R:
                continue
            if not orb_odds.lootish(x):          # an item or relic: reachable, but nothing to expand
                seen.add(x)
                continue
            seen.add(x)
            for vn, vt, vals in R[x]['vars']:
                nxt += [key(y) for y in vals if isinstance(y, str) and y.lower().endswith('.dbr')]
        frontier = nxt
    for k in relics:
        if k not in seen:
            bad.append('%s: not reachable from electrum orbs (%d casino merchants)' % (k.split(BS)[-1], len(casino)))
    log('relics: %d, reachable from electrum orbs: %d' % (len(relics), sum(1 for k in relics if k in seen)))
    # 7e. every field stored with the value type vanilla uses for it (18.09: relic flags written as int read as 0 by the
    #     bool getter -> relic fitted nothing). Compared with the most common type of that field name in vanilla.
    import collections
    vt_of = {k: collections.Counter(c) for k, c in summary['vt_of'].items()}
    mism = collections.Counter()
    for k, r in mine.items():
        for vn, vt, vals in r['vars']:
            if vn in vt_of:
                want = vt_of[vn].most_common(1)[0][0]
                ok = vt == want or {vt, want} <= {0, 1} and vt_of[vn][vt] > 0   # int/real mixes exist in vanilla
                if not ok:
                    mism[(vn, vt, want)] += 1
    for (vn, vt, want), n in sorted(mism.items()):
        bad.append('field %s stored as type %d in %d record(s), vanilla uses %d' % (vn, vt, n, want))
    # 7f. tombstones of deleted characters: no skill, not sold, not dropped
    reg = B.load_registry()[0]
    live = {k.split(BS)[-1][:-len('_pet.dbr')] for k in pets}
    # 7h. every hero the saves still refer to (eidolons, rings, summons) must still have its records
    for cid in B.referenced_cids():
        for part in ('relic', 'relic_bonus', 'summon', 'ring'):
            if NS + cid + '_' + part + '.dbr' not in R:
                bad.append('saves refer to %s%s_%s.dbr but it is not built' % (NS, cid, part))
    # where eidolons/rings could be offered: our own tables and the electrum orb loot (nothing else is modified)
    cand = list(mine) + [k for k in R if 'electrumorbs' in k]
    shop_like = [R[k] for k in cand if any(isinstance(x, str) and key(x).startswith(NS) and key(x).endswith(('_relic.dbr', '_ring.dbr'))
                                           for vn, vt, vals in R[k]['vars'] if vn.startswith('lootName') for x in vals)]
    offered = {key(x) for r in shop_like for vn, vt, vals in r['vars'] if vn.startswith('lootName') for x in vals if isinstance(x, str)}
    for cid, name in reg.items():
        if cid in live:
            continue
        rel = R.get(NS + cid + '_relic.dbr')
        bon = R.get(key(g(R.get(key(g(rel, 'bonusTableName'))), 'randomizerName1'))) if rel else None
        if rel is None or bon is None or g(bon, 'itemSkillName'):
            bad.append('tombstone %s: relic missing or still grants a skill' % name)
        if any(o.startswith(NS + cid + '_') for o in offered):
            bad.append('tombstone %s: still sold or dropped' % name)
    log('registry: %d companions, %d live, %d tombstones' % (len(reg), len(live), len([c for c in reg if c not in live])))
    # 7. summon skills
    for k, r in mine.items():
        if k.endswith('_summon.dbr') and k.split(BS)[-1][:-len('_summon.dbr')] in live_cids:
            if v(r, 'spawnObjectsTimeToLive')[0] or g(r, 'petLimit') != 1 or not g(r, 'skillUpBitmapName'):
                bad.append('%s: summon fields (TTL %s, petLimit %s, icon %s)' % (k.split(BS)[-1], v(r, 'spawnObjectsTimeToLive')[0],
                                                                                g(r, 'petLimit'), g(r, 'skillUpBitmapName')))
    return bad


if __name__ == '__main__':
    import os, paths
    game = paths.find_game()
    base = os.path.join(game, 'Database', 'database.arz' + paths.BASE_SUFFIX)
    if not os.path.exists(base):
        base = os.path.join(game, 'Database', 'database.arz.tqmod-backup')
    problems = check(os.path.join(B.OUT, 'database.arz'), base)
    print('\n'.join(problems) if problems else 'ALL CHECKS PASSED')
    sys.exit(1 if problems else 0)
