# -*- coding: utf-8 -*-
"""Boss souls (1.6.0, 16.10.2026): every boss and hero monster of the game can become a companion.

A boss or a hero monster drops "Enslaved Soul: <name>" (1.6.1, owner's name; "Порабощённая душа") - a relic of
SoulBossShards (3) / SoulHeroShards (2) shards. Shards of the same soul combine like vanilla relic shards; the last
one rolls the completion bonus, which grants "Summon Enslaved Soul: <name>". A boss soul fits the AMULET only (owner 16.10);
a hero monster's soul an amulet or a ring (1.8.4, SOUL_FITS), beside the eidolons.

The summoned soul is the boss record turned into a Class Pet, the way the developers turned the boss Ylva
(loki_a_ylva_55) into the companion Ylva (x2sq23_ylva_companion): Pet.tpl, pet controllers, the pet panel; no next
stage on death, no dying skill, no music, gold or loot, no boss-only passives (GlobalProperties_*_Boss: +100 % damage
on Legendary). The pet gets the game's pet difficulty pak instead of the boss pak (Legendary: life +208 % instead of
+420 %), so a soul is weaker than the boss itself and stronger than an ordinary pet.

"A late boss must not be weak" (owner 16.10): the soul comes at the level of the hero about to be played
(tq_together.choose_hero), on every difficulty. From the boss's own Legendary level to the hero's, its mana and
attributes move along the game's own monster growth curve (research\\souls\\level_curve.py: 2129 vanilla level
variants - +2.4 %/level at Normal levels 20-40, +2.0 % at 40-60) and its skill levels by 0.165 per level (same
survey), capped by each skill's max level. Life is ONE value like a vanilla pet's: LIFE_ANCHOR (15000 for the median
boss at hero level 85) x how tough this boss is among bosses, held in a corridor (bosses x0.7..x1.5, heroes x0.4..x1:
Nessus' 1282 base life is not paper, Akhenaten's 105000 not immortal) x the same growth curve for the hero's level,
x SoulLife %. On Legendary the pet pak makes the median ~47k (1.7.1; 24k in 1.6.5, 16.6k before); the game's
strongest permanent pets have 1.9-2.7k base (~8k).
1.7.0: damage and run speed follow the hero (SoulDamage % of his character-window DPS, his own ground speed; giants
no faster than themselves in the game) - see DAMAGE_FIELDS and SPEEDUP_MAX below. 1.7.3: no animation of a soul
plays more than SoulSpeedMax (2) times faster than the boss's own, so auras on top do not turn it into mush.

Where souls drop (every vanilla item keeps its exact odds):
  - from the monster itself, a Misc loot slot: the eidolon shard's slot of 1.5.1 if there is one (shared, both odds
    exact), else an empty slot, else a vanilla slot whose chance leaves room. SoulBossChance / SoulHeroChance % per
    kill; a fight with k members dropping at the same level (Pharaoh's Honor Guard x4, Tiamat's 3 stages) gives the
    chance per FIGHT;
  - bosses that drop nothing themselves (the Aesir, Ylva, Mimir, most Eternal Embers bosses): their boss chest, found
    by its name (bosschest10_aesir_01..03 and repeat chests), SoulChestChance % per opening;
  - electrum orbs: SoulOrbChance % per orb for one soul shard of a random HERO MONSTER of the orb's region (Antiquity,
    Hades, Scandia, Atlantis, Jade Emperor, Thebes) - 1.7.9, owner: a boss's soul comes from the boss itself; only the
    bosses with no drop and no chest of their own (Baldr, the Chaos bosses) stay in the orbs. (1.6.0-1.7.8: bosses.)
Not built: a family with no possible drop source, no skills, or that cannot move.

Records: records\\tqmod\\companions\\souls\\<sid>_{soul,soulbonus,soulbonustable,soulshard,soulcall,soulpet}.dbr, sid
from the monster's name tag - stable, items in saves point at these names, so a soul once released is never removed.
Which souls are built depends on the game only, never on TQTogether.ini: Souls=0, SoulHeroes=0 or a chance of 0 stop
the DROPS, the records stay (a soul already in an amulet keeps working).
Checks: check() below, run by verify_companions.check."""
import os, re, math, glob, hashlib, collections, json      # no statistics: it imports decimal, excluded from the exe

import paths
import orb_odds
from tqlib import get1, getv, setv, delv, key_of, BS

SUB = 'souls' + BS
# 1.6.6, owner: 30 % per boss was too easy (Soulvizier's soul of Typhon: about 6 %, one needed, ~17 kills) - 15 % for
# 3 shards is ~20 boss fights, 12 % for a hero's 2 shards ~17
# 1.8.0, owner 18.10 (the orbs now give hero monster souls): "from some 20 orbs one to three, sometimes none" - 10 -> 20 %
# per orb (about 4 in 20; none in 20 about 1 % of the time)
# 1.8.2, owner 19.10: the ordinary chests of the Tartarus arenas give a soul of any boss or hero monster, 10 % per
# opening, bosses and heroes equally likely as groups (SoulTartarusChance)
DEFAULTS = (('souls', 1), ('soulheroes', 1), ('soulbossshards', 3), ('soulheroshards', 2), ('soulbosschance', 15.0),
            ('soulherochance', 12.0), ('soulorbchance', 20.0), ('soulchestchance', 15.0), ('soultartaruschance', 10.0),
            ('soullife', 100.0), ('soulmaxscale', 1.3), ('souldamage', 30.0), ('soulspeedmax', 2.0), ('soultestshop', ''))
LIMITS = {'soulbossshards': (2, 5), 'soulheroshards': (2, 5), 'soulbosschance': (0, 95), 'soulherochance': (0, 95),
          'soulorbchance': (0, 50), 'soulchestchance': (0, 95), 'soultartaruschance': (0, 50), 'soullife': (10, 1000),
          'soulmaxscale': (0.5, 3), 'souldamage': (0, 500), 'soulspeedmax': (1.0, 3.0)}
# 1.8.2: the ordinary chests the Tartarus arenas put down (proxy 01x_tartarus, "Non-Golden chest in Tartarus") - the
# Underworld's own chests are 0Nb_ / 0Nc_; the reward orb after Tartarus himself is bosschest_tartarus_0N
TARTARUS_ARENA_CHEST = re.compile(r'^0[123]x_hadeschest_(common|infreq|rare)\.dbr$')
# 1.8.4, owner 21.10: "the bosses only into amulets; the eidolons and the hero monsters may be in rings" - a boss soul
# stays the one soul of the amulet, a hero monster's soul fits an amulet or a ring (beside the eidolons). A soul set
# into an amulet before keeps working either way
SOUL_FITS = {'boss': {'amulet'}, 'hero': {'amulet', 'ring'}}
# 1.8.4 (owner 21.10, "do souls drop from the three skeletons near Megara?" - Polypas, Menon, Aristeus: classified
# Quest, not Hero): named Quest monsters are hero monster souls; not the developers' test monsters
QUEST_SKIP = re.compile(r'\\zz_?dev\\')


def settings():
    """TQTogether.ini: Souls=1, SoulHeroes=1, SoulBossShards=3, SoulHeroShards=2, SoulBossChance=15,
    SoulHeroChance=12, SoulOrbChance=20, SoulChestChance=15, SoulTartarusChance=10 (% per ordinary chest of the
    Tartarus arenas: a soul of any boss or hero monster), SoulLife=100 (%), SoulMaxScale=1.3,
    SoulDamage=30 (% of the hero's damage per second the median boss soul deals with its basic attack; 0 = the boss's
    own damage only), SoulSpeedMax=2 (no animation of a soul faster than this many times the boss's own; 1 = the
    boss's own speeds), SoulTestShop=arachne,nessus (shards sold by the ring merchants - for testing)"""
    st = paths.settings()
    out = {}
    for k, d in DEFAULTS:
        v = st.get(k)
        if isinstance(d, str):
            out[k] = (v if v is not None else d).strip().lower()
            continue
        try:
            x = float((v if v not in (None, '') else str(d)).replace(',', '.'))
        except ValueError:
            x = float(d)
        lo, hi = LIMITS.get(k, (0, 1))
        out[k] = min(hi, max(lo, x))
    for k in ('soulbossshards', 'soulheroshards'):
        out[k] = int(round(out[k]))
    return out


# --- the game's own monster growth (research\souls\level_curve.py, medians of 2129 vanilla level-variant pairs, as
#     ln(1 + %/level) per band of Normal-difficulty levels)
LIFE_CURVE = ((20, 0.0814), (40, 0.0313), (60, 0.0196), (None, 0.0150))
ATTR_CURVE = ((20, 0.0400), (40, 0.0237), (60, 0.0196), (None, 0.0152))
STAT_CURVE = {'characterLife': LIFE_CURVE, 'characterMana': ATTR_CURVE, 'characterStrength': ATTR_CURVE,
              'characterDexterity': ATTR_CURVE, 'characterIntelligence': ATTR_CURVE}
SKILL_PER_LEVEL = 0.165
GAP_E, GAP_L = 16, 31          # median Epic / Legendary level above Normal of vanilla bosses (Legendary-only EE fill)
CORRIDOR = {'boss': (0.7, 1.5), 'hero': (0.4, 1.0)}    # life vs the median boss; owner 16.10: no soul of an early
                                                        # boss may be weak late (hero floor 2000 = Ether Lord's)
# life anchor: the median boss soul of a level-85 hero has 5000 base life - one value on every difficulty, like the
# game's own pets (the pet pak adds +200 % / +208 % on Epic / Legendary: ~16.6k on Legendary, about a companion
# hero's). For scale: the strongest permanent vanilla pets have 1.9-2.7k base (Ether Lord 2300, Core Dweller 1875,
# the developers' companion Ylva 2700 on Legendary, their boss Ylva 13000); the first build of the souls took the
# bosses' own life and gave 7-34k base (x3 with the pak) - Cerberus at 107k.
# 1.6.5, owner after playing Tartarus and Typhon: "a bit tougher, so it shows they are bosses" - 5000 -> 7500
# (~24k on Legendary; a soul also counts as one more player for the party difficulty)
# 1.7.1, owner after Cerberus against Typhon with the 1.7.0 damage (x63): "the damage too strong, the life weak" -
# SoulDamage 50 -> 30 and the anchor 7500 -> 15000 (~47k on Legendary; Cerberus ~70k)
LIFE_ANCHOR, ANCHOR_LEVEL = 15000.0, 85


def anim_view(rec, table=None):
    """{lowercase field: (name, values)} of a creature as the game animates it. 1.7.0: a creature with an animation table
    (charAnimationTableName) plays every animation the table names at the table's speed for it; the same fields in
    its own record are then dead leftovers (Hades' record names a satyr's clips, the table his own)"""
    F = {vn.lower(): (vn, vals) for vn, vt, vals in rec['vars']}
    if table is None:
        return F
    T = {vn.lower(): (vn, vals) for vn, vt, vals in table['vars']}
    for low, (name, vals) in T.items():
        m = ANIM_SET.match(name)
        if not m or not vals or not isinstance(vals[0], str) or not vals[0]:
            continue
        F[low] = (name, vals)
        sp = '%s%sAnimSpeed%s' % m.groups()
        F[sp.lower()] = T.get(sp.lower(), (sp, [1.0]))
    return F


def anim_table(R, rec):
    """the animation table record a creature names, or None (R: a record store with get / peek)"""
    t = get1(rec, 'charAnimationTableName', '') or ''
    k = key_of(t) if t else ''
    if not k or k not in R:
        return None
    return R.peek(k) if hasattr(R, 'peek') else R.get(k)


def anim_fixes(rec, src=None, line=None, table=None, src_table=None, giant=False, speedup=None, atk_factor=1.0,
               cast_factor=1.0):
    """src: the boss record the soul is made from; line: the run line in m/s (the hero's speed); table / src_table:
    their animation tables, if they have one; giant: a boss that paths as Large - its line is its own speed in the game
    (src), at least RUN_LINE, not the hero's; speedup: SoulSpeedMax - no animation of the soul (run, attack, spell,
    skill) plays more than this many times faster than the boss's own (anim speed x stat, src); atk_factor /
    cast_factor (1.7.5): the hero's attack / cast speed bonus - every strike (spell, skill) is aimed at the boss's own
    time, at most the line, divided by it (measured from the boss's own time, so a second pass asks for nothing more).
    -> [(field, old, new, what, in_table)]: what brings this creature to the run line on the ground and within
    ATTACK_LINE / SPECIAL_LINE per attack / skill, as far as `speedup` lets; empty for a creature already that quick
    (or at the caps). in_table: the field belongs in the animation table, not the record. An animation missing from
    soul_anims.ANIMS is left as it is. The walk of a set is sped up with its run (Tartarus walks to run).
    1.6.7: an animation field goes at most to ANIM_CAP (the vanilla maximum); what is still missing goes onto the
    creature's own stat (characterRunSpeed / AttackSpeed / SpellCastSpeed, `new` is then the per-difficulty list), up to
    STAT_CAP - and (1.7.3) only as far as no animation of that kind passes `speedup` x its own in the game."""
    from soul_anims import ANIMS
    line = RUN_LINE if line is None else line
    speedup = SPEEDUP_MAX if speedup is None else speedup
    F = anim_view(rec, table)
    in_tab = {vn.lower() for vn, vt, vals in table['vars'] if ANIM_SET.match(vn) and vals and isinstance(vals[0], str)
              and vals[0]} if table is not None else set()        # the animations the table gives
    val = lambda k, d: (F[k][1] if k in F and F[k][1] else d)
    S = {k: v for k, (n, v) in anim_view(src, src_table).items()} if src is not None else None
    sval = lambda k, d: (S[k] if S and S.get(k) else d)
    scale = float(val('scale', [1.0])[0] or 1.0)
    stat_of = {'Run': 'characterRunSpeed', 'Attack': 'characterAttackSpeed', 'SpellAttack': 'characterSpellCastSpeed',
               'Special': 'characterSpellCastSpeed'}          # spells and skill animations: the cast speed (1.6.4)
    stat = {kd: float(val(f.lower(), [1.0])[-1] or 1.0) for kd, f in stat_of.items()}
    own_stat = {kd: float(sval(f.lower(), [1.0])[-1] or 1.0) for kd, f in stat_of.items()}
    anims = []                                       # (kind, prefix, num, spname, sp, own playback, k wanted, what(k))
    for low, (name, vals) in sorted(F.items()):
        m = ANIM_SET.match(name)
        if not m or not vals or not isinstance(vals[0], str) or not vals[0]:
            continue
        info = ANIMS.get(vals[0].lower().replace('/', BS))
        if not info:
            continue
        pre, kind, num = m.groups()
        if kind == 'Walk':
            continue
        spname = '%s%sAnimSpeed%s' % (pre, kind, num)
        sp = float(val(spname.lower(), [1.0])[0] or 1.0)
        own = float(sval(spname.lower(), [1.0])[0] or 1.0) * own_stat[kind] if S is not None else None
        room = speedup * own / max(sp * stat[kind], 1e-6) if own else float('inf')   # how much faster it may still go
        k, what = 1.0, None
        if kind == 'Run' and info[0] > 0:
            v = info[0] * scale * sp * stat['Run']
            ln = line
            if giant and own:       # 1.7.1: not faster than itself in the game (its own size), at least RUN_LINE
                ln = min(line, max(RUN_LINE, info[0] * float(sval('scale', [1.0])[0] or 1.0) * own))
            if v < ln - 1e-3:
                k = min(ln / v, room)
                what = lambda kk, v=v: 'run %.1f -> %.1f m/s' % (v, v * kk)
        elif kind in ('Attack', 'SpellAttack', 'Special') and info[1] > 0:
            t = info[1] / (sp * stat[kind])
            lim = SPECIAL_LINE if kind == 'Special' else ATTACK_LINE
            t_own = info[1] / own if own else t
            target = min(t_own, lim) / (atk_factor if kind == 'Attack' else cast_factor)
            if t > target + 1e-3:
                k = min(t / target, room)
                label = {'Attack': 'attack', 'SpellAttack': 'spell', 'Special': 'skill'}[kind]
                what = lambda kk, t=t, label=label: '%s %.1f -> %.1f s' % (label, t, t / kk)
        anims.append((kind, pre, num, spname, sp, own, k, what))
    out, rest, new_sp = [], {}, {}
    for kind, pre, num, spname, sp, own, k, what in anims:
        new_sp[spname] = sp
        if what is None or k <= 1.0 + 1e-3:
            continue
        cap = ANIM_CAP[kind]
        ka = min(k, max(1.0, cap / sp))             # the animation, up to the vanilla maximum
        if ka > 1.0 + 1e-6:
            new_sp[spname] = sp * ka
            out.append((spname, sp, sp * ka, what(k), (pre + kind + 'anim' + num).lower() in in_tab))
            if kind == 'Run':
                wname = '%sWalkAnimSpeed' % pre
                if (pre + 'walkanim').lower() in F:
                    wsp = float(val(wname.lower(), [1.0])[0] or 1.0)
                    out.append((wname, wsp, min(max(wsp, cap), wsp * ka), what(k), (pre + 'walkanim').lower() in in_tab))
        if k / ka > 1.0 + 1e-3:
            rest[stat_of[kind]] = max(rest.get(stat_of[kind], 1.0), k / ka)
    for st_name, kr in sorted(rest.items()):
        # the stat moves every animation of its kind: none of them past `speedup` x its own in the game
        kinds = [kd for kd, f in stat_of.items() if f == st_name]
        lim = min([speedup * own / max(new_sp[spname] * stat[kind], 1e-6)
                   for kind, pre, num, spname, sp, own, k, what in anims if kind in kinds and own] or [kr])
        kr = min(kr, max(1.0, lim))
        cur = [float(x or 0) for x in (val(st_name.lower(), [1.0]))]
        new = [min(STAT_CAP[st_name], x * kr) for x in cur]
        if max(n - c for n, c in zip(new, cur)) > 1e-3:
            out.append((st_name, cur, new, '%s x%.2f (animation at its cap)' % (
                st_name, max(n / c for n, c in zip(new, cur))), False))
    return out


def speedups(pet, src, table=None, src_table=None):
    """[(how many times faster the soul plays it than the boss, animation)] for every run, attack, spell and skill
    animation both name (anim speed x its stat)"""
    stat_of = {'Run': 'characterrunspeed', 'Attack': 'characterattackspeed', 'SpellAttack': 'characterspellcastspeed',
               'Special': 'characterspellcastspeed'}
    P, S_ = anim_view(pet, table), anim_view(src, src_table)
    one = lambda V, k: float(((V.get(k) or (None, [1.0]))[1] or [1.0])[-1] or 1.0)
    out = []
    for low, (name, vals) in P.items():
        m = ANIM_SET.match(name)
        if not m or m.group(2) == 'Walk' or not vals or not isinstance(vals[0], str) or not vals[0] or low not in S_:
            continue
        sp = ('%s%sAnimSpeed%s' % m.groups()).lower()
        mine = one(P, sp) * one(P, stat_of[m.group(2)])
        own = one(S_, sp) * one(S_, stat_of[m.group(2)])
        if own > 0:
            out.append((mine / own, name))
    return out


def ai_fixes(R, pet):
    """1.7.7: special-attack slots of a soul that shake the air -> [('range', slot, old class, new class, skill, reach)]
    for a wave / a blast around the caster whose range class reaches past it, then [('drop', slot, kept slot, skill,
    delay, kept delay)] for a skill wired twice for overlapping distances (the longest delay stays)"""
    g = lambda f, d=None: get1(pet, f, d)
    med, lng = float(g('mediumRangeMin', 4) or 4), float(g('longRangeMin', 8) or 8)
    ctl = R.get(key_of(g('controller', '') or ''))
    view = float(get1(ctl, 'ViewDistance', 24) or 24) if ctl is not None else 24.0
    far = {'ShortRange': med, 'MediumRange': lng, 'LongRange': view, 'AnyRange': view}
    out, slots = [], []
    for sl in SLOTS:
        sk = g(sl + 'SkillName', '')
        if not sk:
            continue
        rng = g(sl + 'Range', 'AnyRange') or 'AnyRange'
        s = R.get(key_of(sk))
        cls = (get1(s, 'Class', '') or '') if s is not None else ''
        reach = None
        if cls in REACH_WAVE:
            reach = float(get1(s, 'waveDistance', 0) or 0) or None
        elif cls in REACH_AROUND:
            reach = float(max(float(x or 0) for x in (getv(s, 'skillTargetRadius') or [0]))) or None
        if reach and rng != 'ShortRange' and far.get(rng, view) > reach * REACH_SLACK + 0.5:
            new = 'MediumRange' if reach * REACH_SLACK + 0.5 >= lng else 'ShortRange'
            if new != rng:
                out.append(('range', sl, rng, new, sk, reach))
                rng = new
        slots.append((sl, key_of(sk), sk, rng, float(g(sl + 'Delay', 0) or 0)))
    by = collections.defaultdict(list)
    for sl, k, sk, rng, dl in slots:
        by[k].append((sl, sk, rng, dl))
    for k, lst in by.items():
        kept = []
        for sl, sk, rng, dl in sorted(lst, key=lambda x: (-x[3], SLOTS.index(x[0]))):
            hit = next((x for x in kept if x[2] == rng or 'AnyRange' in (x[2], rng)), None)
            if hit:
                out.append(('drop', sl, hit[0], sk, dl, hit[3]))
            else:
                kept.append((sl, sk, rng, dl))
    return out


def walks(view):
    """False if none of the creature's known run animations moves it (Tiamat: her 'run' is an idle) - it only
    teleports; None if no run animation is known"""
    from soul_anims import ANIMS
    runs = [ANIMS.get(vals[0].lower().replace('/', BS)) for low, (name, vals) in view.items()
            if re.search(r'RunAnim$', name) and vals and isinstance(vals[0], str) and vals[0]]
    runs = [r for r in runs if r]
    if not runs:
        return None
    return max(r[0] for r in runs) > 0.05


WEAPON_CLASS = re.compile(r'^Weapon', re.I)
WEAPON_DAMAGE = ('physical', 'pierce', 'cold', 'fire', 'lightning', 'poison', 'life')     # fields() is lowercase
_WEAPON_AVG = {}


def _weapon_avg(R, k, depth=0):
    """average base hit of the weapons a loot record leads to (every table entry by its weight; a DynWeight table's
    level windows taken as equal), None if it leads to none"""
    if k in _WEAPON_AVG:
        return _WEAPON_AVG[k]
    _WEAPON_AVG[k] = None
    if depth > 10 or k not in R:
        return None
    r = R.peek(k) if hasattr(R, 'peek') else R[k]
    F = fields(r)
    if WEAPON_CLASS.match((F.get('class') or [''])[0] or ''):
        hit = sum((float((F.get('offensive%smin' % t) or [0])[0] or 0) +
                   max(float((F.get('offensive%smax' % t) or [0])[0] or 0), float((F.get('offensive%smin' % t) or [0])[0] or 0)))
                  / 2.0 for t in WEAPON_DAMAGE)
        _WEAPON_AVG[k] = hit if hit > 0 else None
        return _WEAPON_AVG[k]
    acc = tot = 0.0
    for j in range(1, 31):
        v = F.get('lootname%d' % j)
        if not v or not v[0]:
            continue
        w = float((F.get('lootweight%d' % j) or [1])[0] or 0)
        h = _weapon_avg(R, key_of(v[0]), depth + 1) if w > 0 else None
        if h is not None:
            acc, tot = acc + w * h, tot + w
    _WEAPON_AVG[k] = acc / tot if tot else None
    return _WEAPON_AVG[k]


def weapon_hit(R, rec, d=2):
    """1.8.3 (owner 19.10: "the Faceless One kills everything with one blow, harder than me"): (average base hit of the
    weapon a creature carries in its right hand on difficulty d, the chance it carries one) - its equip loot
    (chanceToEquipRightHand, lootRightHandItemN by chanceToEquipRightHandItemN) walked down to the weapons. 91 souls
    fight with a weapon; their basic attack was measured by the bare hand (most have none: measured 0), so no corridor
    held them and the pace with the hero was not made up for - the Faceless One hit at half the hero's DPS, 21 souls
    above it. (0, 0) for a creature without a weapon"""
    F = fields(rec)
    # the right hand first; a bow is carried in the LEFT hand (the Alfar archers: no right-hand weapon at all)
    for hand in ('righthand', 'lefthand'):
        ch = float((F.get('chancetoequip%s' % hand) or [0])[0] or 0)
        if ch <= 0:
            continue
        acc = tot = 0.0
        for j in range(1, 7):
            v = F.get('loot%sitem%d' % (hand, j))
            w = float((F.get('chancetoequip%sitem%d' % (hand, j)) or [0])[0] or 0)
            if v and v[0] and w > 0:
                h = _weapon_avg(R, key_of(v[min(d, len(v) - 1)]))
                if h is not None:
                    acc, tot = acc + w * h, tot + w
        if tot:
            return acc / tot, min(1.0, ch / 100.0)
    return 0.0, 0.0


def basic_dps(pet, table, pak, eq, weapon=(0.0, 0.0)):
    """1.7.0: damage per second of a soul's basic attack, for SoulDamage: its hand hit with the pet pak's Legendary
    physical bonus and its strength (combatequations physicalDamageEquation), over its attack time (its attack
    animations at its attack speed with the pak's). 1.8.3: weapon = weapon_hit() - a creature strikes with the weapon
    it carries, not the hand (0 for one with neither).
    Only the median of the bosses is used: every soul gets the same factor and keeps its strength among the others."""
    from soul_anims import ANIMS
    F = anim_view(pet, table)
    g = lambda k, d=0.0: float(((F.get(k.lower()) or (None, [d]))[1] or [d])[-1] or d)
    hit = (g('handHitDamageMin') + g('handHitDamageMax')) / 2.0
    w, wc = weapon
    if w > 0:
        hit = wc * w + (1 - wc) * hit
    if hit <= 0:
        return 0.0
    hit *= 1 + pak.get('offensivePhysicalModifier', 0.0) / 100.0
    env = {'physicalDamageDV': hit, 'strengthDV': g('characterStrength'), 'dexterityDV': g('characterDexterity'),
           'intelligenceDV': g('characterIntelligence'), 'characterLevelDV': g('charLevel', 1.0)}
    try:
        hit = float(eval(eq.replace('^', '**'), {'__builtins__': {}}, env))
    except Exception:
        pass
    speed = g('characterAttackSpeed', 1.0) * (1 + pak.get('characterAttackSpeedModifier', 0.0) / 100.0)
    times = []
    for low, (name, vals) in F.items():
        m = ANIM_SET.match(name)
        if m and m.group(2) == 'Attack' and vals and isinstance(vals[0], str) and vals[0]:
            info = ANIMS.get(vals[0].lower().replace('/', BS))
            if info and info[1] > 0:
                sp = float(((F.get(('%sAttackAnimSpeed%s' % (m.group(1), m.group(3))).lower()) or (None, [1.0]))[1]
                            or [1.0])[0] or 1.0)
                times.append(info[1] / max(sp * speed, 1e-3))
    t = median(times) if times else 1.2
    return hit / max(t, 0.2)


def floor2(x):
    """x cut DOWN to two significant digits (17.94 -> 17, 1.857 -> 1.8)"""
    if x <= 0:
        return 0.0
    e = math.floor(math.log10(x)) - 1
    return round(math.floor(x / 10.0 ** e + 1e-9) * 10.0 ** e, 6)


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def grow(curve, frm, to):
    """factor a stat grows by from level frm to level to (Normal levels) along curve; to < frm shrinks"""
    sign = 1.0
    if to < frm:
        frm, to, sign = to, frm, -1.0
    s, x = 0.0, frm
    for edge, rate in curve:
        top = to if edge is None else min(edge, to)
        if top > x:
            s += (top - x) * rate
            x = top
        if x >= to:
            break
    return math.exp(sign * s)


# --- which records, grouped how
CLASSES = ('Monster', 'Hades', 'SpiritHost', 'Cerberus', 'Typhon2', 'Megalesios', 'Ormenos')
SPECIAL_CLASS = set(CLASSES) - {'Monster'}
# summoned and fought with by the owner 17.10 (TQVault test vault): they come, follow, fight and die as pets
SPECIAL_TESTED = {'hades ~ god of the dead', 'cerberus ~ warden of hades', 'chaos ~ cerberus', 'megalesios ~ telkine',
                  'ormenos ~ telkine', "pharaoh's honor guard"}
SKIP_KEY = re.compile(r'sandbox|\\old\\|\\zzz\\|_old\.dbr$|test|credits|death_anim')   # zzz: unused Erik
MERGE_EN = {'surtr ~ fire incarnate': 'surtr ~ lord of muspelheim'}     # one soul for both stages
AI_NAMES = ('attackSkillName', 'specialAttackSkillName', 'specialAttack2SkillName', 'specialAttack3SkillName',
            'specialAttack4SkillName', 'specialAttack5SkillName', 'initialSkillName', 'buffSelfSkillName',
            'buffSelf2SkillName', 'buffSelf3SkillName', 'buffOtherSkillName', 'buffOther2SkillName',
            'buffOther3SkillName', 'healSkillName', 'berserkSkillName', 'dyingSkillName', 'chainInitialSkill',
            'chainNextSkill')
# boss chests (FixedItemContainer locked until a Boss dies), by the chest's name: only for a boss with no room in its
# own loot (the gods of Asgard, Ylva, Mimir drop nothing themselves); repeat chests included
# 1.6.3: bosses fought where loot on the ground vanishes at once (the Tartarus arena, owner 16.10: gold and potions from
# chests stay, monster drops vanish) - their reward orb gives the soul as well, whatever room their own loot has
ARENA_CHEST_EN = (('tartarus ~', r'^bosschest_tartarus_0[123]\.dbr$'),)
CHEST_EN = (('freyja', r'^bosschest10_aesir'), ('wodan', r'^bosschest10_aesir'), ('tyr ', r'^bosschest10_aesir'),
            ('ylva', r'^bosschest14_loki'), ('loki', r'^bosschest14_loki'), ('mimer', r'^bosschest12_mimir'),
            ('thrym', r'^bosschest11_thrym'), ('surtr', r'^bosschest15_surtr'), ('king goldtooth', r'^bosschest04_trollking'),
            ('austri', r'^bosschest08_austir&nar'), ('nar ', r'^bosschest08_austir&nar'), ('nidhoggr', r'^bosschest13_nidhoggr'),
            ('hildisvini', r'^bosschest07_hildisvini'), ('fafnir', r'^bosschest17_fafnir'), ('porcus', r'^bosschest01_porcus'),
            ('charon', r'^bosschest02_charon'), ('cerberus ~ warden', r'^bosschest03_cerberus'),
            ('typhon ~ undead', r'^bosschest04_skeletaltyphon'), ('hades', r'^bosschest05_hades'),
            ('deino', r'^bosschest01_graeae'), ('enyo', r'^bosschest01_graeae'), ('pemphredo', r'^bosschest01_graeae'),
            ('ladon', r'^bosschest12_ladon'), ('omega telkine', r'^bosschest12_omega'), ('tiamat', r'^bosschest12_tiamat'),
            ('qiong qi', r'qiongqi'), ('sihai', r'sihailongwang'), ('akhenaten', r'akhenaten'), ('huoshen', r'huoshen'),
            ('shen ~', r'^boss_o_shen'), ('the ten suns', r'^boss_o_sun(_repeat)?\.dbr$'), ('sanshou', r'sanshou'),
            ('exhumed medjai', r'exhumed ?madjai'), ('pirate captain', r'ghostpiratecap'), ('feiyi', r'feiyi'),
            ('demonic elemental', r'demonicelemental'), ('yaoguai', r'yaoguai'),
            # 1.7.9: their souls came from the orbs only - their own chests (Celestial Accord: the Ten Suns merged, one
            # fight). Not Toxeanubis: bosschest18_devhell is Ragnarok's Dark Chest of Wonders
            ('zazamankh', r'^boss_o_zazamankh(_repeat)?\.dbr$'), ('celestial accord', r'^boss_o_sun(_repeat)?\.dbr$'))
# electrum orb regions (x4_electrumorb_<region>_<tier>_loot): by the folder of the boss's own records
REGION_DIR = (('records' + BS + 'creature' + BS, '1_antiquity'), ('records' + BS + 'xpack' + BS, '2_hades'),
              ('records' + BS + 'xpack2' + BS, '3_scandia'), ('records' + BS + 'xpack3' + BS, '4_tiamat'))
CHINA_EN = ('feiyi', 'qiong qi', 'sihai', 'huoshen', 'shen ~', 'the ten suns', 'celestial accord', 'colossal fire elemental',
            'sanshou', 'saixi')
# 1.7.9: Eternal Embers hero monsters (xpack4) by the folder of their creature: the Jade Emperor's lands, else Thebes
CHINA_DIR = ('monk', 'monkeys', 'mogwai', 'terracotta', 'yaoguai', 'earth elemental', 'metal elemental',
             'water elemental', 'wood elemental', 'fire elementals')
# pet panel icon by race (vanilla pets of that kind)
ICONS = {'animal': ('InGameUI\\Icons\\Party\\WolfUp01.tex', 'InGameUI\\Icons\\Party\\WolfDown01.tex'),
         'undead': ('InGameUI\\Icons\\Party\\LicheKingUp01.tex', 'InGameUI\\Icons\\Party\\LicheKingDown01.tex'),
         'magic': ('InGameUI\\Icons\\Party\\EarthPetUp01.tex', 'InGameUI\\Icons\\Party\\EarthPetDown01.tex'),
         'demon': ('XPack\\UI\\Icons\\Party\\NightmareUp01.tex', 'XPack\\UI\\Icons\\Party\\NightmareDown01.tex'),
         'god': ('InGameUI\\icons\\party\\summonoutsiderup01.tex', 'InGameUI\\icons\\party\\summonoutsiderred01.tex'),
         'construct': ('XPack4\\ui\\icons\\pets\\neidanpetup01.tex', 'XPack4\\UI\\Icons\\Pets\\NeidanRedUp01.tex'),
         'human': ('XPack2\\ui\\icons\\pets\\ylva_up.tex', 'XPack2\\ui\\icons\\pets\\ylva_down.tex')}
RACE_ICON = {'Beast': 'animal', 'Beastman': 'animal', 'Insectoid': 'animal', 'Plant': 'animal', 'Undead': 'undead',
             'Magical': 'magic', 'Demon': 'demon', 'Titan': 'god', 'Deity': 'god', 'Olympian': 'god', 'Giant': 'god',
             'Telkine': 'god', 'Construct': 'construct', 'Device': 'construct', 'Humankind': 'human'}
# look of the soul relic: the Act IV charm "Tortured Soul" (bosses: its Legendary colours, heroes: Epic)
LOOK = {'boss': ('XPack\\Items\\Charms\\X_AnimalPart05A_L.tex', 'XPack\\Items\\Charms\\X_AnimalPart05B_L.tex'),
        'hero': ('XPack\\Items\\Charms\\X_AnimalPart05A_E.tex', 'XPack\\Items\\Charms\\X_AnimalPart05B_E.tex')}
CALL_ICON = ('InGameUI\\Icons\\Skills\\Spirit\\SpectralHero01Up.tex', 'InGameUI\\Icons\\Skills\\Spirit\\SpectralHeroDown01.tex')
# 1.6.2: treasureProxyName (80 bosses: the reward chest put down where the boss dies - the Tartarus soul left its orb,
# owner 16.10) and actorToSpawnOnDeath2 (14) go too
# 1.6.8: perPartyMemberDropItemName (30 bosses/heroes: a quest item handed to every party member on death, whatever
# dropItems says - the Ancient One's soul dropped his Magic Compass)
DROP_FIELDS = ('actorToSpawnOnDeath', 'actorToSpawnOnDeath2', 'treasureProxyName', 'perPartyMemberDropItemName',
               'dyingSkillName', 'MonsterMusic',
               'MonsterMusicRadius', 'goldGenerator', 'LowerHealthDisplayPercentage', 'UpperHealthDisplayPercentage',
               'distressCallGroup', 'IsGenerated', 'chainInitialSkill', 'chainNextSkill', 'chainBehavior')
# 1.6.3 speed from the ANIMATIONS (owner 16.10: the Tartarus soul lagged behind and swung slowly; the 1.6.2 floors on the
# speed fields changed nothing). TQ moves a creature by the root motion of its run animation: ground speed = root speed
# of the .anm x scale x <set>RunAnimSpeed x characterRunSpeed. Tartarus "runs" with his walk (tartarus_walk.anm, 2.16 m/s)
# shrunk to 1.05: 2.7 against Arachne's 8.1 and the hero's 6.25 x 1.33 = 8.3. Attacks: animation length / (anim speed x
# characterAttackSpeed) - his 2.4-2.8 s swings, 4-4.9 s spells, against 1.2 s for the median soul and 0.8 s for a hero.
# Each animation set of a soul that is slower is played faster to the line, nothing else changes. Arachne (owner:
# "normal") is the yardstick and stays as she is.
# soul_anims.ANIMS: root speed and length of every animation the souls use, read from the game's archives read-only.
RUN_LINE = 7.0             # m/s on the ground at characterRunSpeed - the floor; 1.7.0: the hero's own speed above it
HERO_RUN = 8.31            # m/s a hero's body runs without bonuses (MalePC_Run / FemalePC_Run 6.25 m/s x run speed 1.33)
ATTACK_LINE = 1.6          # s per basic attack: Arachne's slowest is 1.5 (median soul 1.2, Tartarus 2.4)
# 1.6.4 (owner: "the spells stayed as slow"): spells and skill animations play at characterSpellCastSpeed - Tartarus 1.0,
# Arachne 1.3 - and Tartarus casts most often the ones under the old line (lightning cone with the spell animation,
# fire spikes, fire walk). Cast speed at least Arachne's; skills at it within 2.0 s (Arachne's slowest: 2.5 / 1.3 = 1.9)
CAST_LINE = 1.3
SPECIAL_LINE = 2.0         # s per skill animation at the cast speed (Tartarus' meteor 4.3 s)
# 1.6.7 caps from vanilla monsters and pets (research\souls\probe_speed_ranges.py): animation speeds go up to 2.5 for
# runs and 2.0 for attacks and spells; characterRunSpeed p99 2.2, attack and cast speed p99 2.0
ANIM_CAP = {'Run': 2.5, 'Attack': 2.0, 'SpellAttack': 2.0, 'Special': 2.5}
STAT_CAP = {'characterRunSpeed': 2.5, 'characterAttackSpeed': 2.0, 'characterSpellCastSpeed': 2.0}
# 1.6.9 (owner: the Ancient One "a giant machine running like a cockroach"): the run was sped up at most x2.6 the
# soul's own - Tartarus got x2.57 (right). A giant stays a giant; the rest of the way it teleports.
# 1.7.3 (owner 17.10: Eylin's Heart of Oak, +10 % speed to every ally, turned Talos' animations "almost into mush"):
# only the RUN had that cap - his spells played x2.9 faster than his own, his attacks x2.0; Porcus' skill x4.5, the Ten
# Suns' x4, the Dragon Liche's x3.7. Now no animation of a soul (run, attack, spell, skill) plays more than SoulSpeedMax
# (2.0) times faster than the boss's own: with +30 % from auras and buffs on top still within Tartarus' x2.6
SPEEDUP_MAX = 2.0
# 1.7.0 (owner 17.10: Hades and Megalesios slow, the Ancient One "a bit faster than it should"). 106 souls take their
# animations from a charAnimationTableName table (anim_view): their speed had been measured on dead clips of their own
# records and their fixes written there - only characterRunSpeed acted. The Ancient One really runs lobstermonster_run
# (15.2 m/s at speed 1: 7.6 m strides): x18.6 on a dead field changed nothing (1.6.6), its stat x7.4 / x4.1 / x2.1 made
# it "crazy fast" / "a cockroach" / "a bit fast" (1.6.7-1.6.9). The 1.6.8 cap on anim x stat (3.1) came from that
# misreading and is gone: it held Megalesios (x3.0 by design) at 3.7 m/s and Hades (x2.2) at 4.0. The table is now
# copied per soul (<sid>_soulanm.dbr) and sped up there. The run line follows the hero (owner: "if the player moves
# fast, the boss keeps up"): his own ground speed, HERO_RUN x (1 + his run bonus from gear and passives within the
# game's cap), less the +26 % the game gives every pet on Legendary - at least RUN_LINE
# Skills a boss casts on its arena only (owner 17.10: Cerberus' poison from the floor cracks of his arena): they fire
# the level's geysers / turrets (numGeysersToFire -1 = all of them; "activates lake turrets", targetPlayer) - elsewhere
# nothing happens; Typhon's skill transfer pulls powers from his arena statues. 1.7.2 (owner 17.10): Ormenos' telekinesis
# throws the stalactites of his obsidian cave - away from it the stalactites he drops fall (and hit) but none is
# thrown, and the AI chose the throw 45 % of the time; the drop stays
ARENA_SKILL_CLASS = {'Skill_CerberusGeysers', 'Skill_CharonGeysers', 'Skill_TurretFireControl', 'Skill_TyphonSkillTransfer',
                     'Skill_AttackTelekinesis'}
# souls that cannot walk (Tiamat, Apophis: the run is an idle; owner 17.10: Tiamat casts once and then stands while she
# is hit, Apophis neither attacks nor follows): their basic attack had an 8 s cooldown and the rest strike at arm's
# length, so between waves the AI walked towards the enemy - on the spot. A ranged basic attack of their own body
# (the animation reference decides) and a short leash: they teleport to the hero at STATIC_TELEPORT m
STATIC_ATTACK = (('spitpoison', 'records\\xpack3\\skills\\boss skills\\tiamat_spitpoison.dbr'),)
STATIC_TELEPORT = 14.0
# 1.7.7 (owner 18.10): "Talos uses his flamethrower too often, and from where it does not reach - he shakes the air;
# the boss itself does the same". The AI fires a special when the target is in the slot's range class (ShortRange <
# mediumRangeMin <= MediumRange < longRangeMin <= LongRange, AnyRange: all, up to the controller's ViewDistance). A
# wave (flame breath) or a blast around the caster does not move it, so a class reaching past the skill shakes the
# air: Talos' flamethrower (20 m) sat in LongRange (15-24 m) with a 1 s delay AND in MediumRange with 5 s. Such a slot
# is narrowed to what the skill reaches, and a skill then wired twice for the same distances keeps one slot - the
# longest delay. Melee strikes and charges walk to the target themselves; projectiles fly - they stay as they are
SLOTS = ['specialAttack'] + ['specialAttack%d' % n for n in range(2, 6)]
REACH_WAVE = ('Skill_AttackWave',)
REACH_AROUND = ('Skill_AttackRadius',)          # a blast around the caster (Talos' stomp, Thunder Clap)
REACH_SLACK = 1.1      # a class may reach 10 % past the skill: the Chimera's 17 m breath keeps MediumRange (5-18 m)
# 1.7.0 damage (owner 17.10: with two eidolons and a soul - monsters as for 4 players - "the bosses hit some bug and
# cannot do a thing"; a soul's hand hit is 1-3 % of a geared hero's damage per second): SoulDamage % of the hero's
# character-window DPS is what the MEDIAN boss soul's basic attack deals (basic_dps); every soul gets that one factor
# (never below 1) as a passive (souls\soul_power.dbr: every damage modifier the boss passive GlobalProperties_*_Boss
# has, plus physical), so their skills scale as well and each keeps its rank among the bosses. Per difficulty level it
# multiplies the pet pak's own bonus too: +x % = (factor - 1) x (100 + pak %)
PET_PAK = 'records\\game\\petgamebalanceattributes.dbr'
COMBAT_EQ = 'records\\game\\combatequations.dbr'
DAMAGE_FIELDS = ('offensivePhysicalModifier', 'offensivePierceModifier', 'offensiveColdModifier', 'offensiveFireModifier',
                 'offensiveLightningModifier', 'offensivePoisonModifier', 'offensiveLifeModifier',
                 'offensiveSlowPhysicalModifier', 'offensiveSlowBleedingModifier', 'offensiveSlowColdModifier',
                 'offensiveSlowFireModifier', 'offensiveSlowLightningModifier', 'offensiveSlowPoisonModifier',
                 'offensiveSlowLifeModifier')
DAMAGE_MAX = 200.0
# 1.7.4 (owner 18.10, playing Difficulty=power: monster life x19, damage x3.25): "Talos gives in to the sirens' slows",
# "Cerberus falls off fast", "I kill Typhon for ages and my Typhon soul falls apart from the other mobs".
# - boss_conversionimmunity is the boss's OWN defence (69 of 78 bosses: immune to stun, freeze, sleep, fear, confusion,
#   conversion, slow; 65-85 % against percent-of-life damage; dodge, life +50 %), removed since 1.6.0 along with the
#   boss damage passives - the sirens' song (sleep / conversion / confusion) and dissonance (slow 50 %, stun) took
#   Talos. It stays now; only the boss DAMAGE passives (GlobalProperties_*_Boss) go, damage comes from the hero.
# - the hero difficulty (Difficulty=power) multiplies the monsters' Legendary damage modifiers and offensive ability by
#   HERO_DAMAGE (x3.25 for Nikton's party): the souls were built for vanilla Legendary - their life and defence get
#   the same factor on Legendary (souls\soul_guard.dbr), so a monster's blow lands on a soul as in vanilla Legendary
# a dead soul's body: the eidolons' dissolve (doppelganger record: 2 s, cloud texture, grey) where the boss has none
DISSOLVE_NONE = ('', 'None', 'DissolveOnCallback')
DISSOLVE = (2.0, 'Effects\\Textures\\CloudTEST03.tex', 150)
ANIM_SET = re.compile(r'^(\w+?)(Run|Walk|Attack|SpellAttack|Special)Anim(\d*)$')
BOSS_ONLY_SKILL = re.compile(r'globalproperties_\w*boss|globalproperties_\w*graeae')
MISC_W = 100000                # weights of a slot we write: probabilities x MISC_W / chance


def literal(tag):
    """the name the game shows for a 'tag' that is no tag: the developers' own heroes (zz_dev, a hidden dungeon) carry
    their names as plain text - '~ Toxeanubis the Slayer  ~', 'Anthony The Drunken Warrior' (1.6.6 named the soul
    'toxeanubistheslayer')"""
    return re.sub(r'\s+', ' ', (tag or '').replace('~', ' ')).strip()


def fields(r):
    """{lowercase field name: values} - one pass instead of a scan of ~600 monster fields per lookup"""
    return {vn.lower(): vals for vn, vt, vals in r['vars']}


def misc_slots(r):
    """{slot n: {item value: % per kill}} of a monster's Misc loot (chance x weight / sum of weights of the entries
    that have an item), plus {n: problems} for slots that cannot be read as scalars. 1.8.1: the same item twice in one
    slot is summed (the Exhumed Medjai's health potion 80 + 20 collapsed to the last entry: 5 % -> 1 % per kill)"""
    out, odd = {}, {}
    F = fields(r)
    for n in (1, 2, 3):
        ch = F.get('chancetoequipmisc%d' % n) or [0]
        ents = []
        for j in range(1, 7):
            it = [x for x in (F.get('lootmisc%ditem%d' % (n, j)) or []) if x]
            w = F.get('chancetoequipmisc%ditem%d' % (n, j)) or [0]
            if it:
                ents.append((tuple(key_of(x) for x in it), w))
        if len(ch) != 1 or any(len(w) != 1 for _, w in ents):
            odd[n] = 'per-difficulty chance or weights'
        c = float(ch[0] or 0)
        W = sum(float(w[0] or 0) for _, w in ents)
        out[n] = {}
        if c and W:
            for it, w in ents:
                out[n][it] = out[n].get(it, 0.0) + c * float(w[0] or 0) / W
    return out, odd


def fight_tag(k):
    """1.8.1: what tells records of one folder and level apart as separate spawns: the level number in the file name
    and the side quest (x4_sq301_..._exhumedmedjai_84_a / _87_a; x3sq08_ssaquath_38 / x3sq09_priest_38). The forms and
    stages of one fight share both (boss_hades_50 / boss_hadesform2_50, boss_tiamat1_42 / boss_tiamat2_42)"""
    leaf = k.split(BS)[-1].lower()
    leaf = leaf[:-4] if leaf.endswith('.dbr') else leaf
    nums = re.findall(r'_(\d+)', leaf)
    quest = re.search(r'sq(\d+)', leaf)
    return (nums[-1] if nums else '', quest.group(1) if quest else '')


class Souls(object):
    def __init__(self, b, hero_level=0, hero=''):
        self.b, self.R, self.H, self.hero = b, b.R, int(hero_level or 0), hero
        _WEAPON_AVG.clear()                     # 1.8.3: weapon tables as this database has them (tweaks)
        self.st = settings()
        self.ns = b_ns() + SUB
        self.peek = getattr(b.R, 'peek', None) or b.R.__getitem__   # read-only: no cache
        self._memo = {}
        # 1.7.0: the run line is the hero's own ground speed (his run bonus from gear + passives within the game's cap,
        # Builder.bake_gear) less the run bonus the game gives every pet on Legendary - the soul runs with him
        self.run_bonus = float((getattr(b, 'hero_run', {}) or {}).get(hero, 0.0) or 0.0)
        pet_run = self.pak()[2].get('characterRunSpeedModifier', 0.0)
        self.run_line = round(max(RUN_LINE, HERO_RUN * (1 + max(0.0, self.run_bonus) / 100.0) / (1 + pet_run / 100.0)), 3)
        # 1.7.5: and strikes and casts with him - his attack / cast speed bonus (gear + passives within the caps) speeds
        # every strike / spell / skill of the soul up by as much, within SoulSpeedMax of the boss's own
        hs = (getattr(b, 'hero_speed', {}) or {}).get(hero, {}) or {}
        self.atk_factor = round(1 + max(0.0, float(hs.get('Attack', 0.0) or 0.0)) / 100.0, 3)
        self.cast_factor = round(1 + max(0.0, float(hs.get('SpellCast', 0.0) or 0.0)) / 100.0, 3)
        self.ledger = {'souls': {}, 'misc': {}, 'chests': {}, 'orbs': {}, 'settings': dict(self.st), 'hero_level': self.H,
                       'run_line': self.run_line, 'run_bonus': self.run_bonus, 'atk_factor': self.atk_factor,
                       'cast_factor': self.cast_factor,
                       'loot_counts': getattr(b, 'loot_counts', {})}   # 1.8.1: what add_shards planned per table
        self.orb_entries = {}          # region -> (table record, % per orb), placed by Builder.eidolon_drops
        self.report = []

    # ------------------------------------------------------------------ text
    def text(self, tag, lang):
        t = self.b.vt[lang].get(tag) or ''
        forms = dict(re.findall(r'\[(\w\w)\]([^\[]*)', t))
        if forms:
            t = forms.get('ms') or next(iter(forms.values()), '') or t
        return re.sub(r'\s+', ' ', t.replace('{^n}', ' ')).strip()

    def rec(self, k):
        """a boss or hero record for reading, decoded once (planning reads them many times)"""
        r = self._memo.get(k)
        if r is None:
            r = self._memo[k] = self.peek(k)
        return r

    # ------------------------------------------------------------------ families
    def families(self):
        R = self.R
        fams = collections.OrderedDict()
        tag_en = {}
        rows = self.scan()
        # 1.8.4: a Quest record makes a soul only when its tag names a character of its own: no Boss / Hero soul family
        # has it (those stay exactly as they were) and no record of another classification carries it (a quest's satyr
        # scout is named like every satyr scout), with a name text, not one of the developers' test names
        mcs = collections.defaultdict(set)
        for k, mc, cls_, tag, drop_ in rows:
            if tag.strip() and not SKIP_KEY.search(k):
                mcs[tag.strip().lower()].add(mc)
        for k, mc, cls_, tag, drop_ in rows:
            if mc == 'Other' or cls_ not in CLASSES or SKIP_KEY.search(k):
                continue
            tag = tag.strip()
            if not tag:
                continue
            if mc == 'Quest' and (mcs[tag.lower()] & {'Boss', 'Hero', 'Other'} or QUEST_SKIP.search(k)
                                  or not self.text(tag, 'en')):
                continue
            en = (self.text(tag, 'en') or literal(tag)).lower()
            tag_en[tag.lower()] = en
            fams.setdefault(tag.lower(), {'tag': tag, 'keys': [], 'mc': set()})
            fams[tag.lower()]['keys'].append(k)
            fams[tag.lower()]['mc'].add(mc)
        # merges by English name (Surtr's two stages are one soul)
        by_en = {en: t for t, en in tag_en.items()}
        for a, bb in MERGE_EN.items():
            ta, tb = by_en.get(a), by_en.get(bb)
            if ta and tb and ta in fams and tb in fams:
                gone = fams.pop(ta)
                fams[tb]['keys'] += gone['keys']
                fams[tb]['mc'] |= gone['mc']
        out = []
        for t, f in fams.items():
            kind = 'boss' if 'Boss' in f['mc'] else 'hero'
            f['kind'] = kind
            f['quest'] = f['mc'] == {'Quest'}       # 1.8.4: a named side-quest monster
            f['en'] = tag_en.get(t, '')
            f['sid'] = re.sub(r'[^a-z0-9]+', '', t)[:40]
            f['rep'] = max(f['keys'], key=lambda k: self.rep_score(k))
            out.append(f)
        return out

    def scan(self):
        """[(key, classification, Class, name tag, dropItems)] of every Boss / Hero creature record (Builder's
        boss_monsters uses them too); reading a few fields of 15k monster records takes seconds, so the result is kept
        per base database + tweaks in <data>\\cache.
        1.8.4: the Quest-classified ones as well (the three undead princes near Megara, Ino, Leucus I, Sinmara...: named
        side-quest monsters the game does not call heroes), and as 'Other' any record of another classification that
        carries a Quest tag - a satyr scout of a quest is named like every satyr scout (families() leaves those out)"""
        if getattr(self, '_rows', None) is not None:
            return self._rows
        R = self.R
        import tweaks
        base = getattr(self.b, 'base_arz', '') or ''
        try:
            st_ = os.stat(base)
            tag_ = '%d_%d_%s' % (st_.st_size, int(st_.st_mtime), hashlib.md5(
                (tweaks.fingerprint() + 'scan v3').encode('utf-8')).hexdigest()[:10])
        except OSError:
            tag_ = None
        cache = os.path.join(paths.data_dir(), 'cache', 'souls_scan_%s.json' % tag_) if tag_ else None
        if cache and os.path.exists(cache):
            try:
                rows = json.load(open(cache, encoding='utf-8'))
                if all(len(r_) == 5 and r_[0] in R for r_ in rows):
                    self._rows = rows
                    return rows
            except Exception:
                pass
        few = getattr(R, 'fields', None)
        rows, others = [], []
        for k in sorted(R):
            if 'creature' not in k:      # every one: boss_monsters needs the sandbox records too
                continue
            if few is not None:          # a few fields of each record, not all ~600
                F = few(k, ('monsterClassification', 'Class', 'description', 'dropItems'))
            else:
                F = fields(self.peek(k))
            one = lambda f, d='': (F.get(f.lower()) or [d])[0]
            mc = one('monsterClassification') or ''
            row = [k, mc, one('Class') or '', one('description') or '', one('dropItems', 1)]
            if mc in ('Boss', 'Hero', 'Quest'):
                rows.append(row)
            elif row[3].strip():
                others.append(row)
        qtags = {r_[3].strip().lower() for r_ in rows if r_[1] == 'Quest' and r_[3].strip()}
        rows += [[k, 'Other', cls_, tag, drop] for k, mc, cls_, tag, drop in others if tag.strip().lower() in qtags]
        if cache:
            try:
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                for old in glob.glob(os.path.join(glob.escape(os.path.dirname(cache)), 'souls_scan_*.json')):
                    os.remove(old)
                with open(cache + '.tmp', 'w', encoding='utf-8') as fh:
                    json.dump(rows, fh)
                os.replace(cache + '.tmp', cache)
            except OSError:
                pass
        self._rows = rows
        return rows

    def fd(self, k):
        """field dict of a boss or hero record (planning reads the same ones many times)"""
        m = self.__dict__.setdefault('_fd', {})
        F = m.get(k)
        if F is None:
            F = m[k] = fields(self.rec(k))
        return F

    def rep_score(self, k):
        F = self.fd(k)
        lv = [int(x or 0) for x in (F.get('charlevel') or [0])]
        ai = sum(1 for f in AI_NAMES[:10] if (F.get(f.lower()) or [''])[0])
        # a form that walks beats one that drops: Surtr's lava giant (run 0.2) drops the loot, the warrior fights
        mobile = max(float(x or 0) for x in (F.get('characterrunspeed') or [1.0])) >= 0.5
        return (((F.get('class') or [''])[0] or '') == 'Monster', ai > 0, mobile, self.drops(F), max(lv), ai, k)

    @staticmethod
    def drops(r):
        """r: a record or a field dict"""
        v = (r.get('dropitems') or [1])[0] if isinstance(r, dict) and 'vars' not in r else get1(r, 'dropItems', 1)
        return str(v) not in ('0', 'False')

    def levels(self, r):
        """[Normal, Epic, Legendary] levels of a record (or field dict); a Legendary-only Eternal Embers record
        ([0, 0, 73]) gets the median vanilla boss gaps below its Legendary level"""
        cl = r.get('charlevel') if isinstance(r, dict) and 'vars' not in r else getv(r, 'charLevel')
        lv = [int(x or 0) for x in (cl or [1])]
        lv = (lv + [lv[-1]] * 3)[:3]
        if lv[0] <= 0 or lv[1] <= 0:
            L = max(lv)
            lv = [max(1, L - GAP_L), max(1, L - GAP_E), L]
        return lv

    def region(self, f):
        keys = sorted(k for k in f['keys'] if self.drops(self.fd(k))) or sorted(f['keys'])
        k = keys[0]
        for d, reg in REGION_DIR:
            if k.startswith(d):
                return reg
        folder = (k.split(BS)[4] if len(k.split(BS)) > 5 else '').lower()       # records\xpack4\creatures\monster\X
        china = any(f['en'].startswith(c) for c in CHINA_EN) or folder in CHINA_DIR
        return '5_jadeemperor' if china else '6_thebes'

    # ------------------------------------------------------------------ drop sources (planned before building)
    def misc_room(self, r, p):
        """slot for one more Misc entry worth p % per kill: ('own', n) a slot holding our eidolon shard, ('free', n),
        ('share', n) a vanilla slot whose chance leaves room; None"""
        ours = self.b_ours()
        slots, odd = misc_slots(r)
        for n in (1, 2, 3):
            if any(any(x in ours for x in it) for it in slots[n]) and n not in odd:
                if sum(slots[n].values()) + p <= 100.0:
                    return ('own', n)
        n = self.b_free(r)
        if n is not None:
            return ('free', n)
        F = fields(r)
        for n in (1, 2, 3):
            if n in odd or not slots[n]:
                continue
            items = sum(1 for j in range(1, 7) if any(F.get('lootmisc%ditem%d' % (n, j)) or []))
            stray = any(float((F.get('chancetoequipmisc%ditem%d' % (n, j)) or [0])[0] or 0) and
                        not any(F.get('lootmisc%ditem%d' % (n, j)) or []) for j in range(1, 7))
            if items < 6 and not stray and sum(slots[n].values()) + p <= 100.0:
                return ('share', n)
        return None

    def plan(self, f):
        """drop sources of a family. Whether a soul is BUILT must not depend on TQTogether.ini (a soul in a save
        points at its records; Souls=0 or a chance set to 0 must not delete them): sources are found with the
        default chances; the configured chance is what place() puts in"""
        st = self.st
        dflt = dict(DEFAULTS)
        pct = st['soulbosschance'] if f['kind'] == 'boss' else st['soulherochance']
        pct0 = dflt['soulbosschance'] if f['kind'] == 'boss' else dflt['soulherochance']
        src = [k for k in f['keys'] if self.drops(self.fd(k)) and ((self.fd(k).get('class') or [''])[0] or '') in CLASSES]
        # members killed in the same fight (several records of one folder at the same level: the four Honor Guards,
        # Hades' three forms, Tiamat's stages): the chance is per fight. The same boss in another folder is another
        # spawn (Typhon of Act III and of the Underworld).
        # 1.8.1: each record by the size of ITS fight (one family-wide k gave lone records the odds of the biggest
        # group), and the file's level number and side quest are part of the fight: the Exhumed Medjai's _84_a / _87_a
        # / _90_a are three level bands of one boss that all say level 72 (5.3 % instead of 15 %), Ssaquath (sq08) and
        # the high priest (sq09) two quests. Forms and stages share the number (boss_hades_50, boss_hadesform2_50)
        fight = lambda k: (k.rsplit(BS, 1)[0], tuple(self.levels(self.fd(k))), fight_tag(k))
        mult = collections.Counter(fight(k) for k in src)
        k_fight = max(mult.values()) if mult else 1
        per = lambda c, n: 100.0 * (1 - (1 - c / 100.0) ** (1.0 / n)) if c > 0 else 0.0
        p, p0 = per(pct, k_fight), per(pct0, k_fight)
        p_by = {k: per(pct, mult[fight(k)]) for k in src}
        misc = [(k, self.misc_room(self.rec(k), per(pct0, mult[fight(k)]))) for k in src]
        misc = [(k, room) for k, room in misc if room]
        chests = []
        also = next((re.compile(c) for e, c in ARENA_CHEST_EN if f['en'].startswith(e)), None)
        if also is not None:          # 1.6.3: fought where loot on the ground vanishes - the reward orb as well
            chests = sorted(k for k in self.chests() if also.search(k.split(BS)[-1]))
        elif not misc and f['kind'] == 'boss':
            rx = next((re.compile(c) for e, c in CHEST_EN if f['en'].startswith(e)), None)
            if rx:
                chests = sorted(k for k in self.chests() if rx.search(k.split(BS)[-1]))
        # 'orb' decides whether a soul can be built at all (bosses, since 1.6.0 - the set of souls must not change);
        # which souls the orbs actually give is decided in build() (1.7.9: hero monsters, and bosses with no own drop)
        # 1.8.4: a named side-quest monster whose loot has no room (its Misc slots hold the quest's own item at 100 %:
        # the Ancients, the Restless King, Sciron) is built anyway - its soul comes from its land's orbs and Tartarus
        orb = self.region(f) if f['kind'] == 'boss' or f.get('quest') else None
        return {'p': p, 'p_by': p_by, 'k_fight': k_fight, 'fights': dict(mult), 'misc': misc, 'chests': chests,
                'orb': orb, 'region': self.region(f)}

    def dropping(self, kind):
        """the ini lets this kind of soul drop (Souls=1, SoulHeroes=1 for hero monsters)"""
        return bool(self.st['souls']) and (kind == 'boss' or bool(self.st['soulheroes']))

    def chests(self):
        """every FixedItemContainer with loot tables (boss chests and the rest), once: the database is lazy and
        touching all 74k records would unpack them all"""
        if getattr(self, '_chests', None) is None:
            self._chests = []
            for k in self.R:
                if 'container' not in k:
                    continue
                few = getattr(self.R, 'fields', None)
                F = few(k, ('Class', 'tables')) if few else fields(self.peek(k))
                # FixedItemContainerTartarus too: the orb left after Tartarus (1.6.3)
                if ((F.get('class') or [''])[0] or '').startswith('FixedItemContainer') and F.get('tables'):
                    self._chests.append(k)
        return self._chests

    # ------------------------------------------------------------------ build
    def build(self):
        fams = self.families()
        # skip: no skills, cannot move
        live = []
        for f in fams:
            r = self.rec(f['rep'])
            skills = [x for i in range(1, 34) for x in (getv(r, 'skillName%d' % i) or []) if x]
            run = max(float(x or 0) for x in (getv(r, 'characterRunSpeed') or [1.0]))
            if not skills:
                self.report.append((f, None, 'not built: no skills'))
                continue
            if run <= 0.01:
                self.report.append((f, None, 'not built: cannot move'))
                continue
            f['plan'] = self.plan(f)
            pl = f['plan']
            if not (pl['misc'] or pl['chests'] or pl['orb']):
                self.report.append((f, None, 'not built: no drop source (no room in its loot, no chest)'))
                continue
            live.append(f)
        # life corridor around the median boss, at Normal level 0 of the growth curve
        for f in live:
            r = self.rec(f['rep'])
            life = float((getv(r, 'characterLife') or [1000])[0] or 1000)
            f['tough'] = life / grow(LIFE_CURVE, 0, self.levels(r)[0])
        med = median([f['tough'] for f in live if f['kind'] == 'boss'] or [1.0])
        self.median = med
        # names: always the full name with the title, as the game shows the boss ("Тартар, Владыка Бездны"). 1.6.5,
        # owner: the short name only when unique gave "Тартар" next to "Тифон, погибель богов" (two Typhons)
        for f in live:
            f['name'] = {lg: self.full(f, lg) for lg in ('ru', 'en')}
            self.make(f)
        self.power(live)
        self.guard(live)
        self.pace(live)
        n = collections.Counter(f['kind'] for f in live)
        log('  souls: %d bosses, %d hero monsters (hero level %s), %d not built%s' % (
            n['boss'], n['hero'], self.H or 'unknown - their own', len(self.report) - len(live),
            '' if self.st['souls'] else ' - Souls=0: built, but they drop nowhere'))
        # orb tables per region. 1.7.9 (owner 18.10: "the bosses are mightier than heroes - their souls from the bosses
        # themselves, the electrum orbs should give the hero monsters' souls"): the orbs give hero monster souls, and a
        # boss's only when it drops nothing itself and has no chest (Baldr, the three Chaos bosses: their loot is the
        # chaos dungeon's shared chest; Toxeanubis) - without the orbs those could not be had at all
        if self.st['soulorbchance'] > 0:
            by = collections.defaultdict(list)
            for f in live:
                pl = f['plan']
                if f['kind'] == 'hero':
                    reg = pl['region'] if self.dropping('hero') else None
                else:
                    reg = pl['orb'] if self.dropping('boss') and not (pl['misc'] or pl['chests']) else None
                self.ledger['souls'][f['sid']]['orb'] = reg
                if reg:
                    by[reg].append(f['relic'])
            for reg, relics in sorted(by.items()):
                t = self.table(self.ns + 'orb_%s.dbr' % reg, relics, 'souls of the %s electrum orbs' % reg)
                self.orb_entries[reg] = (t['name'], self.st['soulorbchance'])
                self.ledger['orbs'][reg] = {'table': key_of(t['name']), 'relics': sorted(key_of(x) for x in relics),
                                            'pct': self.st['soulorbchance']}
        # 1.8.2 (owner 19.10): the ordinary chests of the Tartarus arenas give a soul of any boss or hero monster -
        # one table of all bosses and one of all heroes, equally likely, so the 78 bosses do not drown among 301 heroes
        self.tartarus_pool = None
        if self.st['soultartaruschance'] > 0:
            halves = []
            for kind, what in (('boss', 'bosses'), ('hero', 'heroes')):
                rel = sorted(f['relic'] for f in live if f['kind'] == kind and self.dropping(kind))
                if rel:
                    halves.append((self.table(self.ns + 'tartarus_%s.dbr' % what, rel,
                                              'souls of all %s for the Tartarus arena chests' % what), rel, what))
            if len(halves) == 1:
                pool = halves[0][0]
            elif halves:
                pool = self.b.clone(RELIC_TABLE_SRC(), self.ns + 'tartarus_souls.dbr')
                pool['vars'] = []
                setv(pool, 'templateName', 'database' + BS + 'Templates' + BS + 'LootMasterTable.tpl')
                setv(pool, 'Class', 'LootMasterTable')
                for i, (t, _rel, _what) in enumerate(halves, 1):
                    setv(pool, 'lootName%d' % i, t['name'])
                    setv(pool, 'lootWeight%d' % i, 100, 0)
                setv(pool, 'FileDescription', 'TQ Together: a soul of any boss or hero monster, bosses and heroes '
                                              'equally likely (Tartarus arena chests)')
            if halves:
                self.tartarus_pool = (pool['name'], sorted(key_of(x) for _t, rel, _w in halves for x in rel),
                                      {what: len(rel) for _t, rel, what in halves})

    def full(self, f, lg):
        t = self.text(f['tag'], lg) or self.text(f['tag'], 'en') or literal(f['tag']) or f['sid']
        return re.sub(r'\s*~\s*', ', ', t.strip(' ~'))

    def table(self, name, relics, what):
        """FixedWeight table: one of relics, equally likely (30 per table, a master table above)"""
        b = self.b
        t = b.clone(RELIC_TABLE_SRC(), name)
        t['vars'] = []
        chunks = [relics[i:i + 30] for i in range(0, len(relics), 30)]
        if len(chunks) == 1:
            setv(t, 'templateName', 'database' + BS + 'Templates' + BS + 'LootItemTable_FixedWeight.tpl')
            setv(t, 'Class', 'LootItemTable_FixedWeight')
            for i, x in enumerate(relics, 1):
                setv(t, 'lootName%d' % i, x)
                setv(t, 'lootWeight%d' % i, 100, 0)
        else:
            setv(t, 'templateName', 'database' + BS + 'Templates' + BS + 'LootMasterTable.tpl')
            setv(t, 'Class', 'LootMasterTable')
            for c, chunk in enumerate(chunks, 1):
                sub = self.table(name[:-4] + '_%d.dbr' % c, chunk, what)
                setv(t, 'lootName%d' % c, sub['name'])
                setv(t, 'lootWeight%d' % c, 100 * len(chunk), 0)
        setv(t, 'FileDescription', 'TQ Together: %s' % what)
        return t

    def make(self, f):
        b, R, st = self.b, self.R, self.st
        sid, kind = f['sid'], f['kind']
        src = self.rec(f['rep'])
        base_lv = self.levels(src)
        H = self.H
        target = [H] * 3 if H else list(base_lv)
        # one shift for every difficulty: from the boss's own Legendary level to the hero's (the pet difficulty pak
        # adds what Epic and Legendary add to every pet)
        T = H or base_lv[2]
        shift = [T - base_lv[2]] * 3
        pet = b.clone(f['rep'], self.ns + '%s_soulpet.dbr' % sid)
        Fs = fields(src)                 # reads from the untouched source: a monster record has ~600 fields
        one = lambda fld, d='': (Fs.get(fld.lower()) or [d])[0]
        notes = []
        cls = one('Class')
        if cls in SPECIAL_CLASS:
            notes.append('engine class %s -> Pet%s' % (cls, '' if f['en'] in SPECIAL_TESTED else ': NOT TESTED in game'))
        setv(pet, 'templateName', 'database' + BS + 'Templates' + BS + 'Pet.tpl')
        setv(pet, 'Class', 'Pet')
        gone = {x.lower() for x in DROP_FIELDS}
        pet['vars'] = [t for t in pet['vars'] if t[0].lower() not in gone and
                       not re.match(r'^(chanceToEquip|loot)(Misc\d|Finger\d)', t[0])]
        setv(pet, 'dropItems', 0, 3)
        # 1.7.6 (owner 18.10): an eidolon's body dissolves when it dies or is dismissed; a soul whose boss just falls
        # (Arachne, Nessus, Talos: no deleteBehavior - the body stays like a slain monster's) or dissolves only on its
        # fight script's cue (DissolveOnCallback - never given to a pet) dissolves like an eidolon. Its own effect stays
        db = (one('deleteBehavior') or '').strip()
        if db in DISSOLVE_NONE:
            setv(pet, 'deleteBehavior', 'Dissolve', 2)
            if not one('dissolveTime', 0):
                setv(pet, 'dissolveTime', DISSOLVE[0], 1)
            if not one('dissolveTexture'):
                setv(pet, 'dissolveTexture', DISSOLVE[1], 2)
            if not any(one(c, 0) for c in ('dissolveColorR', 'dissolveColorG', 'dissolveColorB')):
                for c in ('dissolveColorR', 'dissolveColorG', 'dissolveColorB'):
                    setv(pet, c, DISSOLVE[2], 0)
            notes.append('body dissolves on death like an eidolon\'s (was: %s)' % (db or 'left lying'))
        setv(pet, 'monsterClassification', 'Champion')
        if 'quest' in Fs:
            setv(pet, 'quest', 0)
        if 'displayasquestitem' in Fs:
            setv(pet, 'DisplayAsQuestItem', 0)
        setv(pet, 'controller', b.fast_controller())
        setv(pet, 'controllerAggressive', b.fast_controller('aggressive'))
        setv(pet, 'controllerDefensive', b.fast_controller('defensive'))
        b.copy_fields(PET_PANEL_SRC(), pet, ('showStatusWidgetWhenPet',))
        up, down = ICONS[RACE_ICON.get(one('characterRacialProfile') or '', 'human')]
        setv(pet, 'StatusIcon', up, 2)
        setv(pet, 'StatusIconRed', down, 2)
        for fld, srcrec in (('healSkillDelay', PET_PANEL_SRC()), ('mediumRangeMin', PET_RANGE_SRC()),
                            ('longRangeMin', PET_RANGE_SRC()), ('actorRadius', PET_RANGE_SRC())):
            if not one(fld, 0):
                b.copy_fields(srcrec, pet, (fld,))
        for fld, vt, v in DISTRESS():
            setv(pet, fld, v, vt)
        # size: a boss can be four times a hero; the soul stays at SoulMaxScale, its collision radius at 1.5. A boss
        # that paths as Large (27 of them: Typhon, Talos, the Hydra - their meshes are big at scale 1) is shrunk x0.7
        # more and paths as Medium, so it follows the hero through doors (316 of 341 vanilla pets path as Small)
        sc = float(one('scale', 1.0) or 1.0)
        large = (one('pathingSize') or '') == 'Large'
        new_sc = min(st['soulmaxscale'], sc * (0.7 if large else 1.0))
        if new_sc < sc - 1e-6:
            setv(pet, 'scale', round(new_sc, 3), 1)
            notes.append('scale %.2f -> %.2f%s' % (sc, new_sc, ' (Large boss)' if large else ''))
        if large:
            setv(pet, 'pathingSize', 'Medium', 2)
        rad = float(one('actorRadius', 0) or (get1(pet, 'actorRadius', 0.5) or 0.5))
        if rad > 1.5:
            setv(pet, 'actorRadius', 1.5, 1)
        # 1.6.3: slow giants up to speed by their animations (after the size is final: the root motion scales with it)
        casts = [float(x or 0) for x in (getv(pet, 'characterSpellCastSpeed') or [1.0])]
        if min(casts) < CAST_LINE - 1e-3:
            new_c = [max(x, min(CAST_LINE, x * st['soulspeedmax'])) for x in casts]      # 1.7.3: within SoulSpeedMax
            setv(pet, 'characterSpellCastSpeed', new_c, 1)
            notes.append('cast speed %s -> %s' % ([round(x, 2) for x in casts], [round(x, 2) for x in new_c]))
        # 1.7.0: a creature animated by a table gets its own copy of it - the fixes go where the game reads them
        src_tab = anim_table(R, src)
        anm = None
        if src_tab is not None:
            anm = b.clone(src_tab['name'], self.ns + '%s_soulanm.dbr' % sid)
            setv(anm, 'FileDescription', 'TQ Together soul %s: animations from %s' % (sid, src_tab['name'].split(BS)[-1][:-4]))
            setv(pet, 'charAnimationTableName', anm['name'])
            notes.append('animations from its table %s' % src_tab['name'].split(BS)[-1])
        # 1.7.5: once without the hero's attack / cast pace (what the damage is measured on, basic_dps), once with it
        f['fixes0'] = anim_fixes(pet, src, self.run_line, anm, src_tab, giant=large, speedup=st['soulspeedmax'])
        fixes = anim_fixes(pet, src, self.run_line, anm, src_tab, giant=large, speedup=st['soulspeedmax'],
                           atk_factor=self.atk_factor, cast_factor=self.cast_factor)
        f['fixes'] = fixes
        for spname, old, new, what, in_tab in fixes:                  # up: rounding must not undo it
            if isinstance(new, list):                                 # a stat, per difficulty (1.6.7)
                setv(pet, spname, [math.ceil(x * 1000) / 1000.0 for x in new], 1)
            else:
                setv(anm if in_tab else pet, spname, math.ceil(new * 1000) / 1000.0, 1)
        if fixes:
            notes.append('faster: ' + '; '.join(sorted({x[3] for x in fixes})))
        f['anm'] = anm
        # level and stats: the hero's level. Life: the anchor x how tough this boss is among bosses (in the corridor)
        # x the vanilla growth from level 85 to the hero's (Legendary levels, as Normal-difficulty levels - GAP_L).
        # Mana and attributes: the boss's own, grown from its Legendary level to the hero's along the same curve.
        setv(pet, 'charLevel', target, 0)
        lo, hi = CORRIDOR[kind]
        rel = min(hi, max(lo, f['tough'] / self.median))
        life = LIFE_ANCHOR * rel * grow(LIFE_CURVE, ANCHOR_LEVEL - GAP_L, T - GAP_L) * st['soullife'] / 100.0
        setv(pet, 'characterLife', round(life, 1), 1)
        for fld, curve in STAT_CURVE.items():
            vals = Fs.get(fld.lower())
            if fld == 'characterLife' or not vals:
                continue
            v0 = float(vals[-1] or 0)                  # a per-difficulty array: its Legendary value
            setv(pet, fld, round(v0 * grow(curve, base_lv[0], base_lv[0] + shift[2]), 1), 1)
        if abs(rel - f['tough'] / self.median) > 1e-9:
            notes.append('life x%.2f of the median boss, held at x%.2f' % (f['tough'] / self.median, rel))
        # skills: boss-only passives, missing records and the dying skill out; levels follow the shift
        dying = key_of(one('dyingSkillName') or '')
        kept, out_ = set(), set()
        for i in range(1, 34):
            nm = one('skillName%d' % i)
            if not nm:
                continue
            k = key_of(nm)
            sr = self.rec(k) if k in R else None
            if sr is None or BOSS_ONLY_SKILL.search(k) or k == dying or not (get1(sr, 'Class', '') or ''):
                out_.update(('skillname%d' % i, 'skilllevel%d' % i))
                continue
            if get1(sr, 'Class', '') in ARENA_SKILL_CLASS:               # 1.7.0: works on its arena only
                out_.update(('skillname%d' % i, 'skilllevel%d' % i))
                notes.append('arena skill removed: %s (%s)' % (k.split(BS)[-1], get1(sr, 'Class', '')))
                continue
            kept.add(k)
            lv = [int(x or 0) for x in (Fs.get('skilllevel%d' % i) or [1])]
            lv = (lv + [lv[-1]] * 3)[:3]
            if max(lv[:2]) == 0 and lv[2] > 0 and max(int(x or 0) for x in (Fs.get('charlevel') or [0])[:2]) == 0:
                lv = [max(1, round(lv[2] * 0.4)), max(1, round(lv[2] * 0.7)), lv[2]]     # Legendary-only boss
            mx = int(get1(sr, 'skillMaxLevel', 0) or 0)
            new = []
            for d in range(3):
                if lv[d] <= 0:
                    new.append(0)
                    continue
                x = int(round(lv[d] + SKILL_PER_LEVEL * shift[d]))
                cap = max(mx, lv[d]) if mx else max(x, lv[d])
                new.append(max(1, min(cap, x)))
            setv(pet, 'skillLevel%d' % i, new, 0)
        for fld in AI_NAMES:
            v = one(fld)
            if v and key_of(v) not in kept:
                out_.add(fld.lower())
                if fld.startswith('specialAttack'):
                    out_.update((fld[:-len('SkillName')] + suf).lower() for suf in ('Chance', 'Delay', 'Range', 'Timeout'))
        pet['vars'] = [t for t in pet['vars'] if t[0].lower() not in out_]
        # bosses the engine drives by class (Hades, Cerberus: no AI fields at all) - wired like a companion
        # (a monster with no attack skill but its own buffs swings its weapon by default - left as it is)
        if not any(get1(pet, x, '') for x in AI_NAMES):
            chosen = []
            for i in range(1, 34):
                nm = get1(pet, 'skillName%d' % i, '')
                if not nm:
                    continue
                c = get1(self.rec(key_of(nm)), 'Class', '') or ''
                ro = next((ro for rx, ro in ROLE() if re.search(rx, c)), 'attack' if c.startswith('Skill_') else 'passive')
                if MOD_CLASS().search(c):
                    continue
                lv = getv(pet, 'skillLevel%d' % i) or [1]
                chosen.append((key_of(nm), nm, max(1, int(lv[-1] or 1)), c, ro))
            wired = b.wire_ai(pet, chosen)
            notes.append('AI wired by skill class: %s' % ', '.join(wired) if wired else 'natural attack only, as in the game')
        # 1.7.0: a soul that cannot walk fights from where it stands and keeps to the hero by teleport
        if walks(anim_view(pet, anm)) is False:
            notes.extend(self.stationary(pet, anm))
        notes.extend(self.tidy_ai(pet))
        f['dps'] = self.paced_dps(f, pet, anm, notes)
        f['pet_key'] = key_of(pet['name'])
        name_ru, name_en = f['name']['ru'], f['name']['en']
        # 1.6.1, owner: an ENSLAVED soul - the relic, the summon and the pet's name
        setv(pet, 'description', b.tag('tagTQSoul_%s_pet' % sid, '%s ~ порабощённая душа' % name_ru,
                                       '%s ~ Enslaved Soul' % name_en))
        setv(pet, 'FileDescription', 'TQ Together soul of %s (%s)' % (f['rep'].split(BS)[-1][:-4], kind))
        # summon skill
        call = b.clone(SUMMON_SRC(), self.ns + '%s_soulcall.dbr' % sid)
        setv(call, 'spawnObjects', [pet['name']])
        setv(call, 'FileDescription', 'TQ Together summon soul: %s' % sid)
        delv(call, 'spawnObjectsTimeToLive')
        setv(call, 'petLimit', 1, 0)
        setv(call, 'skillMaxLevel', 1, 0)
        setv(call, 'skillCooldownTime', 60.0 if kind == 'boss' else 40.0, 1)
        setv(call, 'skillManaCost', 200.0 if kind == 'boss' else 120.0, 1)
        b.copy_fields(SUMMON_FX_SRC(), call, ('targetFxPakName',))
        setv(call, 'skillUpBitmapName', CALL_ICON[0])
        setv(call, 'skillDownBitmapName', CALL_ICON[1])
        setv(call, 'skillDisplayName', b.tag('tagTQSoul_%s_skill' % sid, 'Призвать порабощённую душу: %s' % name_ru,
                                             'Summon Enslaved Soul: %s' % name_en))
        setv(call, 'skillBaseDescription', b.tag('tagTQSoul_%s_skilldesc' % sid,
             'Призывает порабощённую душу: %s. Она сражается на твоей стороне — на твоём уровне, со своими '
             'умениями.' % name_ru,
             'Summons the enslaved soul of %s. It fights at your side - at your level, with its own skills.' % name_en))
        # the relic: completion bonus grants the summon
        bon = b.clone(RELIC_BONUS_SRC(), self.ns + '%s_soulbonus.dbr' % sid)
        bon['vars'] = [t for t in bon['vars'] if t[0] in ('templateName', 'Class', 'characterBaseAttackSpeedTag')]
        setv(bon, 'itemSkillName', call['name'])
        setv(bon, 'itemSkillLevel', 1, 0)
        setv(bon, 'FileDescription', 'TQ Together soul bonus: %s' % sid)
        tab = b.clone(RELIC_TABLE_SRC(), self.ns + '%s_soulbonustable.dbr' % sid)
        tab['vars'] = [t for t in tab['vars'] if not t[0].startswith('randomizer')]
        setv(tab, 'randomizerName1', bon['name'])
        setv(tab, 'randomizerWeight1', 100, 0)
        relic = b.clone(RELIC_SRC(), self.ns + '%s_soul.dbr' % sid)
        relic['vars'] = [t for t in relic['vars'] if not t[0].startswith('racialBonus')]
        setv(relic, 'bonusTableName', tab['name'])
        setv(relic, 'shardBitmap', LOOK[kind][0], 2)
        setv(relic, 'relicBitmap', LOOK[kind][1], 2)
        shards = st['soulbossshards'] if kind == 'boss' else st['soulheroshards']
        setv(relic, 'completedRelicLevel', shards, 0)
        for q in RELIC_SLOTS():
            setv(relic, q, 1 if q in SOUL_FITS[kind] else 0, 3)   # BOOL: Game.dll reads these with the bool getter
        setv(relic, 'levelRequirement', 1, 0)
        setv(relic, 'itemCost', [8000, 8000, 8000] if kind == 'boss' else [4000, 4000, 4000], 0)
        what_ru = 'босса' if kind == 'boss' else 'героя'
        where_ru, where_en = ('амулет', 'an amulet') if kind == 'boss' else ('амулет или кольцо', 'an amulet or a ring')
        setv(relic, 'description', b.tag('tagTQSoul_%s_relic' % sid, 'Порабощённая душа: %s' % name_ru,
                                         'Enslaved Soul: %s' % name_en))
        setv(relic, 'itemText', b.tag('tagTQSoul_%s_relictext' % sid,
             'Частица порабощённой души %s: %s. Собери %d и вложи в %s — и душа будет сражаться за тебя, '
             'становясь сильнее вместе с тобой.' % (what_ru, self.full(f, 'ru'), shards, where_ru),
             'A shard of the enslaved soul of %s. Join %d and set them into %s - the soul will fight for you '
             'and grow with you.' % (self.full(f, 'en'), shards, where_en)))
        setv(relic, 'FileDescription', 'TQ Together soul relic: %s' % sid)
        shard_t = self.table(self.ns + '%s_soulshard.dbr' % sid, [relic['name']], 'one shard of soul %s' % sid)
        f['relic'], f['shard_table'] = relic['name'], shard_t['name']
        self.ledger['souls'][sid] = {'kind': kind, 'en': f['en'], 'rep': f['rep'], 'pet': key_of(pet['name']),
                                     'call': key_of(call['name']), 'relic': key_of(relic['name']),
                                     'shard_table': key_of(shard_t['name']), 'shards': shards, 'sources': [],
                                     'orb': f['plan']['orb'], 'life': getv(pet, 'characterLife'),
                                     'level': target, 'notes': notes, 'giant': large,
                                     'anm': key_of(anm['name']) if anm is not None else ''}
        self.report.append((f, pet, notes))

    # ------------------------------------------------------------------ 1.7.0: fighting where it stands, damage
    def paced_dps(self, f, pet, anm, notes):
        """1.7.5: the soul strikes with the hero's pace (anim_fixes atk_factor / cast_factor); its damage per second
        stays what it was at its own pace (owner 18.10: the damage is right - only the slow boss "gets little done"
        next to a fast hero): the hand hit is lightened by as much as the strikes were sped up. -> basic_dps at its own
        pace (SoulDamage is measured on it); skills keep their damage per cast and only wind up faster"""
        import copy
        pak, eq = self.pak()[2], self.phys_eq()
        wpn = weapon_hit(self.R, pet)          # 1.8.3: a soul with a weapon strikes with it
        f['weapon'] = wpn
        dps = basic_dps(pet, anm, pak, eq, wpn)
        if dps <= 0 or (self.atk_factor <= 1.0 + 1e-9 and self.cast_factor <= 1.0 + 1e-9):
            return dps
        p0, a0 = copy.deepcopy(pet), copy.deepcopy(anm) if anm is not None else None
        for fixes, pick in ((f['fixes'], 1), (f['fixes0'], 2)):      # undo the paced fixes, apply the plain ones
            for spname, old, new, what, in_tab in fixes:
                v = old if pick == 1 else new
                up = (lambda x: math.ceil(x * 1000) / 1000.0) if pick == 2 else (lambda x: x)   # as make() rounds
                if isinstance(v, list):
                    setv(p0, spname, [up(x) for x in v], 1)
                else:
                    setv(a0 if in_tab else p0, spname, up(v), 1)
        dps0 = basic_dps(p0, a0, pak, eq, wpn)
        if dps0 <= 0 or dps <= dps0 * 1.001:
            return dps0 or dps
        if wpn[0] > 0:
            # 1.8.3: a weapon cannot be made lighter for one soul (its item is the game's) - the soul's damage factor
            # takes the speed-up back instead (power(): factor x pace_r)
            f['pace_r'] = dps0 / dps
            notes.append('pace with the hero: strikes x%g, casts x%g (within SoulSpeedMax); fights with a weapon - '
                         'damage factor x%.2f so its damage per second stays as at its own pace' % (
                             self.atk_factor, self.cast_factor, f['pace_r']))
            return dps0
        hands = [(fld, [float(x or 0) for x in getv(pet, fld) or []]) for fld in ('handHitDamageMin', 'handHitDamageMax')]
        r = 1.0
        for _ in range(4):               # damage = (hand x a + b) / time: a few steps to land on dps0
            r *= dps0 / max(basic_dps(pet, anm, pak, eq), 1e-9)
            for fld, vals in hands:
                setv(pet, fld, [round(x * r, 1) for x in vals], 1)
        notes.append('pace with the hero: strikes x%g, casts x%g (within SoulSpeedMax); hand hit x%.2f - damage per '
                     'second as at its own pace' % (self.atk_factor, self.cast_factor, r))
        return dps0

    def tidy_ai(self, pet):
        """1.7.7: no special fired at distances it does not reach, none wired twice for the same distances -> notes"""
        notes = []
        for fx in ai_fixes(self.R, pet):
            if fx[0] == 'range':
                _, sl, old, new, sk, reach = fx
                setv(pet, sl + 'Range', new, 2)
                notes.append('AI: %s %s -> %s (it reaches %g m)' % (sk.split(BS)[-1], old, new, reach))
            else:
                _, sl, kept, sk, dl, kdl = fx
                for suf in ('SkillName', 'Chance', 'Delay', 'Range', 'Timeout'):
                    delv(pet, sl + suf)
                notes.append('AI: %s wired twice for the same distances - %s (delay %g s) kept, %s (delay %g s) out'
                             % (sk.split(BS)[-1], kept, kdl, sl, dl))
        return notes

    def stationary(self, pet, anm):
        """a soul whose run does not move it: a ranged basic attack of its own body, its old basic attack (a wave on a
        cooldown) moved into the special slot of a skill its body has no animation for, a short leash -> notes"""
        b = self.b
        view = anim_view(pet, anm)
        refs = {v[0].lower() for low, (n, v) in view.items() if re.search(r'SpecialAnimRef\d*$', n) and v and v[0]}
        out = []
        for ref, skill in STATIC_ATTACK:
            if ref not in refs or key_of(skill) not in self.R:
                continue
            old = get1(pet, 'attackSkillName', '') or ''
            if key_of(old) == key_of(skill):
                break
            if not any(key_of(get1(pet, 'skillName%d' % i, '') or '') == key_of(skill) for i in range(1, 34)):
                free = next((i for i in range(1, 34) if not get1(pet, 'skillName%d' % i, '')), None)
                if free is None:
                    break
                setv(pet, 'skillName%d' % free, skill)
                setv(pet, 'skillLevel%d' % free, [1, 1, 1], 0)
            setv(pet, 'attackSkillName', skill)
            out.append('cannot walk: basic attack %s (was %s)' % (skill.split(BS)[-1], old.split(BS)[-1] or 'none'))
            if old:
                slots = ['specialAttack'] + ['specialAttack%d' % n for n in range(2, 6)]
                mute = lambda s: (get1(self.R.get(key_of(get1(pet, s + 'SkillName', '') or '')) or {'vars': []},
                                       'skillSpecialAnimationName', '') or '').lower()
                slot = next((s for s in slots if get1(pet, s + 'SkillName', '') and mute(s) and mute(s) not in refs),
                            None) or next((s for s in slots if not get1(pet, s + 'SkillName', '')), None)
                if slot is not None:
                    was = get1(pet, slot + 'SkillName', '') or ''
                    setv(pet, slot + 'SkillName', old)
                    setv(pet, slot + 'Range', 'AnyRange', 2)
                    if not get1(pet, slot + 'Chance', 0):
                        setv(pet, slot + 'Chance', 30.0, 1)
                    out.append('cannot walk: %s -> %s at any range (instead of %s, no animation for it)' % (
                        old.split(BS)[-1], slot, was.split(BS)[-1] or 'nothing'))
            break
        for fld, kind in (('controller', ''), ('controllerAggressive', 'aggressive'), ('controllerDefensive', 'defensive')):
            setv(pet, fld, self.static_controller(kind))
        out.append('cannot walk: teleports to the hero beyond %g m' % STATIC_TELEPORT)
        return out

    def static_controller(self, kind=''):
        """the companion controller of that stance with a short leash (STATIC_TELEPORT)"""
        b = self.b
        name = self.ns + 'controller_static%s.dbr' % ('_' + kind if kind else '')
        if self.R.get(key_of(name)) is None:
            src = b.fast_controller(kind or 'normal')
            c = b.clone(self.R[key_of(src)]['name'], name)
            setv(c, 'TeleportToLeaderDistance', STATIC_TELEPORT, 1)
            setv(c, 'FileDescription', 'TQ Together soul that cannot walk: %s companion controller, teleports at %g m'
                 % (kind or 'normal', STATIC_TELEPORT))
        return name

    def pak(self):
        """[{field: %}] of the pet difficulty pak for one player on Normal, Epic, Legendary (index 6 x difficulty)"""
        if getattr(self, '_pak', None) is None:
            r = self.R.get(key_of(PET_PAK))
            self._pak = [{vn: float(vals[min(6 * d, len(vals) - 1)]) for vn, vt, vals in (r['vars'] if r else [])
                          if vt in (0, 1) and vals} for d in range(3)]
        return self._pak

    def phys_eq(self):
        r = self.R.get(key_of(COMBAT_EQ))
        return (get1(r, 'physicalDamageEquation', '') or 'physicalDamageDV') if r is not None else 'physicalDamageDV'

    def power(self, live):
        """SoulDamage: one damage factor for every soul from the hero's character-window DPS (DAMAGE_FIELDS)"""
        import build_companions as B
        hero = float(getattr(B, 'HERO_DPS', 0) or 0)
        share = self.st['souldamage']
        dps = [f['dps'] for f in live if f['kind'] == 'boss' and f.get('dps', 0) > 0]
        med = median(dps) if dps else 0.0
        m = 1.0
        if share > 0 and hero > 0 and med > 0:
            m = float('%.2g' % max(1.0, min(DAMAGE_MAX, share / 100.0 * hero / med)))
        self.ledger['damage'] = {'hero_dps': round(hero), 'median_soul_dps': round(med, 1), 'share': share, 'factor': m}
        log('  souls: damage x%g (SoulDamage %g%% of the hero\'s %.0f DPS, the median boss soul\'s basic attack %.0f)'
            % (m, share, hero, med))
        if m <= 1.0 + 1e-9:
            return
        shared = None
        for f in live:
            # the hardest hitters are held like life (CORRIDOR): a boss's basic attack at most 1.5 x the median soul's,
            # a hero monster's 1.0 x - Cerberus' bite (x3.5 the median) would hit harder than the hero himself. No
            # floor: Arachne's hand is weak by design, her poison and her spiders do the work.
            # 1.8.3: dps counts the weapon a soul fights with; pace_r (a weapon soul striking at the hero's pace) is
            # taken off the factor - the hand of such a soul was lightened, its weapon never was
            hi = CORRIDOR[f['kind']][1]
            mi = m
            if f.get('dps', 0) > hi * med:
                mi = m * hi * med / f['dps']
            pr = f.get('pace_r', 1.0)
            # rounded once and DOWN to two digits when held: rounding twice to nearest let one soul past its corridor
            me = m if abs(mi * pr - m) < 1e-9 else max(1.0, floor2(mi * pr))
            if abs(me - m) < 1e-9:
                shared = shared or self.power_record(self.ns + 'soul_power.dbr', m)
                r = shared
            else:
                r = self.power_record(self.ns + '%s_soulpower.dbr' % f['sid'], me)
            s = self.ledger['souls'][f['sid']]
            s['basic'], s['pace_r'] = round(f.get('dps', 0), 2), round(pr, 4)
            if not self.add_skill(f, r):
                s['notes'].append('no free skill slot: damage not raised')
                continue
            s['power'], s['damage'] = key_of(r['name']), me
            s['notes'].append('damage x%g: basic attack ~%.0f per second (%.0f%% of the hero\'s)%s%s%s' % (
                me, f.get('dps', 0) * mi, 100.0 * f.get('dps', 0) * mi / hero,
                ' with its weapon' if (f.get('weapon') or (0, 0))[0] > 0 else '',
                ', held at x%.1f the median soul\'s' % hi if mi < m - 1e-9 else '',
                ', x%.3g before the pace with the hero' % mi if abs(me - mi) > 1e-9 else ''))

    def passive(self, name):
        """an empty Skill_Passive of ours (the builder's plain passive with every stat taken out, weapon flags kept: it
        is active with any weapon)"""
        import build_companions as B
        r = self.b.clone(self.R[key_of(B.PASSIVE_SRC)]['name'], name)
        for vn, vt, vals in list(r['vars']):
            if B.STAT_FIELD.match(vn) and (not vn.startswith('skill') or re.match(r'^skill(Cooldown|ManaCost|Projectile)', vn)):
                delv(r, vn)
        return r

    def add_skill(self, f, r, levels=(1, 2, 3)):
        """r into the soul's first free skill slot -> False if it has none"""
        pet = self.R[f['pet_key']]
        free = next((i for i in range(1, 34) if not get1(pet, 'skillName%d' % i, '')), None)
        if free is None:
            return False
        setv(pet, 'skillName%d' % free, r['name'])
        setv(pet, 'skillLevel%d' % free, list(levels), 0)
        return True

    def guard(self, live):
        """1.7.4: the hero difficulty (Difficulty=power) makes the monsters' Legendary damage and accuracy HERO_DAMAGE
        times the game's; the souls answer with life and defence on Legendary (levels 1/2/3 = Normal/Epic/Legendary,
        the builder scales the Legendary entries only): life +(HD - 1) x (100 + the pet pak's %), defence + the
        accuracy the monsters gained - a monster's blow lands on a soul as in vanilla Legendary"""
        import build_companions as B
        hd = float(getattr(B, 'HERO_DAMAGE', 1.0) or 1.0)
        self.ledger['guard'] = {'hero_damage': hd}
        if hd <= 1.0 + 1e-9:
            return
        ge = self.R.get(key_of(B.GAP_SRC))
        mp = self.R.get(key_of(get1(ge, 'monsterAttributePak', '') or '')) if ge is not None else None
        oa = getv(mp, 'characterOffensiveAbility') if mp is not None else None
        oa_l = float(oa[min(12, len(oa) - 1)] or 0) if oa else 0.0          # already x HD (Builder.hero_life)
        da = round(oa_l * (1 - 1 / hd), 1)
        life = round((hd - 1) * (100.0 + self.pak()[2].get('characterLifeModifier', 0.0)), 1)
        r = self.passive(self.ns + 'soul_guard.dbr')
        setv(r, 'characterLifeModifier', [0.0, 0.0, life], 1)
        setv(r, 'characterDefensiveAbility', [0.0, 0.0, da], 1)
        setv(r, 'skillMaxLevel', 3, 0)
        setv(r, 'FileDescription', 'TQ Together soul guard: monsters hit x%g on Legendary - life +%g %%, defence +%g'
             % (hd, life, da))
        self.ledger['guard'].update(life_pct=life, da=da, skill=key_of(r['name']))
        log('  souls: guard against the hero difficulty (monster damage x%g on Legendary): life +%g%%, defence +%g'
            % (hd, life, da))
        for f in live:
            s = self.ledger['souls'][f['sid']]
            if self.add_skill(f, r):
                s['guard'] = key_of(r['name'])
            else:
                s['notes'].append('no free skill slot: no guard against the hero difficulty')

    def pace(self, live):
        """1.7.5: the projectile speed the game gives every monster and boss on Epic / Legendary (+10 / +20 %, monster
        pak skillProjectileSpeedModifier) and not pets - the soul's projectiles flew a fifth slower than its boss's"""
        import build_companions as B
        ge = self.R.get(key_of(B.GAP_SRC))
        mp = self.R.get(key_of(get1(ge, 'monsterAttributePak', '') or '')) if ge is not None else None
        sp = getv(mp, 'skillProjectileSpeedModifier') if mp is not None else None
        vals = [float(sp[min(6 * d, len(sp) - 1)] or 0) for d in range(3)] if sp else [0.0, 0.0, 0.0]
        self.ledger['pace'] = {'projectile': vals}
        if not any(vals):
            return
        r = self.passive(self.ns + 'soul_pace.dbr')
        setv(r, 'skillProjectileSpeedModifier', vals, 1)
        setv(r, 'skillMaxLevel', 3, 0)
        setv(r, 'FileDescription', 'TQ Together soul pace: projectile speed as a monster\'s, %s %% by difficulty' % vals)
        self.ledger['pace']['skill'] = key_of(r['name'])
        for f in live:
            if self.add_skill(f, r):
                self.ledger['souls'][f['sid']]['pace'] = key_of(r['name'])
            else:
                self.ledger['souls'][f['sid']]['notes'].append('no free skill slot: projectiles at the pet speed')

    def power_record(self, name, m):
        """Skill_Passive: every damage modifier +(m - 1) x (100 + the pet pak's %) at levels 1/2/3 = Normal/Epic/Legendary"""
        r = self.passive(name)
        pak = self.pak()
        for fld in DAMAGE_FIELDS:
            setv(r, fld, [round((m - 1.0) * (100.0 + pak[d].get(fld, 0.0)), 1) for d in range(3)], 1)
        setv(r, 'skillMaxLevel', 3, 0)
        setv(r, 'FileDescription', 'TQ Together soul power: damage x%g (levels 1/2/3 = Normal/Epic/Legendary)' % m)
        return r

    # ------------------------------------------------------------------ drops (after Builder.eidolon_drops)
    def place(self):
        b, R = self.b, self.R
        n_misc = 0
        by_chest = collections.defaultdict(list)
        for sid, s in self.ledger['souls'].items():
            f = next(x for x, pet, notes in self.report if pet is not None and x['sid'] == sid)
            pl = f['plan']
            if not self.dropping(s['kind']):
                continue
            for k, _ in (pl['misc'] if pl['p'] > 0 else []):
                r = R[k]
                p = pl['p_by'][k]                       # 1.8.1: the odds of this record's own fight
                room = self.misc_room(r, p)             # re-checked: the eidolon shard may have taken the free slot
                if room is None:
                    continue
                self.add_misc(r, room[1], s['shard_table'], p)
                self.ledger['misc'].setdefault(k, {})[s['shard_table']] = p
                s['sources'].append('kill %s %.1f%% (%s slot %d)' % (k.split(BS)[-1], p, room[0], room[1]))
                n_misc += 1
            for ck in (pl['chests'] if self.st['soulchestchance'] > 0 else []):
                by_chest[ck].append((s['shard_table'], self.st['soulchestchance']))
                s['sources'].append('chest %s %g%%' % (ck.split(BS)[-1], self.st['soulchestchance']))
            if s['orb'] and s['orb'] in self.ledger['orbs']:
                s['sources'].append('electrum orbs %s %g%%' % (s['orb'], self.st['soulorbchance']))
        # a chest shared by several souls (the Aesir, Loki and Ylva) gets them in ONE addition: added one after the
        # other, the second would dilute the first one's odds
        for ck, entries in sorted(by_chest.items()):
            self.add_chest(ck, entries)
        # 1.8.2: every ordinary chest of the Tartarus arenas (common, infrequent, rare; all difficulties), its count
        # equations raised so the vanilla items (mostly potions) stay as many as the rounding allows
        n_tart = 0
        if getattr(self, 'tartarus_pool', None):
            pool, relics, sizes = self.tartarus_pool
            pct = self.st['soultartaruschance']
            for ck in sorted(k for k in self.chests() if TARTARUS_ARENA_CHEST.search(k.split(BS)[-1])):
                self.add_chest(ck, [(pool, pct)], targets={key_of(pool): relics})
                n_tart += 1
            if n_tart:
                inpool = set(relics)
                for sid, s in self.ledger['souls'].items():
                    if s['relic'] in inpool:
                        n = sizes['bosses' if s['kind'] == 'boss' else 'heroes']
                        s['sources'].append('Tartarus arena chests %g%% (one of %d %s, half the chance)' % (
                            pct, n, 'bosses' if s['kind'] == 'boss' else 'heroes'))
        log('  souls drop from %d monster records, %d boss chests, electrum orbs of %d regions, %d Tartarus arena '
            'chests' % (n_misc, len(by_chest), len(self.ledger['orbs']), n_tart))
        shop = [x.strip() for x in self.st['soultestshop'].split(',') if x.strip()]
        if shop:
            relics = [s['relic'] for sid, s in self.ledger['souls'].items()
                      if any(w in s['en'] or w in sid for w in shop)]
            if relics:
                b.sell([R[k]['name'] for k in relics])
                log('  TEST: soul shards on sale at the ring merchants: %s' % ', '.join(
                    self.ledger['souls'][k.split(BS)[-1][:-len('_soul.dbr')]]['en'] for k in relics))
        self.write_report()

    def add_misc(self, r, n, table, p):
        """one more entry worth p % per kill in Misc slot n; every entry already there keeps its % exactly
        (chance += p, weights rewritten as probabilities); weights without an item are cleared"""
        slots, _ = misc_slots(r)
        ents = [(it, q) for it, q in slots[n].items()]
        names = {}
        for j in range(1, 7):
            it = [x for x in (getv(r, 'lootMisc%dItem%d' % (n, j)) or []) if x]
            if it:      # 1.8.1: an item named twice keeps its summed % in its first entry
                names.setdefault(tuple(key_of(x) for x in it), (j, getv(r, 'lootMisc%dItem%d' % (n, j))))
        c2 = sum(q for _, q in ents) + p
        if c2 > 100.0 + 1e-9:
            raise ValueError('no room in Misc %d of %s' % (n, r['name']))
        free_j = [j for j in range(1, 7) if not any(getv(r, 'lootMisc%dItem%d' % (n, j)) or [])]
        for j in range(1, 7):
            setv(r, 'chanceToEquipMisc%dItem%d' % (n, j), 0, 0)
        for it, q in ents:
            j, _ = names[it]
            setv(r, 'chanceToEquipMisc%dItem%d' % (n, j), max(1, int(round(q / c2 * MISC_W))) if q > 0 else 0, 0)
        j = free_j[0]
        setv(r, 'lootMisc%dItem%d' % (n, j), table)
        setv(r, 'chanceToEquipMisc%dItem%d' % (n, j), max(1, int(round(p / c2 * MISC_W))), 0)
        setv(r, 'chanceToEquipMisc%d' % n, c2, 1)
        self.b.db.mark(r['name'])

    def add_chest(self, ck, entries, targets=None):
        """the chest's loot tables are shared with other chests: our own copy per chest, every soul shard added with
        its % per opening (Builder.add_shards: vanilla entries keep their odds). targets {table: [relics]} for a table
        that is not one soul's shard table (1.8.2: the Tartarus pool of all souls)"""
        b, R = self.b, self.R
        chest = R[ck]
        tabs = getv(chest, 'tables') or []
        new = []
        for i, t in enumerate(tabs):
            name = self.ns + 'chest_%s_%d.dbr' % (hashlib.md5(ck.encode('utf-8')).hexdigest()[:10], i)
            cp = b.clone(key_of(t), name)
            if not b.add_shards(cp, entries):
                log('  WARNING: no room for a soul in %s' % t)
            new.append(cp['name'])
        setv(chest, 'tables', new)
        b.db.mark(chest['name'])
        self.ledger['chests'][ck] = {'tables': [key_of(x) for x in new], 'orig': [key_of(x) for x in tabs],
                                     'souls': {key_of(t): pct for t, pct in entries}, 'targets': targets or {}}

    # ------------------------------------------------------------------ helpers into build_companions
    def b_ours(self):
        return {key_of(b_ns() + 'eidolon_shards.dbr')} | {s['shard_table'] for s in self.ledger['souls'].values()}

    def b_free(self, r):
        import build_companions as B
        return B.free_misc_slot(r)

    def write_report(self):
        out = os.path.join(OUT(), 'souls.txt')
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write('Souls (TQ Together %s), hero level %s, median boss life at Normal level 0: %.0f\n' % (
                paths.VERSION, self.H or 'unknown', getattr(self, 'median', 0)))
            for f, pet, notes in sorted(self.report, key=lambda x: (x[0]['kind'], x[0]['en'])):
                if pet is None:
                    fh.write('-- %-5s %-45s %s\n' % (f['kind'], f['en'][:45], notes))
                    continue
                s = self.ledger['souls'][f['sid']]
                fh.write('== %-5s %-45s %s  life %s  level %s\n' % (
                    f['kind'], f['en'][:45], f['sid'], [int(x) for x in s['life'] or []], s['level']))
                fh.write('     from %s\n' % f['rep'])
                for x in s['sources']:
                    fh.write('     drop: %s\n' % x)
                for x in notes:
                    fh.write('     note: %s\n' % x)


# late imports from build_companions (it imports this module)
def _B():
    import build_companions as B
    return B


def log(*a):
    _B().log(*a)


def b_ns():
    return _B().NS


def OUT():
    return _B().OUT


def RELIC_TABLE_SRC():
    return _B().RELIC_TABLE_SRC


def RELIC_SRC():
    return _B().RELIC_SRC


def RELIC_BONUS_SRC():
    return _B().RELIC_BONUS_SRC


def RELIC_SLOTS():
    return _B().RELIC_SLOTS


def SUMMON_SRC():
    return _B().SUMMON_SRC


def SUMMON_FX_SRC():
    return _B().SUMMON_FX_SRC


def PET_PANEL_SRC():
    return _B().PET_PANEL_SRC


def PET_RANGE_SRC():
    return _B().PET_RANGE_SRC


def DISTRESS():
    return _B().DISTRESS


def ROLE():
    return _B().ROLE


def MOD_CLASS():
    return _B().MOD_CLASS


def fingerprint():
    import build_companions as B
    return json.dumps({'souls': settings(), 'level': B.HERO_LEVEL, 'dps': round(float(getattr(B, 'HERO_DPS', 0) or 0)),
                       'v': '1.8.0'}, sort_keys=True)


# ---------------------------------------------------------------------- self-check
def vanilla_kept(what, R, nf, oR, of, planned=None):
    """1.8.1: problems if the vanilla entries of a loot table we changed (fields nf; as it was: of in oR) do not all
    keep their expected number per opening times ONE factor, or that factor is not what the build planned
    (build_companions.add_shards, Builder.loot_counts). How far it is from 1 depends on the chances in the ini and
    on whether the table has count equations (the Tartarus orb has none): a factor outside VANILLA_KEPT is logged,
    it does not stop the install"""
    import build_companions as B
    fac = orb_odds.vanilla_factors(R, nf, oR, of)
    if not fac:
        return []
    lo, hi = min(fac.values()), max(fac.values())
    if hi - lo > 1e-6 * hi:
        (s_, x), _ = min(fac.items(), key=lambda kv: kv[1])
        return ['%s: vanilla entries changed unevenly (x%.5f .. x%.5f, e.g. slot %d %s)' % (
            what, lo, hi, s_, x.split(BS)[-1])]
    if planned is not None and abs(lo - planned) > 1e-3:
        return ['%s: vanilla items per opening x%.4f, the build planned x%.4f' % (what, lo, planned)]
    if planned is None and not 0.5 <= lo <= 1.5:
        return ['%s: vanilla items per opening x%.3f' % (what, lo)]
    VANILLA_SEEN.append(lo)
    if not B.VANILLA_KEPT[0] <= lo <= B.VANILLA_KEPT[1]:
        VANILLA_FAR.append('%s x%.3f' % (what, lo))
    return []


VANILLA_SEEN = []      # factors vanilla_kept passed (for the log line)
VANILLA_FAR = []       # ... and those outside build_companions.VANILLA_KEPT (logged as a note)


def check(R, baseR, ledger, log=print):
    """-> problems. Pets as Class Pet without boss leftovers, chain relic -> bonus -> summon -> pet, amulet only, every
    soul obtainable, kill / chest / orb odds as planned and every vanilla entry's odds unchanged."""
    import build_companions as B
    bad = []
    if not ledger:
        return bad
    st = ledger['settings']
    ctl = {key_of(B.NS + 'controller_companion.dbr'), key_of(B.NS + 'controller_companion_aggressive.dbr'),
           key_of(B.NS + 'controller_companion_defensive.dbr')}
    ctl |= {key_of(B.NS + SUB + 'controller_static%s.dbr' % k) for k in ('', '_aggressive', '_defensive')}
    dmg = ledger.get('damage') or {}
    gd = ledger.get('guard') or {}
    for sid, s in ledger['souls'].items():
        pet = R.get(s['pet'])
        if pet is None:
            bad.append('soul %s: pet record missing' % sid)
            continue
        g = lambda f, d='': get1(pet, f, d)
        if g('Class') != 'Pet' or not (g('templateName') or '').lower().endswith('pet.tpl'):
            bad.append('soul %s: Class %s / %s, want Pet' % (sid, g('Class'), g('templateName')))
        if g('showStatusWidgetWhenPet') != 1 or not g('StatusIcon') or not g('StatusIconRed'):
            bad.append('soul %s: pet panel fields missing' % sid)
        if not (g('mediumRangeMin') and g('longRangeMin') and g('actorRadius')):
            bad.append('soul %s: AI range classes / actorRadius missing' % sid)
        vals = getv(pet, 'dropItems')
        vt = next((t for vn, t, v in pet['vars'] if vn == 'dropItems'), None)
        if vals != [0] or vt != 3:
            bad.append('soul %s: dropItems %s type %s, want 0 as bool' % (sid, vals, vt))
        for fld in DROP_FIELDS:
            if getv(pet, fld):
                bad.append('soul %s: boss leftover %s' % (sid, fld))
        # 1.6.2: nothing put down on death (the Tartarus soul left its reward orb). 1.6.3: no animation slower than the
        # lines (run on the ground, attack, skill) - anim_fixes finds nothing left to speed up
        for vn, vt_, v in pet['vars']:
            if re.search(r'proxy|treasure|OnDeath|DropItemName', vn, re.I) and any(isinstance(x, str) and x for x in v):
                bad.append('soul %s: %s=%s would be put down on death' % (sid, vn, v[0]))
        rep = (R.peek(s['rep']) if hasattr(R, 'peek') else R.get(s['rep'])) if s['rep'] in R else None
        # 1.7.0: a soul animated by a table has its own copy of it, and is checked on it
        rep_tab = anim_table(R, rep) if rep is not None else None
        tab = anim_table(R, pet)
        if (rep_tab is None) != (tab is None) or (tab is not None and key_of(tab['name']) != s.get('anm')):
            bad.append('soul %s: animation table %s, want its own copy of %s' % (
                sid, tab and tab['name'], rep_tab and rep_tab['name']))
        up = st.get('soulspeedmax', SPEEDUP_MAX)
        left = anim_fixes(pet, rep, ledger.get('run_line', RUN_LINE), tab, rep_tab, giant=s.get('giant', False),
                          speedup=up, atk_factor=ledger.get('atk_factor', 1.0), cast_factor=ledger.get('cast_factor', 1.0))
        cast0 = min(float(x or 0) for x in (getv(rep, 'characterSpellCastSpeed') or [1.0])) if rep is not None else CAST_LINE
        if min(float(x or 0) for x in (getv(pet, 'characterSpellCastSpeed') or [1.0])) < min(CAST_LINE, cast0 * up) - 1e-3:
            left = left + [('', 0, 0, 'cast speed %s' % getv(pet, 'characterSpellCastSpeed'), False)]
        if left:
            bad.append('soul %s: still slow - %s' % (sid, '; '.join(x[3] for x in left[:3])))
        # 1.7.3: and none faster than SoulSpeedMax x the boss's own (auras come on top)
        fast = [(r, n) for r, n in speedups(pet, rep, tab, rep_tab) if r > up + 0.01] if rep is not None else []
        if fast:
            bad.append('soul %s: plays %s x%.2f its own, above SoulSpeedMax %g' % (sid, max(fast)[1], max(fast)[0], up))
        if g('monsterClassification') == 'Boss':
            bad.append('soul %s: still classified Boss' % sid)
        for vn, vt_, v in pet['vars']:
            if re.match(r'^(chanceToEquip|loot)(Misc|Finger)', vn) and any(x not in (0, 0.0, '') for x in v):
                bad.append('soul %s: loot field %s left' % (sid, vn))
                break
        own = set()
        for i in range(1, 34):
            nm = g('skillName%d' % i)
            if nm:
                k = key_of(nm)
                own.add(k)
                if k not in R:
                    bad.append('soul %s: skill %s missing' % (sid, nm))
                if BOSS_ONLY_SKILL.search(k):
                    bad.append('soul %s: boss-only skill %s left' % (sid, k.split(BS)[-1]))
                if k in R and get1(R[k], 'Class', '') in ARENA_SKILL_CLASS:
                    bad.append('soul %s: arena skill %s left' % (sid, k.split(BS)[-1]))
                lv = getv(pet, 'skillLevel%d' % i) or []
                if len(lv) != 3:
                    bad.append('soul %s: skillLevel%d %s not per difficulty' % (sid, i, lv))
        for fld in AI_NAMES:
            v = g(fld)
            if v and key_of(v) not in own:
                bad.append('soul %s: %s=%s is not in its skill list' % (sid, fld, v.split(BS)[-1]))
        for fld in ('controller', 'controllerAggressive', 'controllerDefensive'):
            if key_of(g(fld) or '') not in ctl:
                bad.append('soul %s: %s %s is not ours' % (sid, fld, g(fld)))
        lv = [int(x) for x in getv(pet, 'charLevel') or []]
        if len(lv) != 3 or (ledger.get('hero_level') and lv != [ledger['hero_level']] * 3):
            bad.append('soul %s: charLevel %s, want the hero level %s on every difficulty' % (sid, lv, ledger.get('hero_level')))
        if float(g('scale', 1.0) or 1.0) > st['soulmaxscale'] + 1e-6 or float(g('actorRadius', 0) or 0) > 1.5 + 1e-6:
            bad.append('soul %s: scale %s / radius %s above the caps' % (sid, g('scale'), g('actorRadius')))
        life = getv(pet, 'characterLife') or []
        if len(life) != 1 or life[0] <= 0:
            bad.append('soul %s: characterLife %s - want one positive value, like the game\'s pets' % (sid, life))
        # chain
        rel = R.get(s['relic'])
        tab = R.get(key_of(get1(rel, 'bonusTableName', '') or '')) if rel else None
        bon = R.get(key_of(get1(tab, 'randomizerName1', '') or '')) if tab else None
        call = R.get(key_of(get1(bon, 'itemSkillName', '') or '')) if bon else None
        spawn = key_of((getv(call, 'spawnObjects') or [''])[0]) if call else ''
        if not (bon and get1(bon, 'Class') == 'LootRandomizer' and call and get1(call, 'Class') == 'Skill_SpawnPet'
                and spawn == s['pet'] and key_of(call['name']) == s['call']):
            bad.append('soul %s: broken chain relic -> bonus -> summon -> pet' % sid)
        if rel is not None:
            if get1(rel, 'completedRelicLevel') != s['shards'] or s['shards'] < 2:
                bad.append('soul %s: %s shards, want %d (>= 2: the bonus is rolled only by adding a shard)' % (
                    sid, get1(rel, 'completedRelicLevel'), s['shards']))
            for q in B.RELIC_SLOTS:
                t = next((t for vn, t, v in rel['vars'] if vn == q), None)
                if get1(rel, q) != (1 if q in SOUL_FITS[s['kind']] else 0) or t != 3:
                    bad.append('soul %s: fit flag %s=%s type %s (want %s, bool)' % (
                        sid, q, get1(rel, q), t, '/'.join(sorted(SOUL_FITS[s['kind']]))))
                    break
        if call is not None and (getv(call, 'spawnObjectsTimeToLive') or get1(call, 'petLimit') != 1):
            bad.append('soul %s: summon TTL / petLimit' % sid)
        if not s['sources'] and st['souls'] and (s['kind'] == 'boss' or st['soulheroes']) and \
                all(st[k] == v for k, v in DEFAULTS if k.startswith('soul') and 'chance' in k):
            bad.append('soul %s: built but drops nowhere' % sid)
        if dmg.get('factor', 1.0) > 1.0 + 1e-9:
            pr = R.get(s.get('power') or '')
            if pr is None or s['power'] not in own or get1(pr, 'Class') != 'Skill_Passive' or \
                    len(getv(pr, 'offensivePhysicalModifier') or []) != 3 or not (1.0 <= s['damage'] <= dmg['factor']):
                bad.append('soul %s: soul power passive %s missing, not per difficulty or off (x%s of x%g)' % (
                    sid, s.get('power'), s.get('damage'), dmg['factor']))
            elif abs(getv(pr, 'offensivePhysicalModifier')[0] - (s['damage'] - 1.0) * 100.0) > 0.11:
                # level 1 = Normal, where the pet pak adds nothing: exactly (factor - 1) x 100 %
                bad.append('soul %s: soul power x%g, its passive %s' % (sid, s['damage'], getv(pr, 'offensivePhysicalModifier')))
            # 1.8.3: its basic attack (weapon counted) at the hero's pace x its factor within its corridor - the
            # weapon souls ran past it unseen (the Faceless One at half the hero's DPS)
            cap = CORRIDOR[s['kind']][1] * dmg.get('median_soul_dps', 0) * dmg['factor']
            real = s.get('basic', 0) / max(s.get('pace_r', 1.0), 1e-9) * s['damage']
            if s['damage'] > 1.0 + 1e-9 and cap > 0 and real > cap * 1.06:
                bad.append('soul %s: basic attack %.0f per second above its corridor %.0f' % (sid, real, cap))
        left_ai = ai_fixes(R, pet)
        if left_ai:
            bad.append('soul %s: AI slots shaking the air / wired twice: %s' % (sid, left_ai[:2]))
        if (g('deleteBehavior') or '').strip() in DISSOLVE_NONE:
            bad.append('soul %s: deleteBehavior %r - the body would stay lying' % (sid, g('deleteBehavior')))
        pc = ledger.get('pace') or {}
        if pc.get('skill') and s.get('pace') not in own:
            bad.append('soul %s: no soul pace passive (projectile speed)' % sid)
        # 1.7.4: the guard against the hero difficulty, and the boss's own immunity kept
        if gd.get('hero_damage', 1.0) > 1.0 + 1e-9:
            gr = R.get(gd.get('skill') or '')
            if gr is None or s.get('guard') not in own or \
                    [round(x, 1) for x in getv(gr, 'characterLifeModifier') or []] != [0.0, 0.0, gd['life_pct']]:
                bad.append('soul %s: guard %s missing or not life +%g%% on Legendary only' % (sid, s.get('guard'),
                                                                                             gd.get('life_pct')))
        # 1.8.4: only an immunity the game itself gives - four Egyptian side-quest monsters name a bare
        # 'boss_conversionimmunity' (no path, no record), which the game skips
        if rep is not None and any(key_of(v[0]).endswith(BS + 'boss_conversionimmunity.dbr') and key_of(v[0]) in R
                                   for vn, vt_, v in rep['vars'] if vn.startswith('skillName') and v and v[0]) and \
                not any(k.endswith(BS + 'boss_conversionimmunity.dbr') for k in own):
            bad.append('soul %s: the boss\'s own immunity (boss_conversionimmunity) is gone' % sid)
    # kill odds: per Misc slot, every vanilla entry keeps its % and ours are as planned (eidolon shard: 1.5.1 odds)
    eid = key_of(B.NS + 'eidolon_shards.dbr')
    boss_pct = B.drop_chances()[1]
    for k, want in ledger['misc'].items():
        r, r0 = R.get(k), baseR.get(k)
        if r is None or r0 is None:
            bad.append('soul drop record %s missing' % k)
            continue
        new, _ = misc_slots(r)
        old, _ = misc_slots(r0)
        got = {}
        for n in (1, 2, 3):
            for it, q in new[n].items():
                if it in old[n]:
                    if abs(old[n][it] - q) > 0.02:
                        bad.append('%s Misc %d: vanilla %s %.3f%% -> %.3f%%' % (k.split(BS)[-1], n, it[0].split(BS)[-1], old[n][it], q))
                elif it == (eid,):
                    if abs(q - boss_pct) > 0.05:
                        bad.append('%s: eidolon shard %.3f%% per kill, want %g' % (k.split(BS)[-1], q, boss_pct))
                elif len(it) == 1 and it[0] in want:
                    got[it[0]] = got.get(it[0], 0) + q
                else:
                    bad.append('%s Misc %d: unexpected entry %s' % (k.split(BS)[-1], n, it))
            for it in old[n]:
                if it not in new[n]:
                    bad.append('%s Misc %d: vanilla entry %s gone' % (k.split(BS)[-1], n, it[0].split(BS)[-1]))
        for t, p in want.items():
            if abs(got.get(t, 0) - p) > 0.05:
                bad.append('%s: soul %s %.3f%% per kill, want %.3f' % (k.split(BS)[-1], t.split(BS)[-1], got.get(t, 0), p))
    # chests: our copies, the soul with its % per opening, vanilla entries as before
    for ck, c in ledger['chests'].items():
        ch = R.get(ck)
        if ch is None or [key_of(x) for x in getv(ch, 'tables') or []] != c['tables']:
            bad.append('chest %s: tables not our copies' % ck.split(BS)[-1])
            continue
        for t_new, t_old in zip(c['tables'], c['orig']):
            for soul_t, pct in c['souls'].items():
                # 1.8.2: a pool of many souls (the Tartarus arena chests) - any of its souls counts
                pool = (c.get('targets') or {}).get(soul_t)
                targets = frozenset(pool) if pool else frozenset(key_of(x) for x in getv(R[soul_t], 'lootName1') or [])
                e = orb_odds.per_container(R, t_new, targets)
                if abs(e - pct / 100.0) > 5e-3:
                    bad.append('chest %s: soul %.4f per opening, want %.4f' % (ck.split(BS)[-1], e, pct / 100.0))
            # against the table as the build has it (a tweak may have changed it before us: Tartarus' loot)
            oR = R if t_old in R else baseR
            nf, of = orb_odds.fields(R[t_new]), orb_odds.fields(oR[t_old])
            # 1.7.8: six entries a slot, as the engine reads them; a vanilla entry may sit inside our wrapper table
            for n_, j_ in orb_odds.past_slot_max(nf):
                bad.append('chest %s slot %d: entry %d past the six the game reads' % (ck.split(BS)[-1], n_, j_))
            # 1.8.1: what one opening gives of each vanilla entry (items x chance / total x weight share) - the same
            # factor for all of them, and near 1 (the count equations make up for the items the shards take)
            bad += vanilla_kept('chest ' + ck.split(BS)[-1], R, nf, oR, of,
                                (ledger.get('loot_counts') or {}).get(t_new, {}).get('vanilla'))
    # electrum orbs of every difficulty: SoulOrbChance % per orb for a soul of the orb's region
    for reg, o in ledger['orbs'].items():
        targets = frozenset(o['relics'])
        p = orb_odds.odds(R, targets)
        n = 0
        for k in R:
            if 'electrumorbs' in k and k.endswith('_loot.dbr') and ('x4_electrumorb_%s_' % reg) in k.split(BS)[-1]:
                n += 1
                e = orb_odds.per_container(R, k, targets, p)
                if abs(e - o['pct'] / 100.0) > 5e-3:
                    bad.append('orb %s: soul shard %.4f per orb, want %.4f' % (k.split(BS)[-1], e, o['pct'] / 100.0))
                for n_, j_ in orb_odds.past_slot_max(orb_odds.fields(R[k])):
                    bad.append('orb %s slot %d: entry %d past the six the game reads' % (k.split(BS)[-1], n_, j_))
        if not n:
            bad.append('orbs of region %s not found' % reg)
    nb = sum(1 for s in ledger['souls'].values() if s['kind'] == 'boss')
    seen, far = VANILLA_SEEN[:], VANILLA_FAR[:]
    del VANILLA_SEEN[:], VANILLA_FAR[:]
    log('souls: %d bosses (amulet) + %d hero monsters (amulet or ring), %d monster records, %d chests, %d orb regions '
        'checked%s' % (
        nb, len(ledger['souls']) - nb, len(ledger['misc']), len(ledger['chests']), len(ledger['orbs']),
        ', vanilla chest items per opening x%.3f..x%.3f' % (min(seen), max(seen)) if seen else ''))
    if far:
        log('  note: fewer/more vanilla items than in the game (no item count to make up for it, or high chances in '
            'the ini): %s' % ', '.join(sorted(set(re.sub(r'_0\d\.dbr', '', x) for x in far))))
    return bad
