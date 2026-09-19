# -*- coding: utf-8 -*-
"""Companions: your OTHER saved characters as permanent summoned allies (TQ AE), 18.09.2026.

  py -3 build_companions.py            build from the CURRENT saves -> build\\database.arz
  py -3 build_companions.py --install  build + install (game must be closed)
  start_tq.bat                         rebuild from fresh saves, install, launch the game

What it does: every saved character (level >= 20, a mastery chosen) becomes a companion that another character
can summon - with its level, attributes, skills (AI-wired by skill class) and worn gear, rebuilt from the save
on every launch, so levelling that character levels the companion too.
  - the companion is a Class Pet record (pet panel: health/mana, stance, dismiss) on the player's body
  - "Eidolon: <name>": a 2-shard relic that fits rings only (two rings = at most two companions); completing it
    rolls the completion bonus (an affix) that grants "Summon Companion: <name>" - like vanilla relic bonuses
    that grant Wraith Lord etc. Drops only from LEGENDARY electrum orbs (ORB_CHANCE per orb), vanilla odds kept
  - deleted characters leave inert "faded" records (registry.json) so items holding their relic stay valid
Checks: verify_companions.py (run by --install; ALL CHECKS PASSED or nothing is installed).
"""
import os, sys, re, struct, glob, hashlib, collections, json

sys.path.insert(0, r'D:\TQMod\tools')
from tqlib import DB, get1, getv, setv, delv, key_of, BS, write_text_file, load_game_text
from arz_lazy import LazyArz
import paths
from chr_reader import read_char

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(paths.data_dir(), 'build') if paths.frozen() else os.path.join(HERE, 'build')
NS = ('records' + BS + 'tqmod' + BS + 'companions' + BS).lower()
SAVES = paths.saves_dir()
MIN_LEVEL = 20
UNIQUE_AFFIX_TEST = set()   # 18.09 experiment: this companion's Epic/Legendary items go through exact-affix tables
DIRECT_GEAR = set()   # companions whose slots ALL point straight at the item record (no affixes); Epic/Legendary always do
MAX_SKILLS = 33   # Game.dll loads skillName1..33 (audit 18.09); vanilla creatures use <= 17, so 18+ carry only passives
PET_SRC = 'records\\xpack2\\skills\\item skills\\pet\\doppelgangerpet.dbr'
SUMMON_SRC = 'records\\xpack2\\skills\\item skills\\summon_doppel.dbr'
RING_SRC = 'records\\item\\equipmentring\\c01_ring01.dbr'
DYN_SRC = 'records\\item\\loottables\\finger\\commondynamic\\finger_l01.dbr'
PC = {'male': 'records\\xpack\\creatures\\pc\\malepc01.dbr', 'female': 'records\\xpack\\creatures\\pc\\femalepc01.dbr'}
SLOT_BY_CLASS = [   # item Class -> monster loot slot(s)
    (r'^ArmorProtective_Head', ['Head']), (r'^ArmorProtective_UpperBody', ['Torso']),
    (r'^ArmorProtective_LowerBody', ['LowerBody']), (r'^ArmorProtective_Forearm', ['Forearm']),
    (r'^ArmorJewelry_Ring', ['Finger1', 'Finger2']),
    (r'^WeaponHunting_Bow|^WeaponMagical_Staff|^WeaponArmor_Shield', ['LeftHand']),
    (r'^Weapon', ['RightHand', 'LeftHand']),
]
SKIP_SKILL_CLASS = re.compile(r'^(Skill_AllPetAttack|Skill_SpawnPet|Skill_Mastery)$|OnItemUsed')
MOD_CLASS = re.compile(r'Skill_Modifier|ProjectileModifier|^SkillSecondary')
CHILD_FIELD = re.compile(r'^(skillCastName|skillNameCastOnDamage_\w+|buffSkillName|petSkillName|spawnObjects)$')
WFLAGS = ['Sword', 'Axe', 'Mace', 'Spear', 'Bow', 'Staff', 'RangedOneHand', 'Shield']
WEAPON_KIND = {'WeaponMelee_Sword': 'Sword', 'WeaponMelee_Axe': 'Axe', 'WeaponMelee_Mace': 'Mace',
               'WeaponHunting_Spear': 'Spear', 'WeaponHunting_Bow': 'Bow', 'WeaponMagical_Staff': 'Staff',
               'WeaponHunting_RangedOneHand': 'RangedOneHand', 'WeaponArmor_Shield': 'Shield'}
# AI role by skill Class (vanilla Monster/Pet wiring statistics, probe_skills.txt)
ROLE = [(r'Toggled$|^Skill_OnHitAttackRadius$', 'toggle'), (r'^Skill_WeaponPool_', 'pool'),
        (r'^Skill_BuffOther$', 'buffother'), (r'^Skill_GiveBonus$', 'heal'),
        (r'^Skill_Passive|^Skill_WPAttack|^Skill_PassiveOn', 'passive')]
# specialAttack parameters per Class: (Range, Chance, Delay, Timeout) = vanilla modal range / medians
SPECIAL = {
    'Skill_AttackProjectile': ('MediumRange', 50, 4, 1), 'Skill_AttackWeapon': ('ShortRange', 50, 5, 1),
    'Skill_AttackRadius': ('ShortRange', 50, 9, 2), 'Skill_AttackProjectileAreaEffect': ('MediumRange', 33, 8, 1),
    'Skill_AttackProjectileBurst': ('MediumRange', 50, 5, 1), 'Skill_AttackWave': ('MediumRange', 33, 5, 1),
    'Skill_AttackProjectileRing': ('ShortRange', 50, 7, 2), 'Skill_AttackWeaponCharge': ('MediumRange', 100, 12, 2),
    'Skill_AttackSpell': ('ShortRange', 45, 5, 2), 'Skill_AttackSpellChaos': ('AnyRange', 50, 6, 2),
    'Skill_AttackProjectileSpawnPet': ('AnyRange', 33, 6, 1), 'Skill_AttackProjectileDebuf': ('AnyRange', 40, 12, 2),
    'Skill_BuffRadius': ('AnyRange', 50, 30, 2), 'Skill_BuffSelfDuration': ('AnyRange', 25, 12, 0),
    'Skill_BuffAttackRadiusDuration': ('ShortRange', 25, 15, 0), 'Skill_AttackBuff': ('AnyRange', 35, 10, 2),
    'Skill_AttackBuffRadius': ('AnyRange', 50, 10, 1), 'Skill_AttackChain': ('AnyRange', 25, 6, 0.5),
    'Skill_AttackRadiusLightning': ('AnyRange', 50, 8, 1), 'Skill_DispelMagic': ('AnyRange', 38, 4, 1),
    'Skill_AttackProjectileFan': ('MediumRange', 20, 4, 0), 'Skill_AttackProjectileMultiHit': ('LongRange', 25, 7, 2),
    'Skill_DefensiveWall': ('AnyRange', 22, 10, 1.5), 'Skill_DefensiveGround': ('MediumRange', 15, 15, 0),
    'Skill_DefensiveProjectileGroundRing': ('AnyRange', 30, 5, 0), 'Skill_DropProjectileTelekinesis': ('AnyRange', 25, 8, 2),
    'Skill_AttackSpellTeleportSelf': ('LongRange', 5, 11, 0), 'Skill_AttackWeaponBlink': ('AnyRange', 99, 10, 0.5),
    'Skill_BuffSelfImmobilize': ('ShortRange', 20, 10, 0), 'Skill_AttackInherent': ('ShortRange', 40, 5, 1),
    'Skill_AttackWeaponRangedSpread': ('AnyRange', 34, 2, 1),
}
SPECIAL_DEFAULT = ('AnyRange', 40, 6, 1)
CAP = {'toggle': 4, 'pool': 1, 'buffother': 3, 'heal': 1, 'attack': 5}
ROLE_ORDER = ['toggle', 'pool', 'buffother', 'heal', 'attack', 'passive']
CONTROLLERS = ('records\\xpack\\ai controllers\\pet\\controller_licheking_normal.dbr',
               'records\\xpack\\ai controllers\\pet\\controller_licheking_aggressive.dbr',
               'records\\xpack\\ai controllers\\pet\\controller_licheking_defensive.dbr')
SUMMON_ICON = ('XPack3\\ui\\icons\\skills\\dreamimage_up.tex', 'XPack3\\ui\\icons\\skills\\dreamimage_down.tex')
AI_FIELDS = re.compile(r'^(attackSkillName|initialSkillName|healSkillName|healSkillDelay|berserkSkillName|dyingSkillName|'
                       r'buff(Self|Other)\d?SkillName|specialAttack\d?(SkillName|Chance|Delay|Range|Timeout))$')
RELIC_SRC = 'records\\xpack2\\item\\relics\\03_act5_nerthusmistletoe.dbr'          # vanilla one-piece relic
RELIC_BONUS_SRC = 'records\\item\\lootmagicalaffixes\\relics\\bonusesegypt\\03\\03_anubiswrath_attint.dbr'  # grants Wraith Lord
RELIC_TABLE_SRC = 'records\\item\\lootmagicalaffixes\\relics\\03_act2_amunrasglory.dbr'
RELIC_SLOTS = ['amulet', 'bracelet', 'ring', 'armband', 'helmet', 'greaves', 'bodyArmor', 'shield', 'bow', 'spear',
               'staff', 'axe', 'mace', 'sword', 'rangedOneHand']
RELIC_FITS = {'ring'}   # owner 19.09: rings only -> two ring slots = at most two companions
# Game.dll rolls a relic's completion bonus ONLY in ItemRelic::AddShards (0x101c55c0), when adding shards makes it
# complete. A one-piece relic is born complete and never gets a bonus (saves showed relicBonus empty) -> 2 shards.
RELIC_SHARDS = 2
CTRL_SRC = 'records\\xpack\\ai controllers\\pet\\controller_licheking_aggressive.dbr'
FAST_CONTROLLER = {   # vanilla pet controllers: sight anger 1-6/s, tolerance 1-5 -> companions lag; these react at once
    'ViewDistance': 24.0, 'InnerViewDistance': 8.0, 'AngerTolerance': 1.0, 'SightAngerRate': 20.0,
    'InnerSightAngerRate': 40.0, 'AttackedAnger': 20.0, 'AllyAttackedAnger': 25.0, 'ProjectileAnger': 10.0,
    'ForgiveRate': 1.0, 'MaxPursuitDistance': 26.0, 'TeleportToLeaderDistance': 27.2, 'WanderDistance': 5.0,
}
ORB_CHANCE = 10.0      # % per LEGENDARY electrum orb: one eidolon shard of a random companion (2 shards = 1 eidolon)
ORB_TIER = '_3l_'      # legendary orbs only (x4_ElectrumOrb_*_3l_Loot)
AGGR_CONTROLLER = dict(FAST_CONTROLLER, MaxPursuitDistance=32.0, TeleportToLeaderDistance=30.0, WanderDistance=7.0)
GAP_SRC = 'records\\xpack\\game\\gameengine.dbr'   # monsterLevelGapFixer: level the game adds per difficulty
PET_PANEL_SRC = 'records\\xpack2\\quests\\npc\\non speaking\\side\\x2sq23_ylva_companion.dbr'  # humanoid pet icon
PET_RANGE_SRC = 'records\\xpack3\\skills\\item skills\\pet\\pet_atl_lobster.dbr'        # ring-summoned permanent pet
RELIC_LOOK_SRC = 'records\\xpack\\item\\relics\\01_act4_shadeofhektor.dbr'              # «Сущность духа Гектора»
SUMMON_FX_SRC = 'records\\skills\\spirit\\wraithlordsummons.dbr'
RUN_SPEED = 1.5        # player base 1.33, vanilla doppel 1.2, Ylva 1.4; the player's +move speed gear outruns 1.33
REGISTRY = os.path.join(paths.data_dir(), 'registry.json')   # every companion ever built: cid -> name
LOG = []
def log(*a):
    s = ' '.join(str(x) for x in a); print(s, flush=True); LOG.append(s)


def i32(raw, off):
    return struct.unpack_from('<i', raw, off)[0]


def save_extra(path):
    """base attributes ('temp' x5), player texture, from Player.chr"""
    raw = open(path, 'rb').read()
    def after(key):
        out = []
        for m in re.finditer(re.escape(key), raw):
            s = m.start()
            if s >= 4 and i32(raw, s - 4) == len(key):
                out.append(m.end())
        return out
    temps = [struct.unpack_from('<f', raw, e)[0] for e in after(b'temp')]
    tex = ''
    for e in after(b'playerTexture'):
        n = i32(raw, e)
        tex = raw[e + 4:e + 4 + n].decode('latin1')
        break
    # [?, str, dex, int, life, mana]
    attrs = dict(zip(('str', 'dex', 'int', 'life', 'mana'), temps[1:6])) if len(temps) >= 6 else {}
    return attrs, tex


def parse_equipment(path):
    """Exact equipped items: the stream after 'equipmentCtrlIOStreamVersion' lists slots in order
    (head, amulet, torso, legs, forearm, ring, ring, weapon set 0 R/L, weapon set 1 R/L, artifact);
    after every item comes 'itemAttached' - 1 = worn now (the inactive weapon set has 0)."""
    raw = open(path, 'rb').read()
    i = raw.find(b'equipmentCtrlIOStreamVersion') - 4
    n = len(raw)
    items, cur, last_key = [], None, None
    while 0 <= i and i + 4 <= n:
        l = i32(raw, i)
        if 1 <= l <= 200 and i + 4 + l <= n and re.fullmatch(rb'[ -~]+', raw[i + 4:i + 4 + l]):
            tok = raw[i + 4:i + 4 + l].decode('latin1')
            i += 4 + l
            if tok in ('baseName', 'prefixName', 'suffixName', 'relicName'):
                last_key = tok
                continue
            if tok == 'itemAttached':
                if cur is not None:
                    cur['attached'] = i32(raw, i) == 1
                    items.append(cur)
                    cur = None
                continue
            if tok in ('storedType', 'skillName'):          # the hot-bar section starts: equipment is over
                break
            if last_key == 'baseName' and tok.lower().endswith('.dbr'):
                cur = {'base': tok, 'prefix': '', 'suffix': '', 'attached': False}
            elif last_key in ('prefixName', 'suffixName') and cur is not None and tok.lower().endswith('.dbr'):
                cur['prefix' if last_key == 'prefixName' else 'suffix'] = tok
            last_key = None
            continue
        i += 1
    return [it for it in items if it['attached']]


def load_base(base_arz):
    """the untouched game database, via a pickle cache keyed by size+mtime (Arz.load takes ~20 s)"""
    import pickle
    st = os.stat(base_arz)
    cache = os.path.join(paths.data_dir(), 'cache', 'base_%d_%d.pickle' % (st.st_size, int(st.st_mtime)))
    if os.path.exists(cache):
        try:
            with open(cache, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    a = Arz.load(base_arz)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    for old in glob.glob(os.path.join(os.path.dirname(cache), 'base_*.pickle')):
        os.remove(old)
    with open(cache, 'wb') as f:
        pickle.dump(a, f, 4)
    return a


class Builder(object):
    def __init__(self, base_arz):
        log('loading the game database ...')
        self.db = DB(LazyArz.load(base_arz))   # lazy: ~100 MB instead of several GB
        self.R = self.db.arz.records
        self.vt = {'ru': load_game_text('ru'), 'en': load_game_text('en')}
        self.text = {'ru': [], 'en': []}
        self.report = []
        self.cids = set()
        self.registry, self.folders = load_registry()
        self.known = set(self.registry)

    def tag(self, name, ru, en):
        self.text['ru'].append((name, ru)); self.text['en'].append((name, en))
        return name

    def clone(self, src, dst):
        return self.db.clone(src, dst.lower())

    # ------------------------------------------------------------ gear
    def item_table(self, cid, slot, it):
        """a dynamic loot table that can only give THIS item with THESE affixes"""
        db = self.db
        base = self.R.get(key_of(it['base']))
        if base is None:
            return None
        t = self.clone(DYN_SRC, NS + 'gear\\%s_%s.dbr' % (cid, slot))
        for vn, vt, vals in list(t['vars']):
            if vn != 'templateName' and vn != 'Class':
                delv(t, vn)
        setv(t, 'itemNames', [base['name']])
        # never a zero slope (18.09: [0.0] made the table empty); the level window is centred on the item itself,
        # so the pick does not depend on the companion's level
        lvl = int(get1(base, 'itemLevel', 0) or 0)
        setv(t, 'bellSlope', [200.0, 400.0, 600.0], 1)
        setv(t, 'defaultWeight', 1.0, 1)
        setv(t, 'minItemLevelEquation', '%d' % max(0, lvl - 2))
        setv(t, 'maxItemLevelEquation', '%d' % (lvl + 2))
        setv(t, 'targetLevelEquation', '%d' % lvl)
        for kind in ('prefix', 'suffix'):
            aff = self.R.get(key_of(it[kind])) if it[kind] else None
            if aff is None:
                continue
            rt = self.clone('records\\item\\lootmagicalaffixes\\prefix\\tablesjewelry\\ring_l01.dbr',
                            NS + 'gear\\%s_%s_%s.dbr' % (cid, slot, kind))
            for vn, vt, vals in list(rt['vars']):
                if vn.startswith('randomizer'):
                    delv(rt, vn)
            setv(rt, 'randomizerName1', aff['name'])
            setv(rt, 'randomizerWeight1', 100, 0)
            setv(t, '%sRandomizerName1' % kind, rt['name'])
            setv(t, '%sRandomizerWeight1' % kind, 100, 0)
            setv(t, '%sRandomizerChance' % kind, 100.0, 1)
        has_p = bool(it['prefix'] and self.R.get(key_of(it['prefix'])))
        has_s = bool(it['suffix'] and self.R.get(key_of(it['suffix'])))
        setv(t, 'bothPrefixSuffix', 100 if (has_p and has_s) else 0, 0)
        setv(t, 'prefixOnly', 100 if (has_p and not has_s) else 0, 0)
        setv(t, 'suffixOnly', 100 if (has_s and not has_p) else 0, 0)
        setv(t, 'noPrefixNoSuffix', 100 if not (has_p or has_s) else 0, 0)
        setv(t, 'FileDescription', 'TQMod companion gear: %s %s' % (cid, slot))
        return t['name']

    # ----------------------------------------------------------- skills
    def trees(self):
        """skill-tree order and the parent of every modifier (nearest preceding normal skill in its tree)"""
        if hasattr(self, '_tree_pos'):
            return
        self._tree_pos, self._tree_parent = {}, {}
        for ti, k in enumerate(sorted(x for x in self.R if 'skilltree' in x)):
            r = self.R[k]
            if not (get1(r, 'templateName', '') or '').lower().endswith('skilltree.tpl'):
                continue
            last = None
            for i in range(1, 60):
                sn = get1(r, 'skillName%d' % i, '')
                if not sn:
                    continue
                sk = key_of(sn)
                self._tree_pos.setdefault(sk, (ti, i))
                c = get1(self.R.get(sk), 'Class', '') if self.R.get(sk) is not None else ''
                if MOD_CLASS.search(c or ''):
                    if last:
                        self._tree_parent.setdefault(sk, last)
                elif c != 'Skill_Mastery':
                    last = sk

    def parent_of(self, k, taken):
        r = self.R[k]
        dep = [key_of(x) for x in (getv(r, 'skillDependancy') or []) if x]
        for d in dep:
            if d in taken:
                return d
        if k in self._tree_parent and self._tree_parent[k] in taken:
            return self._tree_parent[k]
        stem = k.split(BS)[-1][:-4]
        for t in sorted(taken, key=lambda x: -len(x)):
            ts = t.split(BS)[-1][:-4]
            if len(ts) >= 5 and ts in stem and ts != stem:
                return t
        return None

    def pick_skills(self, skills, weapons):
        """-> ordered [(key, name, level, class, role)] (modifiers right after their parent), dropped [(leaf, why)]"""
        self.trees()
        best = {}
        for sname, lv in skills:
            k = key_of(sname)
            best[k] = max(best.get(k, 0), lv)
        best = {k: lv for k, lv in best.items() if self.R.get(k) is not None}
        children = set()
        for k in best:
            for vn, vt, vals in self.R[k]['vars']:
                if CHILD_FIELD.match(vn):
                    children.update(key_of(x) for x in vals if isinstance(x, str) and x)
        melee = sum(1 for w in weapons if w not in ('Shield', 'Bow', 'Staff'))
        dropped, cand = [], {}
        for k, lv in best.items():
            r = self.R[k]
            c = get1(r, 'Class', '') or ''
            leaf = k.split(BS)[-1]
            if SKIP_SKILL_CLASS.search(c):
                continue
            if k in children:
                dropped.append((leaf, 'cast by another skill')); continue
            flags = [f for f in WFLAGS if get1(r, f, 0)]
            if flags and not set(flags) & set(weapons):
                dropped.append((leaf, 'needs ' + '/'.join(flags))); continue
            if get1(r, 'dualWieldOnly', 0) and melee < 2:
                dropped.append((leaf, 'dual wield only')); continue
            cand[k] = (lv, c)
        # one exclusive toggle (the engine switches the others off): highest level, then skill-tree order
        def exclusive(k):
            r = self.R[k]
            bs = get1(r, 'buffSkillName', '')
            b = self.R.get(key_of(bs)) if bs else None
            return bool(get1(r, 'exclusiveSkill', 0) or (b is not None and get1(b, 'exclusiveSkill', 0)))
        excl = sorted([k for k in cand if exclusive(k)], key=lambda k: (-cand[k][0], self._tree_pos.get(k, (999, 0))))
        for k in excl[1:]:
            dropped.append((k.split(BS)[-1], 'exclusive with ' + excl[0].split(BS)[-1]))
            cand.pop(k)
        normal = {k: v for k, v in cand.items() if not MOD_CLASS.search(v[1])}
        mods = collections.defaultdict(list)
        for k, (lv, c) in cand.items():
            if MOD_CLASS.search(c):
                par = self.parent_of(k, set(normal))
                if par is None:
                    dropped.append((k.split(BS)[-1], 'parent not taken'))
                else:
                    mods[par].append(k)

        def role(c):
            if c in SPECIAL or c.startswith('Skill_Attack') or c.startswith('Skill_Defensive'):
                return 'attack'
            return next((ro for rx, ro in ROLE if re.search(rx, c)), 'attack' if c.startswith('Skill_') else 'passive')

        def quest(k):
            return bool(re.search(r'quests' + re.escape(BS) + r'rewards|hcdungeon', k))
        groups = sorted(normal, key=lambda k: (quest(k), ROLE_ORDER.index(role(normal[k][1])), -normal[k][0],
                                               self._tree_pos.get(k, (999, 0)), k))
        out, used = [], collections.Counter()
        for k in groups:
            lv, c = normal[k]
            ro = role(c)
            if ro in CAP and used[ro] >= CAP[ro]:
                dropped.append((k.split(BS)[-1], 'no free AI slot for ' + ro)); continue
            if len(out) >= MAX_SKILLS:
                dropped.append((k.split(BS)[-1], 'all %d skill slots full' % MAX_SKILLS)); continue
            used[ro] += 1
            out.append((k, self.R[k]['name'], lv, c, ro))
            for m in sorted(mods.get(k, []), key=lambda m: self._tree_pos.get(m, (999, 0))):
                if len(out) >= MAX_SKILLS:
                    dropped.append((m.split(BS)[-1], 'all %d skill slots full' % MAX_SKILLS)); continue
                out.append((m, self.R[m]['name'], cand[m][0], cand[m][1], 'mod'))
        return out, dropped

    def wire_ai(self, pet, chosen):
        for vn, vt, vals in list(pet['vars']):
            if AI_FIELDS.match(vn):
                delv(pet, vn)
        toggles = [x for x in chosen if x[4] == 'toggle']
        if toggles:
            setv(pet, 'initialSkillName', toggles[0][1])
            for i, x in enumerate(toggles[1:4]):
                setv(pet, 'buffSelf%sSkillName' % ('' if i == 0 else i + 1), x[1])
        for x in [x for x in chosen if x[4] == 'pool'][:1]:
            setv(pet, 'attackSkillName', x[1])
        for i, x in enumerate([x for x in chosen if x[4] == 'buffother'][:3]):
            setv(pet, 'buffOther%sSkillName' % ('' if i == 0 else i + 1), x[1])
        for x in [x for x in chosen if x[4] == 'heal'][:1]:
            setv(pet, 'healSkillName', x[1])
            setv(pet, 'healSkillDelay', 3.0, 1)
        wired = []
        for i, x in enumerate([x for x in chosen if x[4] == 'attack'][:5]):
            p = 'specialAttack' + ('' if i == 0 else str(i + 1))
            rng, ch, dl, to = SPECIAL.get(x[3], SPECIAL_DEFAULT)
            setv(pet, p + 'SkillName', x[1])
            setv(pet, p + 'Range', rng)
            setv(pet, p + 'Chance', float(ch), 1)
            setv(pet, p + 'Delay', float(dl), 1)
            setv(pet, p + 'Timeout', float(to), 1)
            wired.append(x[0].split(BS)[-1])
        return wired

    def fold_passives(self, skills, taken):
        best = {}
        for s, lv in skills:
            k = key_of(s)
            best[k] = max(best.get(k, 0), lv)
        add = collections.Counter()
        for k, lv in best.items():
            if k in taken:
                continue
            r = self.R.get(k)
            if r is None:
                continue
            cls = get1(r, 'Class', '') or ''
            if not (cls == 'Skill_Mastery' or (cls == 'Skill_Passive' and re.search(r'quests' + re.escape(BS) + r'rewards|hcdungeon', k))):
                continue
            for key, field in (('str', 'characterStrength'), ('dex', 'characterDexterity'), ('int', 'characterIntelligence'),
                               ('life', 'characterLife'), ('mana', 'characterMana')):
                v = getv(r, field)
                if v:
                    add[key] += float(v[min(len(v), max(1, lv)) - 1])
        return add

    # -------------------------------------------------------- companion
    def companion(self, path):
        c = read_char(path)
        name = c['name']
        if c['level'] < MIN_LEVEL or not c['masteries']:
            log('  skip %s (level %d, masteries %d)' % (name, c['level'], len(c['masteries'])))
            return None
        attrs, tex = save_extra(path)
        gender = 'female' if 'female' in tex.lower() else 'male'
        # record-name id, once given to a save folder it never changes (items in saves point at these records)
        folder = os.path.basename(os.path.dirname(path)).lower()
        cid = self.folders.get(folder)
        if not cid:
            latin = re.fullmatch(r'[ -~]+', name) is not None
            cid = (re.sub(r'[^a-z0-9]+', '', name.lower()) if latin else '') or \
                'c' + hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
            claimed = set(self.folders.values())
            # a known id without a folder (made before ids were pinned to folders) belongs to the hero whose name
            # gives it; only an id already pinned to ANOTHER folder or used in this run needs a suffix
            if cid in self.cids or cid in claimed:
                cid += '_' + hashlib.md5(folder.encode('utf-8')).hexdigest()[:4]
            self.folders[folder] = cid
        self.cids.add(cid)
        db = self.db
        pet = self.clone(PET_SRC, NS + '%s_pet.dbr' % cid)
        pc = self.R.get(key_of(PC[gender]))
        # look: the character's own body, texture and animations
        for vn, vt, vals in list(pet['vars']):
            if 'Anim' in vn or vn in ('charAnimationTableName',):
                delv(pet, vn)
        for vn, vt, vals in pc['vars']:
            if 'Anim' in vn or vn == 'charAnimationTableName':
                setv(pet, vn, list(vals), vt)
        setv(pet, 'mesh', get1(pc, 'mesh'))
        setv(pet, 'baseTexture', tex or get1(pc, 'baseTexture'))
        setv(pet, 'characterGenderProfile', get1(pc, 'characterGenderProfile') or gender.capitalize())
        # Class Pet -> the pet panel (health/mana, stance, dismiss); the doppel's own switches go away
        setv(pet, 'templateName', 'database\\Templates\\Pet.tpl')
        setv(pet, 'Class', 'Pet')
        delv(pet, 'doppelSkills')
        delv(pet, 'doppelGear')
        setv(pet, 'dropItems', 0, 3)
        setv(pet, 'controller', self.fast_controller())
        setv(pet, 'controllerAggressive', self.fast_controller('aggressive'))
        setv(pet, 'controllerDefensive', CONTROLLERS[2])
        equipped = parse_equipment(path)
        weapons = []
        for it in equipped:
            b = self.R.get(key_of(it['base']))
            k = WEAPON_KIND.get(get1(b, 'Class', '') if b is not None else '')
            if k:
                weapons.append(k)
        L = int(c['level'])
        # Class Pet does NOT get monsterLevelGapFixer (in game 19.09: [85,77,73] showed 73 on Legendary;
        # as Class Monster [85,85,85] had shown 97) -> the save's level on every difficulty
        setv(pet, 'charLevel', [L, L, L], 0)
        setv(pet, 'characterRunSpeed', RUN_SPEED, 1)
        for key, field in (('str', 'characterStrength'), ('dex', 'characterDexterity'), ('int', 'characterIntelligence'),
                           ('life', 'characterLife'), ('mana', 'characterMana')):
            if attrs.get(key):
                setv(pet, field, [float(attrs[key])], 1)
        # skills
        for vn, vt, vals in list(pet['vars']):
            if re.match(r'skill(Name|Level)\d+$', vn):
                delv(pet, vn)
        chosen, dropped = self.pick_skills(c['skills'], weapons)
        # masteries and quest-reward passives are not in the 17 slots: fold their flat bonuses
        # (life, str/dex/int, mana) into the base stats, as the game adds them on top of the save's values
        folded = self.fold_passives(c['skills'], {x[0] for x in chosen})
        for key, field in (('str', 'characterStrength'), ('dex', 'characterDexterity'), ('int', 'characterIntelligence'),
                           ('life', 'characterLife'), ('mana', 'characterMana')):
            if attrs.get(key) or folded.get(key):
                setv(pet, field, [float(attrs.get(key, 0) + folded.get(key, 0))], 1)
        for i, (k, nm, lv, cls, ro) in enumerate(chosen, 1):
            setv(pet, 'skillName%d' % i, nm)
            setv(pet, 'skillLevel%d' % i, [int(lv)], 0)
        wired = self.wire_ai(pet, chosen)
        # what every vanilla permanent pet has and the doppel clone lacked: pet panel + hover widget, AI range classes
        self.copy_fields(PET_PANEL_SRC, pet, ('showStatusWidgetWhenPet', 'StatusIcon', 'StatusIconRed', 'healSkillDelay'))
        self.copy_fields(PET_RANGE_SRC, pet, ('mediumRangeMin', 'longRangeMin'))
        self.copy_fields(PC[gender], pet, ('actorRadius', 'actorHeight'))
        delv(pet, 'distressCallGroup')
        # gear
        for vn, vt, vals in list(pet['vars']):
            if re.match(r'^(chanceToEquip|loot)(Head|Torso|LowerBody|Forearm|Finger1|Finger2|RightHand|LeftHand|Misc\d)', vn):
                delv(pet, vn)
        used = set(); gear = []; skipped = []
        for it in equipped:
            base = self.R.get(key_of(it['base']))
            cls = get1(base, 'Class', '') if base is not None else ''
            slots = next((s for rx, s in SLOT_BY_CLASS if re.search(rx, cls or '')), None)
            slot = next((s for s in (slots or []) if s not in used), None)
            if slot is None:
                skipped.append((it['base'].split(BS)[-1], cls))
                continue
            unique = (get1(base, 'itemClassification', '') or '') in ('Epic', 'Legendary')
            tab = base['name'] if (cid in DIRECT_GEAR or (unique and cid not in UNIQUE_AFFIX_TEST)) else self.item_table(cid, slot, it)
            if tab is None:
                skipped.append((it['base'].split(BS)[-1], 'missing record'))
                continue
            used.add(slot)
            setv(pet, 'chanceToEquip%s' % slot, 100.0, 1)
            setv(pet, 'chanceToEquip%sItem1' % slot, 100, 0)
            setv(pet, 'loot%sItem1' % slot, [tab, tab, tab])
            gear.append((slot, self.vt['ru'].get(get1(base, 'itemNameTag', '') or get1(base, 'description', '') or '', '')
                         or it['base'].split(BS)[-1]))
        title_ru = '%s ~ соратник' % name
        setv(pet, 'description', self.tag('tagTQComp_%s_pet' % cid, title_ru, '%s ~ Companion' % name))
        setv(pet, 'FileDescription', 'TQMod companion from save %s (level %d)' % (name, L))
        # summon skill
        sk = self.clone(SUMMON_SRC, NS + '%s_summon.dbr' % cid)
        setv(sk, 'spawnObjects', [pet['name']])
        delv(sk, 'spawnObjectsTimeToLive')
        setv(sk, 'petLimit', 1, 0)
        setv(sk, 'skillMaxLevel', 1, 0)
        setv(sk, 'skillCooldownTime', 40.0, 1)
        setv(sk, 'skillManaCost', 150.0, 1)
        self.copy_fields(SUMMON_FX_SRC, sk, ('targetFxPakName',))
        setv(sk, 'skillUpBitmapName', SUMMON_ICON[0])
        setv(sk, 'skillDownBitmapName', SUMMON_ICON[1])
        setv(sk, 'skillDisplayName', self.tag('tagTQComp_%s_skill' % cid, 'Призвать соратника: %s' % name,
                                              'Summon Companion: %s' % name))
        setv(sk, 'skillBaseDescription', self.tag('tagTQComp_%s_skilldesc' % cid,
             'Зовёт на помощь персонажа %s — с его уровнем, умениями и снаряжением из сохранения.' % name,
             'Calls %s from your saves - with their level, skills and gear.' % name))
        ring = self.make_ring(cid, name, None)   # rings retired 19.09: inert record, old rings in saves stay valid
        relic = self.make_relic(cid, name, sk)
        self.relics.append(relic['name'])
        self.report.append((name, L, gender, [(x[0].split(BS)[-1], x[2], x[4]) for x in chosen],
                            dropped, gear, skipped, wired))
        return ring['name']

    def copy_fields(self, src, dst, names):
        """copy fields from a vanilla record keeping their value types (a wrong type reads as the default)"""
        r = self.R[key_of(src)]
        have = {vn: (vt, vals) for vn, vt, vals in r['vars']}
        for n in names:
            if n not in have:
                raise SystemExit('%s has no %s' % (src, n))
            vt, vals = have[n]
            setv(dst, n, list(vals) if len(vals) > 1 else vals[0], vt)

    def make_ring(self, cid, name, sk):
        ring = self.clone(RING_SRC, NS + '%s_ring.dbr' % cid)
        if sk is not None:
            setv(ring, 'itemSkillName', sk['name'])
            setv(ring, 'itemSkillLevel', 1, 0)
            setv(ring, 'itemNameTag', self.tag('tagTQComp_%s_ring' % cid, 'Кольцо соратника: %s' % name,
                                               'Companion Ring: %s' % name))
        else:
            setv(ring, 'itemNameTag', self.tag('tagTQComp_%s_ring' % cid, 'Потускневшее кольцо: %s' % name,
                                               'Faded Ring: %s' % name))
        setv(ring, 'itemClassification', 'Legendary')
        setv(ring, 'levelRequirement', 1, 0)
        setv(ring, 'itemLevel', 1, 0)
        return ring

    def make_relic(self, cid, name, sk):
        """one-piece relic for any item type; its completion bonus (an affix) grants the summon skill.
        sk None = tombstone of a deleted character: same record names, no skill"""
        bon = self.clone(RELIC_BONUS_SRC, NS + '%s_relic_bonus.dbr' % cid)
        for vn, vt, vals in list(bon['vars']):
            if vn not in ('templateName', 'Class', 'characterBaseAttackSpeedTag'):
                delv(bon, vn)
        if sk is not None:
            setv(bon, 'itemSkillName', sk['name'])
            setv(bon, 'itemSkillLevel', 1, 0)
        setv(bon, 'FileDescription', 'TQMod companion relic bonus: %s' % name)
        tab = self.clone(RELIC_TABLE_SRC, NS + '%s_relic_bonustable.dbr' % cid)
        for vn, vt, vals in list(tab['vars']):
            if vn.startswith('randomizer'):
                delv(tab, vn)
        setv(tab, 'randomizerName1', bon['name'])
        setv(tab, 'randomizerWeight1', 100, 0)
        relic = self.clone(RELIC_SRC, NS + '%s_relic.dbr' % cid)
        for vn, vt, vals in list(relic['vars']):
            if vn.startswith('racialBonus'):
                delv(relic, vn)
        setv(relic, 'bonusTableName', tab['name'])
        self.copy_fields(RELIC_LOOK_SRC, relic, ('shardBitmap', 'relicBitmap'))
        setv(relic, 'completedRelicLevel', RELIC_SHARDS, 0)
        for q in RELIC_SLOTS:
            setv(relic, q, 1 if q in RELIC_FITS else 0, 3)   # BOOL: Game.dll reads these with the bool getter
        setv(relic, 'levelRequirement', 1, 0)
        setv(relic, 'itemCost', [5000, 5000, 5000], 0)
        if sk is not None:
            setv(relic, 'description', self.tag('tagTQComp_%s_relic' % cid, 'Эйдолон: %s' % name, 'Eidolon: %s' % name))
            setv(relic, 'itemText', self.tag('tagTQComp_%s_relictext' % cid,
                 'Призрачный образ героя %s из иного странствия. Соедини два образа и вложи в кольцо — и герой '
                 'придёт на зов таким, каков он сейчас.' % name,
                 'The ghostly image of %s from another journey. Join two images and set them into a ring - and the '
                 'hero will answer your call as they are now.' % name))
        else:
            setv(relic, 'description', self.tag('tagTQComp_%s_relic' % cid, 'Угасший эйдолон: %s' % name,
                                                'Faded Eidolon: %s' % name))
            setv(relic, 'itemText', self.tag('tagTQComp_%s_relictext' % cid,
                 'Образ угас: героя %s больше нет среди твоих странствий.' % name,
                 'The image has faded: %s is no longer among your journeys.' % name))
        setv(relic, 'FileDescription', 'TQMod companion relic: %s%s' % (name, '' if sk is not None else ' (faded)'))
        return relic

    def tombstone(self, cid, name):
        """a deleted character: keep only inert records that items in saves may still point at"""
        sk = self.clone(SUMMON_SRC, NS + '%s_summon.dbr' % cid)
        for vn, vt, vals in list(sk['vars']):
            if vn.startswith('spawnObjects'):
                delv(sk, vn)
        setv(sk, 'skillDisplayName', self.tag('tagTQComp_%s_skill' % cid, 'Угасший зов: %s' % name, 'Faded Call: %s' % name))
        setv(sk, 'skillBaseDescription', self.tag('tagTQComp_%s_skilldesc' % cid,
             'Героя %s больше нет.' % name, '%s is gone.' % name))
        self.make_ring(cid, name, None)
        self.make_relic(cid, name, None)
        log('  tombstone: %s (save deleted)' % name)

    def fast_controller(self, kind='normal'):
        name = NS + ('controller_companion.dbr' if kind == 'normal' else 'controller_companion_%s.dbr' % kind)
        if self.R.get(name) is None:
            c = self.clone(CTRL_SRC, name)
            for k, v in (FAST_CONTROLLER if kind == 'normal' else AGGR_CONTROLLER).items():
                setv(c, k, v, 1)
            setv(c, 'FileDescription', 'TQMod companion: LicheKing aggressive + fast anger (%s)' % kind)
        return name

    def electrum(self, relics):
        """one eidolon shard with ORB_CHANCE % per LEGENDARY electrum orb, vanilla odds untouched"""
        if not relics:
            return
        shards = self.clone(RELIC_TABLE_SRC, NS + 'eidolon_shards.dbr')   # any record; rebuilt as a FixedWeight table
        for vn, vt, vals in list(shards['vars']):
            delv(shards, vn)
        setv(shards, 'templateName', 'database\\Templates\\LootItemTable_FixedWeight.tpl')
        setv(shards, 'Class', 'LootItemTable_FixedWeight')
        chunks = [relics[i:i + 30] for i in range(0, len(relics), 30)]   # lootName1..30 per table
        if len(chunks) == 1:
            for i, r in enumerate(relics, 1):
                setv(shards, 'lootName%d' % i, r)
                setv(shards, 'lootWeight%d' % i, 100, 0)
        else:
            setv(shards, 'templateName', 'database\\Templates\\LootMasterTable.tpl')
            setv(shards, 'Class', 'LootMasterTable')
            for c, chunk in enumerate(chunks, 1):
                t = self.clone(RELIC_TABLE_SRC, NS + 'eidolon_shards_%d.dbr' % c)
                for vn, vt, vals in list(t['vars']):
                    delv(t, vn)
                setv(t, 'templateName', 'database\\Templates\\LootItemTable_FixedWeight.tpl')
                setv(t, 'Class', 'LootItemTable_FixedWeight')
                for i, r in enumerate(chunk, 1):
                    setv(t, 'lootName%d' % i, r)
                    setv(t, 'lootWeight%d' % i, 100, 0)
                setv(shards, 'lootName%d' % c, t['name'])
                setv(shards, 'lootWeight%d' % c, 100 * len(chunk), 0)
        setv(shards, 'FileDescription', 'TQMod companions: one eidolon shard, companions equally likely')
        n = 0
        for k in sorted(self.R):
            if 'electrumorbs' not in k or not k.endswith('_loot.dbr') or ORB_TIER not in k:
                continue
            loot = self.R[k]
            slots = []
            for s_ in range(1, 7):
                ch = float(get1(loot, 'loot%dChance' % s_, 0) or 0)
                names = [(j, get1(loot, 'loot%dName%d' % (s_, j), '')) for j in range(1, 40)]
                names = [(j, x) for j, x in names if x]
                W = sum(float(get1(loot, 'loot%dWeight%d' % (s_, j), 0) or 0) for j, _ in names)
                if ch and W and ch + ORB_CHANCE <= 100:
                    slots.append((0 if any('relic' in x.lower() for _, x in names) else 1, ch, s_, W, len(names)))
            if not slots:
                log('  WARNING: no room for eidolons in %s' % k)
                continue
            _, ch, s_, W, cnt = min(slots)
            w = max(1, int(round(ORB_CHANCE * W / ch)))    # weights are ints; the chance absorbs the rounding
            j = next(j for j in range(1, 40) if not get1(loot, 'loot%dName%d' % (s_, j), ''))
            setv(loot, 'loot%dName%d' % (s_, j), shards['name'])
            setv(loot, 'loot%dWeight%d' % (s_, j), w, 0)
            setv(loot, 'loot%dChance' % s_, ch * (W + w) / W, 1)   # every vanilla entry keeps ch*w_i/W exactly
            self.db.mark(loot['name']); n += 1
        log('  eidolon shards in %d legendary electrum orbs, %.1f%% per orb' % (n, ORB_CHANCE))

    # ---------------------------------------------------------- merchant
    def sell(self, rings):
        db = self.db
        shop = self.clone('records\\xpack2\\item\\loottables\\misc\\dye_norse_all.dbr', NS + 'shop_rings.dbr')
        for vn, vt, vals in list(shop['vars']):
            if re.match(r'loot(Name|Weight)\d+$', vn):
                delv(shop, vn)
        for i, r in enumerate(rings, 1):
            setv(shop, 'lootName%d' % i, r)
            setv(shop, 'lootWeight%d' % i, 100, 0)
        targets = set()
        for k, r in self.R.items():
            for vn, vt, vals in r['vars']:
                if vt == 2 and vn.startswith('marketRingTable'):
                    targets.update(key_of(v) for v in vals if v)
        n_items = n_master = 0
        for k in sorted(targets):
            lt = self.R.get(k)
            if lt is None:
                continue
            tpl = (get1(lt, 'templateName', '') or '').lower()
            free = [i for i in range(1, 31) if not get1(lt, 'lootName%d' % i, '')]
            wmax = max([int(get1(lt, 'lootWeight%d' % i, 0) or 0) for i in range(1, 31)] or [100]) or 100
            if tpl.endswith('lootmastertable.tpl') and free:
                setv(lt, 'lootName%d' % free[0], shop['name'])
                setv(lt, 'lootWeight%d' % free[0], wmax * 3, 0)
                db.mark(lt['name']); n_master += 1
            elif tpl.endswith('lootitemtable_fixedweight.tpl') and len(free) >= len(rings):
                for r in rings:
                    i = free.pop(0)
                    setv(lt, 'lootName%d' % i, r)
                    setv(lt, 'lootWeight%d' % i, wmax * 3, 0)
                db.mark(lt['name']); n_items += 1
        log('  rings on sale: %d master tables, %d item tables' % (n_master, n_items))

    def run(self):
        rings, self.relics, active = [], [], {}
        for path in sorted(glob.glob(os.path.join(SAVES, '_*', 'Player.chr'))):
            r = self.companion(path)
            if r:
                rings.append(r)
                active[r.split(BS)[-1][:-len('_ring.dbr')]] = self.report[-1][0]
        reg = dict(self.registry)
        # heroes whose eidolons/rings/summons the saves still hold, even if the registry was lost
        for cid in referenced_cids():
            reg.setdefault(cid, cid)
        for cid, name in sorted(reg.items()):
            if cid not in active:
                self.tombstone(cid, name)
        reg.update(active)
        self.registry = reg
        self.electrum(self.relics)   # 19.09: nothing on sale any more - eidolons only from legendary electrum orbs
        os.makedirs(OUT, exist_ok=True)
        for lg in ('ru', 'en'):
            write_text_file(os.path.join(OUT, 'text', lg, 'zz_tqmod.txt'), self.text[lg])
        self.db.arz.save(os.path.join(OUT, 'database.arz'), level=1)   # rebuilt on every change: speed over size
        save_registry(self.registry, self.folders)
        with open(os.path.join(OUT, 'companions.txt'), 'w', encoding='utf-8') as f:
            for name, L, g, sk, dr, gear, skipped, wired in self.report:
                f.write('== %s (level %d, %s)\n' % (name, L, g))
                f.write('   skills (slot order, AI role):\n' + ''.join('     %2d %-44s L%-3s %s\n' % (i, a, b, c)
                                                                     for i, (a, b, c) in enumerate(sk, 1)))
                f.write('   AI special attacks: %s\n' % wired)
                f.write('   not taken:\n' + ''.join('     %-44s %s\n' % d for d in dr))
                f.write('   gear: %s\n   gear skipped: %s\n' % (gear, skipped))
        log('  companions: %s' % [r[0] for r in self.report])


def load_registry():
    """-> ({cid: name}, {save folder: cid}); an unreadable file is not fatal (the saves are scanned as well)"""
    try:
        d = json.load(open(REGISTRY, encoding='utf-8'))
    except FileNotFoundError:
        return {}, {}
    except Exception:
        log('  ! registry.json is unreadable - rebuilding it from the saves')
        return {}, {}
    if 'companions' in d:
        return dict(d['companions']), dict(d.get('folders', {}))
    return dict(d), {}          # 1.0 dev format: a flat {cid: name}


def save_registry(companions, folders):
    tmp = REGISTRY + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'companions': dict(sorted(companions.items())), 'folders': dict(sorted(folders.items()))},
                  f, ensure_ascii=False, indent=1)
    os.replace(tmp, REGISTRY)


def referenced_cids():
    """cids of our records that any save refers to (relic / ring / summon), straight from the Player.chr bytes"""
    out = set()
    pat = re.compile(re.escape(NS.encode()) + rb'([a-z0-9_]+?)_(?:relic_bonus|relic|ring|summon)\.dbr', re.I)
    for p in glob.glob(os.path.join(SAVES, '_*', 'Player.chr')):
        try:
            out.update(m.group(1).decode().lower() for m in pat.finditer(open(p, 'rb').read()))
        except Exception:
            pass
    return out


def inputs_fingerprint():
    """hash of everything a companion is built from (not of the save file itself: the game rewrites it on every save,
    and a rebuild after every session would cost a minute for nothing)"""
    h = hashlib.md5()
    for path in sorted(glob.glob(os.path.join(SAVES, '_*', 'Player.chr'))):
        try:
            c = read_char(path)
            data = {'name': c.get('name'), 'level': c.get('level'), 'masteries': c.get('masteries'),
                    'skills': c.get('skills'), 'extra': save_extra(path), 'gear': parse_equipment(path)}
        except Exception as e:
            data = {'path': path, 'error': str(e), 'size': os.path.getsize(path)}
        h.update(json.dumps(data, sort_keys=True, default=str).encode('utf-8'))
    return h.hexdigest()


def text_payload(lang):
    p = os.path.join(OUT, 'text', lang, 'zz_tqmod.txt')
    if not os.path.exists(p):
        return ''
    raw = open(p, 'rb').read()
    return raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8')


if __name__ == '__main__':      # development entry; players use tq_together.py / TQTogether.exe
    import installer, verify_companions
    game = paths.find_game()
    inst = installer.Installer(game, log)
    if '--uninstall' in sys.argv:
        inst.uninstall()
        sys.exit()
    base = inst.prepare()
    Builder(base).run()
    if '--install' in sys.argv:
        if installer.game_running():
            raise SystemExit('Titan Quest is running - close it first.')
        problems = verify_companions.check(os.path.join(OUT, 'database.arz'), base, log)
        if problems:
            raise SystemExit('\n'.join(problems) + '\nverify failed - not installed.')
        log('ALL CHECKS PASSED')
        inst.install(os.path.join(OUT, 'database.arz'), text_payload('ru'), text_payload('en'))
