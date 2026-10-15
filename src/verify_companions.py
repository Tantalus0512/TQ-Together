# -*- coding: utf-8 -*-
"""Static checks of build\\database.arz (companions). Run after every build: must print ALL CHECKS PASSED.
Each check = a failure that already happened once or an audit finding (18.09)."""
import sys, re, collections
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


# the doppelganger pet's own monster skills (records\xpack2\skills\item skills\pet\doppelgangerpet.dbr skillName8/15-17)
DOPPEL_ONLY = {key(x) for x in (
    'records\\xpack2\\skills\\monster skills\\passive_buffs\\doppelganger_reflect.dbr',
    'Records\\XPack\\Skills\\MonsterSkills\\Passive\\ElementalResistance_10xLevel.dbr',
    'records\\skills\\boss skills\\hero_conversionimmunity.dbr',
    'records\\skills\\monster skills\\defense\\resist_ghost.dbr')}




def base_summary(base_arz):
    """what the checks need from the untouched database - value types per field name, the electrum orb loot
    records and (1.3.1) the references that are already broken in the game itself - cached once per base (loading
    the whole base again cost ~40 s per build)"""
    import os, pickle, collections, paths
    st = os.stat(base_arz)
    cache = os.path.join(paths.data_dir(), 'cache', 'summary2_%d_%d.pickle' % (st.st_size, int(st.st_mtime)))
    if os.path.exists(cache):
        try:
            with open(cache, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    vt_of = collections.defaultdict(collections.Counter)
    orb_loot = {}
    names, refs = set(), set()
    for k, r in LazyArz.load(base_arz).records.stream():     # one pass, nothing kept in memory
        names.add(k)
        for vn, vt, vals in r['vars']:
            vt_of[vn][vt] += 1
            if vt == 2:
                refs.update(key(x) for x in vals if isinstance(x, str) and x.lower().endswith('.dbr'))
        if 'electrumorbs' in k and k.endswith('_loot.dbr'):
            orb_loot[k] = r
    # e.g. Hou Yi's bow: dropSoundWater -> a sound record the game never shipped; the game lives with it, and a
    # baked copy of the bow carries the same reference
    out = {'vt_of': {k: dict(c) for k, c in vt_of.items()}, 'orb_loot': orb_loot, 'broken_in_game': refs - names}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    import glob
    for old in glob.glob(os.path.join(os.path.dirname(cache), 'summary*.pickle')):    # only the current base counts
        try:
            os.remove(old)
        except OSError:
            pass
    with open(cache, 'wb') as f:
        pickle.dump(out, f, 4)
    return out


def getattr_tables(r):
    """the `tables` list of a container record (strings, empty ones dropped)"""
    vals, _ = v(r, 'tables') if r is not None else ([], None)
    return [x for x in vals if isinstance(x, str) and x]


def string_table(path):
    """1.3.4, the written database file as the engine reads it: Engine.dll 0x102906d0 gives a string table entry an id
    only if its bytes are new and finds records by that id, so a single repeated entry makes every record after it
    unreachable (25.09: Эйлин's eidolon vanished from a ring because 'TQMod companion relic: ?????' was also Темун's)"""
    import struct
    raw = open(path, 'rb').read()
    st_start = struct.unpack_from('<I', raw, 16)[0]        # header <2H5i: magic, version, rt start/size/count, st start
    n = struct.unpack_from('<i', raw, st_start)[0]
    p, seen, dups = st_start + 4, set(), []
    for i in range(n):
        l = struct.unpack_from('<i', raw, p)[0]
        s = raw[p + 4:p + 4 + l]
        p += 4 + l
        if s in seen:
            dups.append((i, s))
        seen.add(s)
    return ['database string table repeats %r at entry %d - the game would not find the records after it' % (s[:60], i)
            for i, s in dups[:5]]


def stat_values(rec, idx=0, only=None):
    """{attribute value field: number} of a record - the summable part (no chance/duration/flags, no names);
    augment levels without their slot number (a level may move to the other slot); 1.3.2: a level whose slot names no
    skill / mastery counts as nothing - the game gives nothing for it (vanilla Archer's Prowess ring: two such levels),
    and the builder may put a real bonus into that empty slot"""
    out = collections.Counter()
    for f, (vt, val) in B.stat_fields(rec, idx).items():
        if vt not in (0, 1) or (only is not None and f not in only):
            continue
        if B.split_role(f)[1] in B.SHAPE_ROLES or f == 'itemSkillLevel':
            continue
        m = B.AUGMENT.match(f)
        if m and m.group(2) == 'Level' and not g(rec, 'augment%sName%s' % (m.group(1), m.group(3))):
            continue
        out[re.sub(r'\d$', '', f) if B.AUGMENT.match(f) else f.lower()] += float(val)
    return out


def skill_speed(R, skill, depth=0):
    """{kind: highest % over the levels} a BUFF granted by an item (and the buffs it casts) adds to Attack/SpellCast/Run
    speed; attacks (charges move fast only while striking) do not count"""
    out = collections.Counter()
    r = R.get(key(skill)) if skill else None
    if r is None or depth > 3 or depth == 0 and not re.search(r'Buff|PassiveOn', g(r, 'Class')) or B.enemy_debuff(r):
        return out
    arr = {vn: vals for vn, vt, vals in r['vars']}
    total = arr.get('characterTotalSpeedModifier') or [0]
    for kind in B.SPEED_KINDS:
        own_ = arr.get('character%sSpeedModifier' % kind) or [0]
        out[kind] += max(float(own_[min(i, len(own_) - 1)]) + float(total[min(i, len(total) - 1)])
                         for i in range(max(len(own_), len(total))))
    for kind, (f, c) in B.DODGE_KINDS.items():
        out[kind] += max([float(x) for x in (arr.get(f) or [0])])
    for vn in ('buffSkillName', 'skillCastName'):
        if arr.get(vn) and arr[vn][0]:
            out.update(skill_speed(R, arr[vn][0], depth + 1))
    return out


def check_gear(R, gear, log):
    """7i. baked gear (1.0.3): for every pet, each attribute summed over the records it wears = the hero's worn records
    + every affix / relic (at its shard count) / bonus / amulet / artifact baked in - what the report lists as not
    transferred. Summed straight from the source records, independent of how the builder placed them. And a baked
    copy differs from the worn item only in attributes: look, class, requirements stay the item's own."""
    bad = []
    for pk, led in sorted(gear.items()):
        pet = R.get(pk)
        leaf = pk.split(BS)[-1]
        if pet is None:
            bad.append('%s: pet record missing' % leaf)
            continue
        want, got = collections.Counter(), collections.Counter()
        for s, name in led['slots'].items():
            worn = led['worn'][s]
            if key((v(pet, 'loot%sItem1' % s)[0] or [''])[0]) != key(worn):
                bad.append('%s: %s does not wear %s' % (leaf, s, worn.split(BS)[-1]))
            orig, baked = R.get(key(name)), R.get(key(worn))
            if orig is None or baked is None:
                bad.append('%s: %s record missing (%s / %s)' % (leaf, s, name, worn))
                continue
            want.update(stat_values(orig))
            got.update(stat_values(baked))
            if baked is not orig:
                a = {vn: vals for vn, vt, vals in orig['vars'] if not B.STAT_FIELD.match(vn) and vn != 'FileDescription'}
                b = {vn: vals for vn, vt, vals in baked['vars'] if not B.STAT_FIELD.match(vn) and vn != 'FileDescription'}
                if a != b:
                    bad.append('%s: baked %s changed non-attribute fields %s' % (
                        leaf, s, sorted(set(a) ^ set(b) | {k for k in set(a) & set(b) if a[k] != b[k]})[:6]))
        for rn, idx in led['sources']:
            want.update(stat_values(R[key(rn)], idx))
        for rn, idx, fields in led['lost']:
            if key(rn) in R:
                want.subtract(stat_values(R[key(rn)], idx, set(fields)))
        for f, d in led.get('adjust', {}).items():       # trimmed down to the hero's speed caps
            want[f.lower()] += d
        # 1.0.4: base speeds are the hero body's; gear speed bonuses never above the hero's caps
        body = R.get(key(B.PC['female' if g(pet, 'characterGenderProfile') == 'Female' else 'male']))
        ge = R.get(key(B.GAP_SRC))
        par = led.get('attack')
        for f in B.BASE_SPEEDS:
            want_f = float(g(body, f, -1)) if body is not None else -1
            if f == 'characterAttackSpeed' and par:
                # 1.0.6: body scaled to the hero's cap, the difference on the weapon(s): body + weapon unchanged
                want_f *= float(g(ge, 'playerAttackSpeedCapMax')) / float(g(ge, 'monsterAttackSpeedCapMax'))
                for s in par['slots']:
                    d = float(g(R[key(led['worn'][s])], 'characterBaseAttackSpeed', 0) or 0) - \
                        float(g(R[key(led['slots'][s])], 'characterBaseAttackSpeed', 0) or 0)
                    if abs(d - (float(g(body, f)) - want_f)) > 1e-4:
                        bad.append('%s: %s weapon base speed +%.4f, body moved %.4f' % (leaf, s, d, float(g(body, f)) - want_f))
            if body is None or abs(float(g(pet, f, 0) or 0) - want_f) > 1e-4:
                bad.append('%s: %s %s, want %s (hero body %s)' % (leaf, f, g(pet, f), want_f, g(body, f) if body else None))
        # 1.2.0: no attribute of the doppelganger record left: every one is the hero body's, except the base values we
        # set from the save (attributes, life, mana) and the speeds checked above
        ours = {'characterStrength', 'characterDexterity', 'characterIntelligence', 'characterLife', 'characterMana'} | \
            set(B.BASE_SPEEDS)
        pv = {vn: vals for vn, vt, vals in pet['vars'] if vt in (0, 1)}
        bv = {vn: vals for vn, vt, vals in (body['vars'] if body else []) if vt in (0, 1)}
        for f in sorted(set(pv) | set(bv)):
            if (re.match(r'^(character|defensive|offensive|retaliation)', f) and f not in ours
                    or f in ('numAttackSlots', 'numDefenseSlots')) and pv.get(f) != bv.get(f):
                if any(x not in (0, 0.0) for x in (pv.get(f) or []) + (bv.get(f) or [])):
                    bad.append('%s: %s = %s, the hero body has %s' % (leaf, f, pv.get(f), bv.get(f)))
        if g(pet, 'characterRacialProfile'):
            bad.append('%s: race %s left from the doppelganger' % (leaf, g(pet, 'characterRacialProfile')))
        # 1.0.6: the companion's own passive cancels the pet difficulty bonus exactly, one level per difficulty
        own = [(i, g(pet, 'skillName%d' % i)) for i in range(1, 34) if key(g(pet, 'skillName%d' % i)).endswith(
            leaf[:-len('_pet.dbr')] + '_passive.dbr')]
        if len(own) != 1 or v(pet, 'skillLevel%d' % own[0][0])[0] != [1, 2, 3]:
            bad.append('%s: own passive missing or not on levels [1,2,3] (%s)' % (leaf, own))
        else:
            pas = R.get(key(own[0][1]))
            pak = R.get(key(g(ge, 'petAttributePak')))
            parts = led.get('passive') or {}
            # 1.2.0: the passive = quest rewards + pak cancel + owner pet-bonus cancel + resist penalty/trim; the pak
            # part must cancel the WHOLE pet pak (read here from the database), per difficulty
            for vn, vt, vals in (pak['vars'] if pak else []):
                if vt in (0, 1) and B.STAT_FIELD.match(vn) and vals and any(vals):
                    part = (parts.get('pak') or {}).get(vn, [0, 0, 0])
                    if any(abs(part[d] + float(vals[min(6 * d, len(vals) - 1)])) > 1e-4 for d in range(3)):
                        bad.append('%s: own passive does not cancel the pet pak %s (%s vs %s)' % (leaf, vn, part, vals))
            fields = set()
            for p in parts.values():
                fields |= set(p)
            for f in fields:
                want_p = [sum((parts[c].get(f) or [0, 0, 0])[d] for c in parts) for d in range(3)]
                have_p = [float(x) for x in (v(pas, f)[0] or [0, 0, 0])]
                if any(abs(have_p[min(d, len(have_p) - 1)] - want_p[d]) > 1.0 + 1e-6 for d in range(3)):
                    bad.append('%s: own passive %s %s, its parts add up to %s' % (leaf, f, have_p, want_p))
        # 1.0.6: auto-cast attacks on the gear: vanilla-proven class, 'on attack', and not ALSO in the skill list
        listed = {key(g(pet, 'skillName%d' % i)) for i in range(1, 34) if g(pet, 'skillName%d' % i)}
        # 1.0.7: no taunt anywhere (owner: enemies must not be pulled off the hero); the chain is a single link from a
        # wired special, whose delay covers the chained skill's cooldown
        for s_ in listed | {key(g(R.get(key(w)) or {'vars': []}, 'itemSkillName')) for w in led['worn'].values()}:
            r_ = R.get(s_)
            if r_ is not None and (float(g(r_, 'offensiveTauntMin', 0) or 0) or float(g(r_, 'offensiveTauntMax', 0) or 0)):
                bad.append('%s: taunt skill %s' % (leaf, s_.split(BS)[-1]))
        # 1.0.9: party burden (TQTogether.ini PartyBurden): the initial skill, an ally aura of -pct % total damage
        pct = B.party_burden()
        cid_ = leaf[:-len('_pet.dbr')]
        if pct:
            aura = R.get(key(g(pet, 'initialSkillName')))
            buff = R.get(key(g(aura, 'buffSkillName'))) if aura else None
            if not (aura and key(aura['name']).endswith(cid_ + '_burden.dbr') and buff and
                    float(g(buff, 'offensiveTotalDamageModifier', 0) or 0) == -pct and not g(buff, 'characterManaLimitReserve')
                    and key(aura['name']) in listed):
                bad.append('%s: party burden %d%% is not the initial skill / wrong values' % (leaf, pct))
        elif any(key(x).endswith('_burden.dbr') for x in listed):
            bad.append('%s: party burden in the skill list though PartyBurden is 0' % leaf)
        ci, cn = g(pet, 'chainInitialSkill'), g(pet, 'chainNextSkill')
        if ci or cn:
            slots = [p for p in ('specialAttack', 'specialAttack2', 'specialAttack3', 'specialAttack4', 'specialAttack5')
                     if key(g(pet, p + 'SkillName')) == key(ci)]
            nr = R.get(key(cn))
            cd = float((v(nr, 'skillCooldownTime')[0] or [0])[-1]) if nr else 0
            if not (slots and key(cn) in listed and key(cn) != key(ci) and
                    float(g(pet, slots[0] + 'Delay', 0) or 0) >= cd - 1e-6):
                bad.append('%s: chain %s -> %s is not a single link from a special covering the cooldown %.0f s' % (
                    leaf, ci, cn, cd))
        # 1.1.7: a creature never registers item auto-casts (Game.dll init order) - no worn record may carry one; every
        # item skill converted from one is in the skill list, and an area proc (a toggle) sits in a buff-self slot
        for s, worn in led['worn'].items():
            wr = R.get(key(worn))
            if wr is not None and g(wr, 'itemSkillAutoController'):
                bad.append('%s: %s still carries the dead item auto-cast %s' % (leaf, s, g(wr, 'itemSkillName')))
        toggles = {key(g(pet, f)) for f in ('initialSkillName', 'buffSelfSkillName', 'buffSelf2SkillName',
                                            'buffSelf3SkillName') if g(pet, f)}
        for nm, lv, toggle, what in led.get('procs', []):
            pr = R.get(key(nm))
            if pr is None or key(nm) not in listed or (toggle and key(nm) not in toggles):
                bad.append('%s: item proc %s (%s) missing from the skill list / toggle slot' % (leaf, nm.split(BS)[-1], what))
            elif 'PassiveOn' in g(pr, 'Class') or g(pr, 'Class') == 'Skill_OnHitAttackRadius':
                if g(pr, 'Class') != 'Skill_PassiveOnLifeBuffSelf' and not float(g(pr, 'onHitActivationChance', 0) or 0):
                    bad.append('%s: item proc %s has no activation chance' % (leaf, nm.split(BS)[-1]))
                if g(pr, 'characterManaLimitReserve'):
                    bad.append('%s: item proc %s reserves mana' % (leaf, nm.split(BS)[-1]))
        buffs = collections.Counter()          # 1.0.5: speed of buffs granted by the worn items, at most the room left
        for worn in led['worn'].values():
            buffs.update(skill_speed(R, g(R.get(key(worn)) or {'vars': []}, 'itemSkillName')))
        for kind, cap in B.SPEED_KINDS.items():
            s = got['character%sspeedmodifier' % kind.lower()] + got['charactertotalspeedmodifier']
            if s + buffs[kind] > float(g(ge, cap)) - 100 + 1e-3:
                bad.append('%s: gear %s speed %+.0f%% + item buffs %+.0f%% above the hero cap %s' % (
                    leaf, kind, s, buffs[kind], g(ge, cap)))
        for kind, (f, cap) in B.DODGE_KINDS.items():             # 1.1.3
            s = got[f.lower()]
            if s + buffs[kind] > float(g(ge, cap)) + 1e-3:
                bad.append('%s: gear %s %.0f%% + item buffs %.0f%% above the hero cap %s' % (leaf, f, s, buffs[kind], g(ge, cap)))
        # 1.1.3: always-on resistances on every difficulty (difficulty penalty in the own passive) <= the hero's cap
        rcap = float(g(ge, 'playerDefenseCap'))
        for d in range(3):
            res = collections.Counter()

            def add(r_, lv, depth=0):
                if r_ is None or depth > 3:
                    return
                dd = {vn: vals for vn, vt, vals in r_['vars']}
                for f in B.RESISTS + ('defensiveElementalResistance',):
                    if dd.get(f) and not float((dd.get(f + 'Chance') or [0])[0] or 0):
                        val = float(dd[f][min(max(lv, 1), len(dd[f])) - 1])
                        for t in (B.ELEMENTAL if f == 'defensiveElementalResistance' else (f,)):
                            res[t] += val
                if dd.get('buffSkillName') and dd['buffSkillName'][0]:
                    add(R.get(key(dd['buffSkillName'][0])), lv, depth + 1)
            for w in led['worn'].values():
                add(R.get(key(w)), 1)
            for i in range(1, 34):
                sk = g(pet, 'skillName%d' % i)
                r_ = R.get(key(sk)) if sk else None
                if r_ is not None and re.search(r'Passive|Toggled|Modifier', g(r_, 'Class')) and 'PassiveOn' not in g(r_, 'Class'):
                    lv = v(pet, 'skillLevel%d' % i)[0] or [1]
                    add(r_, int(lv[min(d, len(lv) - 1)]))
            over = {t: x for t, x in res.items() if x > rcap + 1e-3}
            if over:
                bad.append('%s: difficulty %d resistances above the hero cap %g: %s' % (leaf, d, rcap, over))
        for f in sorted(set(want) | set(got)):
            if abs(want[f] - got[f]) > 1e-3 * max(1.0, abs(want[f])):
                bad.append('%s: gear %s = %g, sources give %g' % (leaf, f, got[f], want[f]))
        log('%s: gear %d slots, %d sources baked in, %d not transferred' % (
            leaf, len(led['slots']), len(led['sources']), len(led['lost'])))
    return bad


def check(build, base_arz, log=print, touched=(), gear=None):
    """-> list of problems (empty = ALL CHECKS PASSED). build = built database path or its records dict,
    base_arz = the untouched game database, gear = Builder.gear_ledger (the 7i check runs only when given)."""
    import collections
    R = LazyArz.load(build).records if isinstance(build, str) else build
    NS = B.NS
    bad = []
    summary = base_summary(base_arz)
    keys = list(R)
    if len(keys) != len(set(keys)):
        bad.append('%d duplicate record entries in the database' % (len(keys) - len(set(keys))))
    mine = {k: R[k] for k in keys if k.startswith(NS)}
    if B.MARKER not in R:
        bad.append('marker record %s missing: the installer would not recognise the installed database' % B.MARKER)
    # 1. names lowercase, every .dbr reference resolves (the game looks up lowercased paths) - except a reference that
    #    is broken in the game's own database too (copied from a vanilla record, the game already lives with it)
    broken = summary['broken_in_game']
    inherited = set()
    for k, r in mine.items():
        if r['name'] != r['name'].lower():
            bad.append('uppercase record name ' + r['name'])
        for vn, vt, vals in r['vars']:
            for x in vals:
                if isinstance(x, str) and x.lower().endswith('.dbr') and key(x) not in R:
                    if key(x) in broken:
                        inherited.add(key(x))
                    else:
                        bad.append('%s: %s -> missing %s' % (k.split(BS)[-1], vn, x))
    if inherited:
        log('  %d reference(s) broken in the game itself, kept as they are: %s' % (
            len(inherited), ', '.join(sorted(x.split(BS)[-1] for x in inherited))))
    # 1b. records created or changed by tweaks (tweaks.py): names lowercase, references resolve, vanilla field types
    vt_base = {k: collections.Counter(c) for k, c in summary['vt_of'].items()}
    for k in sorted(touched):
        r = R.get(k)
        if r is None:
            bad.append('tweak: record %s is missing after the build' % k)
            continue
        if r['name'] != r['name'].lower():
            bad.append('tweak: uppercase record name ' + r['name'])
        for vn, vt, vals in r['vars']:
            for x in vals:
                if isinstance(x, str) and x.lower().endswith('.dbr') and key(x) not in R and key(x) not in broken:
                    bad.append('tweak: %s: %s -> missing %s' % (k, vn, x))
            if vn in vt_base:
                want = vt_base[vn].most_common(1)[0][0]
                if not (vt == want or {vt, want} <= {0, 1} and vt_base[vn][vt] > 0):
                    bad.append('tweak: %s: field %s stored as type %d, vanilla uses %d' % (k, vn, vt, want))
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
        # 1.3.5: a healer companion heals the others only on their calls for help - they must never run out
        if not (g(r, 'distressCall', 0) and float(g(r, 'distressCallRange', 0) or 0) >= 15 and
                int(g(r, 'maxDistressCalls', 0) or 0) >= 1000 and int(g(r, 'distressCallTime', 99999) or 0) <= 5000):
            bad.append('%s: calls for help limited (distressCall %s range %s every %s ms, %s calls) - a healer companion '
                       'would not heal it' % (leaf, g(r, 'distressCall', 0), g(r, 'distressCallRange', 0),
                                             g(r, 'distressCallTime', 0), g(r, 'maxDistressCalls', 0)))
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
        # 5. old doppel wiring gone. 1.3.2: not by name - the doppel's special attacks are the Dream skills Psionic Touch
        #    and Distort Reality, which a Dream hero legitimately has (a mace moves his Distort Reality to special 2);
        #    what only the doppel has are its monster passives (4. already rejects AI fields naming unlisted skills)
        left = sorted(s.split(BS)[-1] for s in own if s in DOPPEL_ONLY)
        if left:
            bad.append('%s: vanilla doppel skills left in the skill list: %s' % (leaf, ', '.join(left)))
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
    # 7g. electrum orbs of every difficulty: one opening gives an eidolon shard with EidolonOrbChance % (1.5.0: the
    #     engine's own rules, orb_odds.per_container - 7-8 items, slot by chance / running total), and inside every
    #     slot each vanilla entry keeps chance * weight / slot weight
    import orb_odds
    from arz_lazy import LazyArz as _LA
    vanR = summary['orb_loot']
    live_rel = frozenset(k for k in mine if k.endswith('_relic.dbr') and k.split(BS)[-1][:-len('_relic.dbr')] in
                         {p.split(BS)[-1][:-len('_pet.dbr')] for p in pets})
    po = orb_odds.odds(R, live_rel)
    orb_pct, boss_pct = B.drop_chances()

    def kept(name, nf, of):
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
                    bad.append('%s slot %d: vanilla entry %s odds %.6f -> %.6f' % (name, s_, x.split(BS)[-1], po_, pn))
    for name, price, t in orb_odds.orbs(R):
        e = orb_odds.per_container(R, t, live_rel, po)
        want = orb_pct / 100.0 if live_rel else 0.0
        if abs(e - want) > 5e-3:
            bad.append('orb %s: eidolon shard per orb %.4f, want %.4f' % (name, e, want))
        kept('orb ' + name, orb_odds.fields(R[t]), orb_odds.fields(vanR[t]))
    log('orbs: %g%% eidolon shard per orb on every difficulty, vanilla entries unchanged' % orb_pct)
    # 7i. boss chests (1.5.0): every table a boss guards is our copy giving EidolonBossChance % per opening, the copy
    #     keeps the original's odds, and no other container uses the copies (ordinary chests stay vanilla)
    baseR = _LA.load(base_arz).records
    n_chests, guarded = 0, set()
    bosses = B.boss_chests(R)
    for k, r in bosses:
        orig = baseR.get(k)
        for i, t in enumerate(getattr_tables(r)):
            tk = key(t)
            if not tk.startswith(NS + 'bossloot_'):
                if live_rel and boss_pct > 0 and (g(R.get(tk) or {'vars': []}, 'templateName') or '').lower().endswith('fixeditemloot.tpl'):
                    bad.append('boss chest %s: table %s has no eidolon shard' % (k.split(BS)[-1], tk.split(BS)[-1]))
                continue
            guarded.add(tk)
            e = orb_odds.per_container(R, tk, live_rel, po)
            if abs(e - boss_pct / 100.0) > 5e-3:
                bad.append('boss chest %s: eidolon shard per opening %.4f, want %.4f' % (k.split(BS)[-1], e, boss_pct / 100.0))
            ot = getattr_tables(orig)[i] if orig is not None and i < len(getattr_tables(orig)) else ''
            if not ot or key(ot) not in baseR:
                bad.append('boss chest %s: copy %s without its original' % (k.split(BS)[-1], tk.split(BS)[-1]))
            else:
                kept('boss chest ' + k.split(BS)[-1], orb_odds.fields(R[tk]), orb_odds.fields(baseR[key(ot)]))
        n_chests += 1
    users = [k for k in R if not k.startswith(NS) and ('container' in k or 'chest' in k or 'orb' in k)
             and g(R[k], 'Class') == 'FixedItemContainer' and any(key(t).startswith(NS + 'bossloot_') for t in getattr_tables(R[k]))]
    boss_keys = {k for k, _ in bosses}
    for k in users:
        if k not in boss_keys:
            bad.append('container %s (not a boss chest) uses an eidolon boss table' % k.split(BS)[-1])
    log('boss chests: %d, %d loot tables with %g%% eidolon shard per opening, ordinary chests untouched' % (
        n_chests, len(guarded), boss_pct))
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
    if gear is not None:
        bad += check_gear(R, gear, log)
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
