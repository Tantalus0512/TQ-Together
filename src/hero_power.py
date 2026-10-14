# -*- coding: utf-8 -*-
"""1.3.0: a hero's strength for the auto difficulty = the character window's "damage per second", read from the save.
READ-ONLY reproduction of the Titan Quest AE character-sheet "Total Damage" (tab1TotalDamageNumber), "Attack Speed" and
"DPS" (tab1DPSNumber = trunc(Total x AttackSpeed% / 100)) from a save + the database. Spells are not on the sheet and
are not counted. strength(path) -> {'sheet', 'speed', 'dps', ...}; use_db(path) first (the untouched base database).

Mirrors Game.dll 2.10.21415 (modded build) code paths (addresses in D:\\TQMod\\research\\parity2\\damage_notes.md):
  sheet = trunc(A) + trunc(max(0, B - A))      (TQ.exe 0x4d7b75 -> Character::CalculateUIDamageValues 0x100e0e40)
  A = the main weapon's own attributes (store + its relics) processed alone,
  B = the full attack: weapon damage + non-weapon items + set bonuses + game-balance pak + active skills, with ALL modifiers.
Display accumulator: every min..max = midpoint, every chance = x chance/100, global-chance groups count iff chance >= 50.
NOT modelled (see report): exact item stat jitter (seeded per item; nominal = expectation, --band = extremes), toggles are ON unless --no-toggles, temporary buffs,
on-hit/proc buffs, pet bonuses, conditional skill requirements beyond weapon-type flags.
Attack speed (Character::GetAttackSpeed 0x100dc930, CalculateAttackSpeed 0x100e0f50, Player::CapAttackSpeed 0x10207630):
  speed = (body characterAttackSpeed + weapon characterBaseAttackSpeed [dual wield: half the sum]) x (1 + mods/100),
  mods = every characterAttackSpeedModifier / characterTotalSpeedModifier (CharAttributeMod_AttackSpeed 0x100fda80 adds
  to the body AND the weapon slot), held between body x playerAttackSpeedCapMin/Max %;
  shown % = 100 x speed / body x D(unarmed attack anims) / D(attack anims of the hand state) (1.3.3, see anim_ratio).
usage: python hero_power.py <Player.chr> [--no-toggles] [--difficulty N] [--band] [-v]
"""
import sys, os, re, math
sys.path.insert(0, r'D:\TQMod\tools')   # development only; the exe bundles these
from arz_lazy import LazyArz
import chr_reader
import build_companions as bc

DB = None
_A = None


def use_db(path):
    global DB, _A
    if path != DB:
        DB, _A = path, None
        _cache.clear()


def db():
    global _A
    if _A is None:
        if DB is None:
            import paths
            g = paths.find_game()
            b = os.path.join(g, 'Database', 'database.arz')
            use_db(b + paths.BASE_SUFFIX if os.path.isfile(b + paths.BASE_SUFFIX) else b)
        _A = LazyArz.load(DB)
    return _A


_cache = {}


def rec(name):
    """record -> {lowercase field: [values]} or None"""
    if not name:
        return None
    k = name.lower().replace('/', '\\')
    if k in _cache:
        return _cache[k]
    a = db()
    r = None
    if k in a.records:
        r = {}
        for fn, vt, vals in a.records[k]['vars']:
            r[fn.lower()] = vals
    _cache[k] = r
    return r


def arr(r, field, level=1):
    """value at index min(level-1, n-1) (GetValueMin 0x10155300 / GetChance 0x10155bc0)"""
    v = r.get(field.lower()) if r else None
    if not v:
        return 0.0
    i = min(max(level, 1) - 1, len(v) - 1)
    try:
        return float(v[i])
    except (TypeError, ValueError):
        return 0.0


def sval(r, field):
    v = r.get(field.lower()) if r else None
    return v[0] if v else ''


# ---------------------------------------------------------------- attribute catalogue (VERIFIED types, see notes)
T_PHYS, T_PRATIO, T_PIERCE, T_COLD, T_FIRE, T_POISON, T_LIGHT, T_LIFE = 2, 3, 4, 5, 6, 7, 8, 9
T_BLEED, T_LLEECH, T_MLEECH, T_ELEM, T_TOTAL = 0xe, 0x13, 0x14, 0x2f, 0x30
# instant "bonus" damage (all item kinds): stem -> (type, equation)
ABS = {'Fire': (T_FIRE, 'elem'), 'Cold': (T_COLD, 'elem'), 'Lightning': (T_LIGHT, 'elem'), 'Life': (T_LIFE, 'elem'),
       'Poison': (T_POISON, None), 'Pierce': (T_PIERCE, 'pierceNW'), 'LifeLeech': (T_LLEECH, None)}
# weapon "base" damage (weapons only, no jitter)
BASE = {'BaseFire': (T_FIRE, 'elem'), 'BaseCold': (T_COLD, 'elem'), 'BaseLightning': (T_LIGHT, 'elem'),
        'BaseLife': (T_LIFE, 'elem'), 'BasePoison': (T_POISON, 'poison')}
# damage over time: offensiveSlow<stem>
DUR = {'Physical': (T_PHYS, 'physDur'), 'Bleeding': (T_BLEED, 'bleedDur'), 'Fire': (T_FIRE, 'elemDur'),
       'Cold': (T_COLD, 'elemDur'), 'Lightning': (T_LIGHT, 'elemDur'), 'Poison': (T_POISON, 'poisonDur'),
       'Life': (T_LIFE, 'elemDur'), 'LifeLeach': (T_LLEECH, 'leechDur'), 'ManaLeach': (T_MLEECH, 'leechDur')}
ABSMOD = {'Physical': T_PHYS, 'PierceRatio': T_PRATIO, 'Pierce': T_PIERCE, 'Cold': T_COLD, 'Fire': T_FIRE,
          'Poison': T_POISON, 'Lightning': T_LIGHT, 'Life': T_LIFE, 'Bleeding': T_BLEED, 'Elemental': T_ELEM,
          'TotalDamage': T_TOTAL}
DURMOD = {'Physical': T_PHYS, 'Bleeding': T_BLEED, 'Cold': T_COLD, 'Fire': T_FIRE, 'Lightning': T_LIGHT,
          'Poison': T_POISON, 'Life': T_LIFE, 'LifeLeach': T_LLEECH, 'ManaLeach': T_MLEECH}
# expansion of the aggregate modifiers (0x1015fe30 total, 0x1015fbb0 elemental)
ABS_EXPAND = {T_TOTAL: (2, 4, 5, 6, 7, 8, 9, 0x13), T_ELEM: (5, 6, 8)}
DUR_EXPAND = {T_TOTAL: (2, 5, 6, 7, 8, 9, 0xe, 0x13), T_ELEM: (6, 5, 8)}
CHAR_ATTRS = ('characterStrength', 'characterDexterity', 'characterIntelligence', 'characterPhysToElementalRatio')


def chance_mult(c):
    """CombatDisplayAccumulator::GetChanceMultiplier 0x10110a70"""
    return 1.0 if c == 0 or c >= 100 else c / 100.0


def mid(r, stem, level):
    lo = arr(r, stem + 'Min', level)
    hi = arr(r, stem + 'Max', level)
    return (lo + max(lo, hi)) * 0.5


class Store(object):
    """one DamageAttributeStore: attributes of one or several records sharing one global chance"""

    def __init__(self, label):
        self.label = label
        self.entries = []   # (kind, spec, value, chance, group, src)
        self.gchance = 0.0

    jit = 0.0          # jitter % of the record being loaded (set by load); 0 = never jittered
    band = 0.0         # -1 / 0 / +1: evaluate with every jittered value at its low / nominal / high extreme
    rng = None         # random.Random for --mc

    def add(self, kind, spec, value, chance, r, gstem, level, src):
        if value == 0:
            return
        grp = None
        if gstem and arr(r, gstem + 'Global', level):
            grp = 'xor' if arr(r, gstem + 'XOR', level) else 'and'
        j = 0.0 if kind == 'basephys' else self.jit
        if Store.band and j:
            value = value * (1 + Store.band * min(j, 50.0) / 100.0)
        if Store.rng is not None and j:     # Monte-Carlo: Jitter 0x10155420 (integer +-d, d=max(1,int(v*j/100)))
            d = max(1, int(abs(value) * min(j, 50.0) / 100.0))
            nv = value + Store.rng.randint(-d, d)
            if abs(nv) >= 1:
                value = nv
        self.entries.append((kind, spec, value, chance, grp, src))

    def load(self, r, level, role, is_base, src):
        """role: 'weapon' | 'armor' | 'other' (relic, charm, artifact, set, skill, pak) - DamageAttributeStore_*::Load"""
        if not r:
            return
        # Jitter (VERIFIED 0x10159890 / 0x10155420): item base record 20%, affix = its lootRandomizerJitter;
        # relic/charm/artifact/skill stores: not traced -> treated as un-jittered here
        if src.startswith('base:'):
            self.jit = 20.0
        elif src.startswith(('prefix:', 'suffix:')):
            self.jit = arr(r, 'lootRandomizerJitter', 1)
        else:
            self.jit = 0.0
        if role == 'weapon':
            keep, self.jit = self.jit, 0.0     # AbsBase*::AddJitter / BasePhysical::AddJitter are `ret` (no jitter)
            if is_base:   # DamageAttribute_BasePhysical::LoadFromTable 0x10160f00 (base record only)
                self.add('basephys', arr(r, 'offensivePierceRatioMin', level), mid(r, 'offensivePhysical', level),
                         0, r, None, level, src)
            for stem, (t, eq) in BASE.items():
                self.add('abs', (t, eq), mid(r, 'offensive' + stem, level), arr(r, 'offensive' + stem + 'Chance', level),
                         r, 'offensive' + stem, level, src)
            self.jit = keep
            self.add('bonusphys', None, mid(r, 'offensiveBonusPhysical', level),
                     arr(r, 'offensiveBonusPhysicalChance', level), r, 'offensiveBonusPhysical', level, src)
        else:         # armor & everything else: offensivePhysical = DamageAttribute_Physical (kind 2, with chance)
            self.add('phys', arr(r, 'offensivePierceRatio', level), mid(r, 'offensivePhysical', level),
                     arr(r, 'offensivePhysicalChance', level), r, 'offensivePhysical', level, src)
        for stem, (t, eq) in ABS.items():
            self.add('abs', (t, eq), mid(r, 'offensive' + stem, level), arr(r, 'offensive' + stem + 'Chance', level),
                     r, 'offensive' + stem, level, src)
        self.add('elemall', None, mid(r, 'offensiveElemental', level), arr(r, 'offensiveElementalChance', level),
                 r, 'offensiveElemental', level, src)
        for stem, (t, eq) in DUR.items():
            f = 'offensiveSlow' + stem
            self.add('dur', (t, eq), mid(r, f, level), arr(r, f + 'Chance', level), r, f, level, src)
        for stem, t in ABSMOD.items():
            f = 'offensive' + stem + 'Modifier'
            self.add('absmod', t, arr(r, f, level), arr(r, f + 'Chance', level), r, 'offensive' + stem, level, src)
        for stem, t in DURMOD.items():
            f = 'offensiveSlow' + stem + 'Modifier'
            self.add('durmod', t, arr(r, f, level), arr(r, f + 'Chance', level), r, 'offensiveSlow' + stem, level, src)

    def evaluate(self):
        """DamageAttributeStore::AddDamageToAccumulator 0x1015b750 / AddModifierToAccumulator 0x1015b5a0, display RNG"""
        out = []
        for e in self.entries:
            if e[4] is None:
                out.append(e)
        if self.gchance >= 50.0:      # RandFloat(0,100) == 50 in the display accumulator
            out += [e for e in self.entries if e[4] == 'and']
            xor = [e for e in self.entries if e[4] == 'xor']
            if xor:
                tot = sum(e[3] for e in xor)
                cum = 0.0
                for e in xor:
                    cum += e[3]
                    if cum >= tot * 0.5:
                        out.append(e)
                        break
        return out


def set_gchance(store, recs_levels):
    """GetGlobalChance 0x1015a690: suffix>0 ? suffix : prefix>0 ? prefix : base[level]"""
    base, lvl = recs_levels[0]
    g = arr(base, 'offensiveGlobalChance', lvl) if base else 0.0
    for r, l in recs_levels[1:]:
        v = arr(r, 'offensiveGlobalChance', 1) if r else 0.0
        if v > 0:
            g = v
    store.gchance = g


# ---------------------------------------------------------------- equations (records\game\combatequations.dbr)
class Eq(object):
    def __init__(self, st, dx, it, level):
        self.s, self.d, self.i, self.l = st, dx, it, level
        ce = rec(r'records\game\combatequations.dbr')
        self.src = {k: sval(ce, k) for k in ('physicalDamageEquation', 'physicalNonWeaponDamageEquation',
                                               'pierceDamageEquation', 'pierceNonWeaponDamageEquation',
                                               'elementalDamageEquation', 'elementalDurationDamageEquation',
                                               'physicalDurationDamageEquation', 'poisonDamageEquation',
                                               'poisonDurationDamageEquation', 'bleedingDurationDamageEquation',
                                               'lifeLeachDurationDamageEquation', 'manaLeachDurationDamageEquation')}

    def run(self, name, **dv):
        """evaluate the designer equation text exactly as stored ('^' = power)"""
        env = {'strengthDV': self.s, 'dexterityDV': self.d, 'intelligenceDV': self.i, 'characterLevelDV': self.l}
        env.update(dv)
        return float(eval(self.src[name].replace('^', '**'), {'__builtins__': {}}, env))

    def apply(self, eq, v):
        if v <= 0 or eq is None:
            return v
        m = {'elem': ('elementalDamageEquation', 'elementalDamageDV'),
             'pierceNW': ('pierceNonWeaponDamageEquation', 'pierceDamageDV'),
             'poison': ('poisonDamageEquation', 'poisonDamageDV'),
             'elemDur': ('elementalDurationDamageEquation', 'elementalDamageDV'),
             'physDur': ('physicalDurationDamageEquation', 'physicalDamageDV'),
             'poisonDur': ('poisonDurationDamageEquation', 'poisonDamageDV'),
             'bleedDur': ('bleedingDurationDamageEquation', 'bleedingDamageDV'),
             'leechDur': ('lifeLeachDurationDamageEquation', 'lifeLeachDamageDV')}[eq]
        if eq == 'leechDur':
            return self.run('lifeLeachDurationDamageEquation', lifeLeachDamageDV=v)
        return self.run(m[0], **{m[1]: v})


def process(entries, eq, ptoe=0.0, detail=None):
    """ProcessDamage 0x1010ef50: sum modifiers per type, then CombatAttribute*::Process, then GetTotalDamage"""
    amod, dmod = {}, {}
    for kind, spec, value, chance, grp, src in entries:
        v = value * chance_mult(chance)
        if kind == 'absmod':
            for t in ABS_EXPAND.get(spec, (spec,)):
                amod[t] = amod.get(t, 0.0) + v
            if spec in DUR_EXPAND:
                for t in DUR_EXPAND[spec]:
                    dmod[t] = dmod.get(t, 0.0) + v
        elif kind == 'durmod':
            dmod[spec] = dmod.get(spec, 0.0) + v
    total = 0.0
    parts = {}

    def put(key, v, src):
        parts.setdefault(key, 0.0)
        parts[key] += v
        if detail is not None:
            detail.append((key, round(v, 2), src))

    for kind, spec, value, chance, grp, src in entries:
        if kind in ('basephys', 'phys'):
            v = value * (1.0 if kind == 'basephys' else chance_mult(chance))
            ratio = spec
            if kind == 'basephys' and ptoe > 0:      # DamageAttribute_BasePhysical::AddDamageToAccumulator 0x101611c0
                f = min(ptoe / 100.0, 1.0)
                conv = v * f
                v -= conv
                for t in (T_FIRE, T_COLD, T_LIGHT):
                    e = conv / 3.0 * (1 + amod.get(t, 0.0) / 100.0)
                    e = eq.apply('elem', max(e, 0.0))
                    put('elemental(PtoE)', e, src)
            phys = max(v + abs(v) * amod.get(T_PHYS, 0.0) / 100.0, 0.0)
            if phys > 0:
                if kind == 'basephys':
                    phys = eq.run('physicalDamageEquation', physicalDamageDV=phys)
                else:
                    phys = eq.run('physicalNonWeaponDamageEquation', physicalDamageDV=phys)
            r = min(max(ratio + abs(ratio) * amod.get(T_PRATIO, 0.0) / 100.0, 0.0), 100.0)
            pierce = phys * r / 100.0
            phys = max(phys - pierce, 0.0)
            pierce = max(pierce + abs(pierce) * amod.get(T_PIERCE, 0.0) / 100.0, 0.0)
            if kind == 'basephys' and pierce > 0:
                pierce = eq.run('pierceDamageEquation', pierceDamageDV=pierce)
            put('physical', phys, src)
            put('pierce(ratio)', pierce, src)
        elif kind == 'bonusphys':
            put('bonusPhysical', value * chance_mult(chance), src)
        elif kind in ('abs', 'elemall'):
            base = value * chance_mult(chance)
            items = [(t, 'elem', base / 3.0) for t in (T_COLD, T_FIRE, T_LIGHT)] if kind == 'elemall' else \
                [(spec[0], spec[1], base)]
            for t, e, v in items:
                v = max(v + abs(v) * amod.get(t, 0.0) / 100.0, 0.0)
                v = eq.apply(e, v)
                put({2: 'physical', 4: 'pierce', 5: 'cold', 6: 'fire', 7: 'poison', 8: 'lightning', 9: 'vitality',
                     0x13: 'lifeLeech'}.get(t, str(t)), v, src)
        elif kind == 'dur':
            t, e = spec
            v = value * chance_mult(chance)
            v = max(v + abs(v) * dmod.get(t, 0.0) / 100.0, 0.0)
            v = eq.apply(e, v)
            put({2: 'DoT physical', 0xe: 'DoT bleeding', 5: 'DoT cold', 6: 'DoT fire', 8: 'DoT lightning',
                 7: 'DoT poison', 9: 'DoT vitality', 0x13: 'DoT lifeLeech', 0x14: 'DoT manaLeech'}[t], v, src)
    total = sum(parts.values())
    return total, parts, amod, dmod


# ---------------------------------------------------------------- the hero
PLAYER_BODY = 'records\\xpack\\creatures\\pc\\malepc01.dbr'   # every hero body: characterAttackSpeed 0.74
PLAYER_CAPS = bc.GAP_SRC                                        # xpack gameengine: playerAttackSpeedCapMin/Max
WEAPON_TYPE = {'weaponmelee_axe': 2, 'weaponmelee_sword': 3, 'weaponmelee_mace': 4, 'weaponhunting_spear': 5,
               'weaponhunting_bow': 6, 'weaponmagical_staff': 7, 'weaponarmor_shield': 9,
               'weaponhunting_rangedonehand': 10}
WEAPON_FLAG = {'axe': 2, 'sword': 3, 'mace': 4, 'spear': 5, 'bow': 6, 'staff': 7, 'magical': 8, 'shield': 9,
               'rangedonehand': 10}
TOGGLE_CLASSES = ('skill_buffradiustoggled', 'skill_buffselftoggled')


def item_stores(it):
    """-> (kind, class, [Store...]) for one worn item"""
    base = rec(it['base'])
    cls = sval(base, 'Class').lower()
    role = 'weapon' if cls.startswith('weapon') else ('armor' if cls.startswith('armor') else 'other')
    stores = []
    s = Store('item ' + os.path.basename(it['base']))
    pre, suf = rec(it['prefix']), rec(it['suffix'])
    s.load(base, 1, role, True, 'base:' + os.path.basename(it['base']))
    s.load(pre, 1, role, False, 'prefix:' + os.path.basename(it['prefix']))
    s.load(suf, 1, role, False, 'suffix:' + os.path.basename(it['suffix']))
    set_gchance(s, [(base, 1), (pre, 1), (suf, 1)])
    stores.append(s)
    for rk, bk, sk in (('relic', 'relic_bonus', 'shards'), ('relic2', 'relic_bonus2', 'shards2')):
        if it.get(rk):
            rr = rec(it[rk])
            lvl = it.get(sk) or 1
            if rr and not (1 <= lvl <= 10):
                lvl = int(arr(rr, 'completedRelicLevel', 1)) or 1
            s2 = Store('relic ' + os.path.basename(it[rk]))
            s2.load(rr, lvl, 'other', False, 'relic:%s@%d' % (os.path.basename(it[rk]), lvl))
            set_gchance(s2, [(rr, lvl)])
            stores.append(s2)
        if it.get(bk):
            rb = rec(it[bk])
            s3 = Store('bonus ' + os.path.basename(it[bk]))
            s3.load(rb, 1, 'other', False, 'relicBonus:' + os.path.basename(it[bk]))
            set_gchance(s3, [(rb, 1)])
            stores.append(s3)
    return role, cls, stores


def item_char_records(it):
    """(record, level) pairs that contribute character attributes / skill augments"""
    out = [(rec(it['base']), 1), (rec(it['prefix']), 1), (rec(it['suffix']), 1)]
    for rk, bk, sk in (('relic', 'relic_bonus', 'shards'), ('relic2', 'relic_bonus2', 'shards2')):
        if it.get(rk):
            rr = rec(it[rk])
            lvl = it.get(sk) or 1
            if rr and not (1 <= lvl <= 10):
                lvl = int(arr(rr, 'completedRelicLevel', 1)) or 1
            out.append((rr, lvl))
        if it.get(bk):
            out.append((rec(it[bk]), 1))
    return [(r, l) for r, l in out if r]


def save_skills(path):
    """skill tree from the save IN FILE ORDER (the game attaches every Skill_Modifier to the last loaded non-modifier
    skill: SkillManager::CreateAndLoadSkill 0x10251fa0); max level per record (hot-bar duplicates come with level 1)"""
    info = chr_reader.read_char(path)
    sk = {}
    order = []
    for name, lvl in info['skills']:
        k = name.lower()
        if k not in sk:
            order.append(k)
            sk[k] = (name, lvl)
        elif lvl > sk[k][1]:
            sk[k] = (name, lvl)
    return info, [sk[k] for k in order]


# ---- sheet attack speed: hand state + attack-animation ratio (research\parity3\speed_notes.md)
# EquipManager::GetHandState 0x101792a0 (after ForceRightHandAsNeeded 0x10178120), Weapon_Type = vt+0x1dc:
# 2 axe, 3 sword, 4 mace, 5 spear, 6 bow, 7 staff, 9 shield, 10 thrown (WeaponHunting_RangedOneHand)
HAND_PREFIX = ('unarmed', 'sHanded', 'dHanded', 'bow', 'spear', 'staff', 'rangedOneHand', 'dualRanged')
# frames/fps of the player attack .anm files (Resources\Creatures.arc, header ANM 2: bones, frames, fps);
# GraphicsAnim::GetAnimSpeed (Engine 0x10159100) = frames / fps. Anything not listed: 25 frames @ 30 fps.
ANM_SECONDS = {'malepc_unarmed_attalpha.anm': 21 / 30.0, 'malepc_unarmed_attbeta.anm': 17 / 30.0,
               'malepc_unarmed_attgamma.anm': 21 / 30.0, 'femalepc_unarmed_attalpha.anm': 21 / 30.0,
               'femalepc_unarmed_attbeta.anm': 17 / 30.0, 'malepc_roh_attbeta.anm': 46 / 30.0}
PLAYER_BODY_FEMALE = 'records\\xpack\\creatures\\pc\\femalepc01.dbr'


def hand_state(weapons):
    """weapons = the attached Weapon items (shields included) in slot order: right hand first, then left.
    Bow/staff/shield only fit the left hand, a spear only the right (Get{Right,Left}HandType 0x102d6370..),
    a lone one-hander/thrown is moved to the right hand (ForceRightHandAsNeeded)."""
    types = [w['wtype'] for w in weapons]
    right = left = None
    if len(types) >= 2:
        right, left = types[0], types[1]
    elif types:
        if types[0] in (6, 7, 9):
            left = types[0]
        else:
            right = types[0]
    if left in (2, 3, 4):
        return 2            # dual wield (melee in the left hand)
    if left == 6:
        return 3            # bow
    if left == 7:
        return 5            # staff
    if left == 10:
        return 7            # thrown weapon in the left hand = dual thrown
    return {2: 1, 3: 1, 4: 1, 8: 1, 5: 4, 7: 5, 10: 6}.get(right, 0)   # 1 one-hand, 4 spear, 6 thrown, 0 bare


def attack_anim_seconds(table, prefix):
    """AnimationPool::GetAnimSpeed 0x100cd380 for the 'Attack' pool (AnimationSet slot 16, +0x4c): plain mean over
    <prefix>AttackAnim1..3 with a non-empty name of seconds / <prefix>AttackAnimSpeedN (default 1.0); weights unused."""
    vals = []
    for n in (1, 2, 3):
        nm = sval(table, '%sAttackAnim%d' % (prefix, n))
        if not nm:
            continue
        sp = arr(table, '%sAttackAnimSpeed%d' % (prefix, n), 1) or 1.0
        vals.append(ANM_SECONDS.get(nm.replace('/', '\\').split('\\')[-1].lower(), 25 / 30.0) / sp)
    return sum(vals) / len(vals) if vals else 0.0


def anim_ratio(pc, hand):
    """Character::CalculateAttackSpeed 0x100e0f50: x AnimSpeed(unarmed set +0x1160) / AnimSpeed(current set +0x1180)
    when GetHandState() != 0; the sets come from the body's charAnimationTableName (Character::LoadAnimations 0x100e19a0)."""
    if hand == 0:
        return 1.0
    table = rec(sval(pc, 'charAnimationTableName')) or pc
    cur = attack_anim_seconds(table, HAND_PREFIX[hand])
    return attack_anim_seconds(table, 'unarmed') / cur if cur > 0 else 1.0


# Which vtable collectors a class uses (Game.dll vtable slots +0x12c char / +0x134 damage / +0x138 modifier):
#   Skill_Passive::Collect* 0x10281ae0/0x10281bd0/0x10281c30 - needs Skill+0xa0 (SetAvailability) and base level > 0
PASSIVE_FAMILY = {'skill_passive', 'skill_mastery', 'skill_passiveshield', 'skill_passiveontargethit',
                  'skill_passiveontargetkilled', 'skill_passiveontargetkilleddrop', 'skill_passiveonitemusedbuffself',
                  'skill_passivedualwieldweapon', 'skill_draupner'}
#   Skill_BuffSelfToggled::Collect* 0x10276c60/0x10276d50/0x10276db0 - needs +0xa8 (toggled on), no weapon check
SELF_TOGGLES = {'skill_buffselftoggled'}
#   Skill_BuffRadius(Toggled): own record gives nothing (base Skill no-op); the buffSkillName record is the toggle's
#   profile (Skill_BuffRadius::Load 0x10273ef0) and reaches the sheet as a SkillBuff in SkillManager+0x60
#   (SkillBuff::Collect* 0x1024e6e0/0x1024e790/0x1024e7e0) at the toggle's level, carrying the toggle's first two
#   modifiers (SkillActivated::ApplyBuffOnTarget 0x102481e0 -> Skill::GetModifierInfo 0x1023ed20 for index 0 and 1).
#   The toggle switches itself off when the profile's weapon flags do not match (UpdateSkillController 0x10274f10).
RADIUS_TOGGLES = {'skill_buffradiustoggled'}
RADIUS_LOAD = {'skill_buffradius', 'skill_buffradiustoggled'}      # classes whose profile = buffSkillName record


def is_debuff(r):
    """a buff that the game puts on ENEMIES (debufSkill flag, SkillBuff_Debuf* / SkillBuff_Contageous classes)"""
    cls = sval(r, 'Class').lower()
    return bool(arr(r, 'debufSkill', 1)) or cls.startswith('skillbuff_debuf') or cls == 'skillbuff_contageous'


def analyse(path, toggles=True, difficulty=2, verbose=False):
    info, skills = save_skills(path)
    attrs, _tex = bc.save_extra(path)
    items = bc.parse_equipment(path)
    level = info['level']
    # ---- items
    worn = []
    for it in items:
        role, cls, stores = item_stores(it)
        worn.append({'it': it, 'role': role, 'cls': cls, 'stores': stores,
                     'is_weapon': role == 'weapon', 'wtype': WEAPON_TYPE.get(cls)})
    weapons = [w for w in worn if w['is_weapon']]
    # right hand = first weapon listed (slot order in parse_equipment: weapon set R then L)
    right = weapons[0] if weapons else None
    left = weapons[1] if len(weapons) > 1 else None
    hand_types = {w['wtype'] for w in weapons}
    dual = len([w for w in weapons if w['wtype'] != 9]) == 2
    ranged = bool(hand_types & {6, 10})
    # ---- skill level bonuses (augmentAllLevel / augmentMasteryLevelN / augmentSkillLevelN)
    # SetMasteryAugment 0x102571d0 matches Skill+0xc8 (owning mastery id, set at load) -> key by mastery RECORD
    all_bonus, mast_bonus, skill_bonus = 0, {}, {}
    item_skill_grants = []
    for w in worn:
        for r, l in item_char_records(w['it']):
            all_bonus += int(arr(r, 'augmentAllLevel', l))
            for n in (1, 2):
                mn = sval(r, 'augmentMasteryName%d' % n)
                if mn:
                    d = mn.lower()
                    mast_bonus[d] = mast_bonus.get(d, 0) + int(arr(r, 'augmentMasteryLevel%d' % n, l))
            for n in (1, 2, 3, 4):
                sn = sval(r, 'augmentSkillName%d' % n)
                if sn:
                    skill_bonus[sn.lower()] = skill_bonus.get(sn.lower(), 0) + int(arr(r, 'augmentSkillLevel%d' % n, l))
            isn = sval(r, 'itemSkillName')
            if isn:
                item_skill_grants.append((isn, int(arr(r, 'itemSkillLevel', l)) or 1))

    def profile(r, cls):
        if cls in RADIUS_LOAD and sval(r, 'buffSkillName'):
            return rec(sval(r, 'buffSkillName'))
        return r

    def available(prof):
        """Skill::SetAvailability 0x10245bc0: QualifyingWeapon (IsQualifyingWeapons 0x1023f510: no flags, or a flag
        matching the right/left item type) and QualifyingHandState 0x1023f410 (dualWieldOnly / meleeOnly)"""
        req = {v for f, v in WEAPON_FLAG.items() if arr(prof, f, 1)}
        if req and not (req & hand_types):
            return False, 'weapon %s' % sorted(req)
        if arr(prof, 'dualWieldOnly', 1) and not dual:
            return False, 'dualWieldOnly'
        if arr(prof, 'meleeOnly', 1) and ranged:
            return False, 'meleeOnly'
        return True, ''

    # ---- load the tree like the game: mastery owner + modifier parent by save order
    nodes = []
    cur_mastery = None
    parent = None
    for name, base in skills:
        r = rec(name)
        k = name.lower()
        cls = sval(r, 'Class').lower() if r else ''
        n = {'name': name, 'k': k, 'r': r, 'cls': cls, 'base': base, 'mastery': cur_mastery, 'mods': [], 'item': False}
        if cls == 'skill_mastery':
            cur_mastery = k
            n['mastery'] = None
            parent = None
        elif cls == 'skill_modifier':
            if parent is not None:
                parent['mods'].append(n)
        elif cls.startswith('skillsecondary'):
            pass        # AddSecondarySkill; may become the parent when its +0x1f1 == 0 (UNVERIFIED) - no sheet effect here
        else:
            parent = n
        nodes.append(n)
    for isn, il in item_skill_grants:            # SkillManager::AddItemSkill 0x10257610: +0x128 list, no augments
        r = rec(isn)
        nodes.append({'name': isn, 'k': isn.lower(), 'r': r, 'cls': sval(r, 'Class').lower() if r else '',
                      'base': il, 'mastery': None, 'mods': [], 'item': True})

    def cur_level(n):
        """Skill::GetCurrentLevel 0x10240de0: 0 if base == 0, else min(base + augment, max(skillMaxLevel, Ultimate))"""
        if not n['r'] or n['base'] <= 0:
            return 0
        aug = 0
        if not n['item'] and n['cls'] != 'skill_mastery':   # Skill_Mastery::IncrementAugmentedSkillLevel = ret
            aug = all_bonus + mast_bonus.get(n['mastery'], 0) + skill_bonus.get(n['k'], 0)
        prof = profile(n['r'], n['cls']) or n['r']
        cap = max(int(arr(prof, 'skillUltimateLevel', 1)), int(arr(prof, 'skillMaxLevel', 1)))
        return min(n['base'] + aug, cap)

    active = []      # (record, level, what)      -> offensive damage / modifier stores
    char_src = []    # (record, level, label)     -> character attribute store (+0x100)
    notes = []

    def add(r, lvl, lab, off=True, ch=True):
        if off:
            active.append((r, lvl, lab))
        if ch:
            char_src.append((r, lvl, lab))

    def add_mods(n, lab, limit=None, ch=True):
        """Skill::AddModifier*Attributes 0x1023ef50/0x1023ef00/0x1023f000 -> Skill_Modifier::CollectModifier* 0x1027e2d0..:
        each child needs its own availability (+0xa0) and base level > 0; stores read at the CHILD's level"""
        for m in n['mods'][:limit]:
            ml = cur_level(m)
            if ml <= 0:
                continue
            ok, why = available(profile(m['r'], m['cls']))
            if not ok:
                notes.append('modifier %s skipped (%s)' % (os.path.basename(m['name']), why))
                continue
            add(m['r'], ml, '%s > modifier %s L%d' % (lab, os.path.basename(m['name']), ml), True, ch)

    for n in nodes:
        lvl = cur_level(n)
        if lvl <= 0:
            continue
        r, cls, bn = n['r'], n['cls'], os.path.basename(n['name'])
        if cls in PASSIVE_FAMILY:
            ok, why = available(r)
            if not ok:
                notes.append('%s %s skipped (%s)' % (cls, bn, why))
                continue
            lab = '%s %s L%d' % ('mastery' if cls == 'skill_mastery' else 'passive', bn, lvl)
            add(r, lvl, lab)
            add_mods(n, lab)
        elif cls in SELF_TOGGLES:
            if not toggles:
                notes.append('toggle %s excluded (--no-toggles)' % bn)
                continue
            lab = 'toggle %s L%d (assumed ON)' % (bn, lvl)
            add(r, lvl, lab)
            add_mods(n, lab)
        elif cls in RADIUS_TOGGLES:
            br = profile(r, cls)
            if br is None or br is r:
                continue
            if not toggles:
                notes.append('toggle %s excluded (--no-toggles)' % bn)
                continue
            if is_debuff(br):                # Deathchill, Blood Pact, Gates of Hell: the aura works on ENEMIES
                notes.append('aura %s skipped (enemy debuff)' % bn)
                continue
            ok, why = available(br)
            if not ok:
                notes.append('toggle %s off (%s)' % (bn, why))
                continue
            lab = 'aura %s -> %s L%d (assumed ON)' % (bn, os.path.basename(sval(r, 'buffSkillName')), lvl)
            add(br, lvl, lab)
            add_mods(n, lab, limit=2)        # buff-carried modifiers: SkillBuff char collector passes (1, 0) = +0x100
        elif cls == 'skill_buffattackradiustoggled' and toggles:
            # item aura Ares' Retreat (u_l_aresweakness): its own speed/attributes reach the hero, no damage (skill_sweep.md)
            add(r, lvl, 'attack aura %s L%d (assumed ON)' % (bn, lvl), off=False)
    # ---- character attributes
    flat = {a: 0.0 for a in CHAR_ATTRS}
    mod = {a: 0.0 for a in CHAR_ATTRS}
    flat['characterStrength'] += attrs.get('str', 0)
    flat['characterDexterity'] += attrs.get('dex', 0)
    flat['characterIntelligence'] += attrs.get('int', 0)
    set_count = {}
    for w in worn:
        for r, l in item_char_records(w['it']):
            for a_ in CHAR_ATTRS:
                flat[a_] += arr(r, a_, l)
                mod[a_] += arr(r, a_ + 'Modifier', l)
        sn = sval(rec(w['it']['base']), 'itemSetName')
        if sn:
            set_count[sn.lower()] = set_count.get(sn.lower(), 0) + 1
    set_recs = [(rec(sn), n) for sn, n in set_count.items() if rec(sn)]
    for r, n in set_recs:
        for a_ in CHAR_ATTRS:
            flat[a_] += arr(r, a_, n)
            mod[a_] += arr(r, a_ + 'Modifier', n)
    for r, l, lab in char_src:
        for a_ in CHAR_ATTRS:
            flat[a_] += arr(r, a_, l)
            mod[a_] += arr(r, a_ + 'Modifier', l)
    pak = rec(r'records\game\playergamebalanceattributes.dbr')
    pak_idx = 1 + 6 * difficulty
    for a_ in CHAR_ATTRS:
        flat[a_] += arr(pak, a_, pak_idx)
        mod[a_] += arr(pak, a_ + 'Modifier', pak_idx)
    # ---- attack speed (Character::GetAttackSpeed 0x100dc930, CalculateAttackSpeed 0x100e0f50, see the notes)
    # every contributor feeds the same accumulator: characterAttackSpeed -> slot 0xd, characterBaseAttackSpeed -> 0xf
    srcs = [(r, l) for w in worn for r, l in item_char_records(w['it'])] + list(set_recs) + \
        [(r, l) for r, l, lab in char_src] + [(pak, pak_idx)]
    spd = lambda r, l: arr(r, 'characterAttackSpeedModifier', l) + arr(r, 'characterTotalSpeedModifier', l)
    spd_mod = sum(spd(r, l) for r, l in srcs)
    pc = rec(PLAYER_BODY_FEMALE if 'female' in (_tex or '').lower() else PLAYER_BODY)
    body = arr(pc, 'characterAttackSpeed', 1) or 0.74          # record value = CalculateAttackSpeed's denominator
    body_a = body + sum(arr(r, 'characterAttackSpeed', l) for r, l in srcs)
    hand = hand_state(weapons)
    wsum = sum(arr(r, 'characterBaseAttackSpeed', l) for r, l in srcs)   # all weapons summed; shields carry none
    if hand == 2:
        wsum *= 0.5                                             # halved for dual MELEE only (not dual thrown)
    ge = rec(PLAYER_CAPS)
    cap_lo, cap_hi = (arr(ge, 'playerAttackSpeedCap' + x, difficulty + 1) for x in ('Min', 'Max'))
    speed = max(0.0, body_a * (1 + spd_mod / 100.0)) + max(0.0, wsum * (1 + spd_mod / 100.0))
    # (x (1 - active offensiveSlowAttackSpeed debuff %/100) in game: DurationDamageManager::GetFixedDamage(0x10) = 0 here)
    if cap_lo > 0 and cap_hi > 0:
        speed = min(max(speed, body * cap_lo / 100.0), body * cap_hi / 100.0)
    # 1.3.3: the sheet scales by attack-animation length (unarmed / this hand setup); owner's Nikton 222 % = 350 x 0.633
    speed_pct = 100.0 * speed / body * anim_ratio(pc, hand)

    def total_attr(a_):          # CombatManager::GetDesignerVariable 0x10111090
        f = flat[a_]
        v = f + abs(f) * mod[a_] / 100.0
        return max(v, 0.0)
    STR, DEX, INT = total_attr('characterStrength'), total_attr('characterDexterity'), total_attr('characterIntelligence')
    PTOE = total_attr('characterPhysToElementalRatio')
    eq = Eq(STR, DEX, INT, level)
    # ---- non-weapon damage/modifier sources
    pak_store = Store('game balance pak')
    pak_store.load(pak, pak_idx, 'other', False, 'playerAttributePak[%d]' % pak_idx)
    set_stores = []
    for r, n in set_recs:
        s = Store('set')
        s.load(r, n, 'other', False, 'set:%s@%d' % (sval(r, 'FileDescription'), n))
        set_stores.append(s)
    skill_stores = []
    for r, l, lab in active:
        s = Store(lab)
        s.load(r, l, 'other', False, lab)
        set_gchance(s, [(r, l)])
        skill_stores.append(s)

    def weapon_parts(w):
        dmg, mods = [], []
        for s in w['stores']:
            for e in s.evaluate():
                (mods if e[0] in ('absmod', 'durmod') else dmg).append(e)
        return dmg, mods

    def attack(w):
        """A and B for one hand (CalculateDamageValues 0x100e0990)"""
        wd, wm = weapon_parts(w) if w else ([], [])
        detA = []
        A, partsA, _, _ = process(wd + wm, eq, PTOE, detA)
        dmgB, modB = list(wd), []
        for x in worn:                                           # GetEquipOffensiveModifierAttributes: ALL attached
            for s in x['stores']:
                for e in s.evaluate():
                    if e[0] in ('absmod', 'durmod'):
                        modB.append(e)
                    elif not x['is_weapon']:                     # GetEquipArmorDamageAttributes: non-weapons only
                        dmgB.append(e)
        for s in set_stores + [pak_store] + skill_stores:        # misc (sets), game balance, SkillManager
            for e in s.evaluate():
                (modB if e[0] in ('absmod', 'durmod') else dmgB).append(e)
        detB = []
        B, partsB, amod, dmod = process(dmgB + modB, eq, PTOE, detB)
        return A, B, partsA, partsB, amod, dmod, detB

    hands = []
    if right is not None:
        hands.append(right)
    if left is not None and left['wtype'] != 9:
        hands.append(left)
    if not hands:
        hands = [None]   # bare hand: CombatManager::GetHandHitDamage (not modelled -> 0 weapon part)
    res = [attack(h) for h in hands]
    if len(res) == 2:
        a = int((res[0][0] + res[1][0]) * 0.5)
        b = int((max(0.0, res[0][1] - res[0][0]) + max(0.0, res[1][1] - res[1][0])) * 0.5)
    else:
        a = int(res[0][0])
        b = int(max(0.0, res[0][1] - res[0][0]))
    out = {'name': info['name'], 'level': level, 'str': STR, 'dex': DEX, 'int': INT, 'ptoe': PTOE,
           'flat': flat, 'mod': mod, 'A': [r[0] for r in res], 'B': [r[1] for r in res], 'sheet': a + b,
           'speed': speed_pct, 'speed_mod': spd_mod, 'dps': max(0, int((a + b) * speed_pct / 100.0)),
           'parts': res[0][3], 'amod': res[0][4], 'dmod': res[0][5], 'detail': res[0][6], 'notes': notes,
           'hands': [os.path.basename(h['it']['base']) if h else 'bare hand' for h in hands],
           'skills_active': [lab for r, l, lab in active],
           'sets': [(sval(r, 'FileDescription'), n) for r, n in set_recs],
           'skill_bonus': (all_bonus, mast_bonus, skill_bonus)}
    return out


def strength(path):
    """the auto-difficulty measure of one hero: the sheet's DPS on Legendary, toggles on (the save does not say which
    toggles are running; a toggled hero plays with them on)"""
    return analyse(path, True, 2)['dps']


def report(o, verbose=False):
    print('=' * 70)
    print('%s  level %d   hands: %s' % (o['name'], o['level'], ', '.join(o['hands'])))
    print('Str %.1f  Dex %.1f  Int %.1f  PtoE %.1f' % (o['str'], o['dex'], o['int'], o['ptoe']))
    print('  flat: ' + ', '.join('%s %.1f' % (k[9:], v) for k, v in o['flat'].items()))
    print('  mod%%: ' + ', '.join('%s %.1f' % (k[9:], v) for k, v in o['mod'].items()))
    print('skill bonus: all +%d, mastery %s, skills %s' % o['skill_bonus'])
    print('active skills counted: ' + '; '.join(o['skills_active']))
    for n in o['notes']:
        print('  note: ' + n)
    print('sets: %s' % o['sets'])
    print('modifiers (instant) %%: ' + ', '.join('%s=%.1f' % (k, v) for k, v in sorted(o['amod'].items())))
    print('modifiers (DoT)     %%: ' + ', '.join('%s=%.1f' % (k, v) for k, v in sorted(o['dmod'].items())))
    print('B by damage kind:')
    for k, v in sorted(o['parts'].items(), key=lambda x: -x[1]):
        print('    %-18s %10.1f' % (k, v))
    print('A (weapon alone) = %s   B (full) = %s' % (['%.1f' % x for x in o['A']], ['%.1f' % x for x in o['B']]))
    print('>>> SHEET TOTAL DAMAGE (predicted, nominal DB values) = %d' % o['sheet'])
    print('>>> ATTACK SPEED %d %% (mods %+.0f %%)   DPS %d' % (int(o['speed'] + 0.5), o['speed_mod'], o['dps']))
    if verbose:
        for k, v, s in o['detail']:
            print('      %-18s %9.2f  %s' % (k, v, s))


if __name__ == '__main__':
    args = sys.argv[1:]
    verbose = '-v' in args
    toggles = '--no-toggles' not in args
    diff = 2
    if '--difficulty' in args:
        diff = int(args[args.index('--difficulty') + 1])
    paths = [a for a in args if a.lower().endswith('.chr')]
    for p in paths:
        report(analyse(p, toggles, diff, verbose), verbose)
        if '--band' in args:
            for b in (-1, 1):
                Store.band = b
                o = analyse(p, toggles, diff)
                print('    jitter band %+d (all item-store damage/modifier values at their %s extreme): sheet %d'
                      % (b, 'low' if b < 0 else 'high', o['sheet']))
            Store.band = 0
        if '--mc' in args:
            import random
            n = int(args[args.index('--mc') + 1])
            Store.rng = random.Random(12345)
            vals = sorted(analyse(p, toggles, diff)['sheet'] for _ in range(n))
            Store.rng = None
            print('    Monte-Carlo jitter (%d rolls): 5%%=%d  median=%d  95%%=%d  min=%d max=%d'
                  % (n, vals[int(n * .05)], vals[n // 2], vals[int(n * .95) - 1], vals[0], vals[-1]))
