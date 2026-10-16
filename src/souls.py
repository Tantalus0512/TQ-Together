# -*- coding: utf-8 -*-
"""Boss souls (1.6.0, 16.10.2026): every boss and hero monster of the game can become a companion.

A boss or a hero monster drops "Enslaved Soul: <name>" (1.6.1, owner's name; "Порабощённая душа") - a relic of
SoulBossShards (3) / SoulHeroShards (2) shards. Shards of the same soul combine like vanilla relic shards; the last
one rolls the completion bonus, which grants "Summon Enslaved Soul: <name>". The soul fits the AMULET only (owner 16.10): eidolons stay in the rings, so a hero can lead two eidolons and
one soul.

The summoned soul is the boss record turned into a Class Pet, the way the developers turned the boss Ylva
(loki_a_ylva_55) into the companion Ylva (x2sq23_ylva_companion): Pet.tpl, pet controllers, the pet panel; no next
stage on death, no dying skill, no music, gold or loot, no boss-only passives (GlobalProperties_*_Boss: +100 % damage
on Legendary). The pet gets the game's pet difficulty pak instead of the boss pak (Legendary: life +208 % instead of
+420 %), so a soul is weaker than the boss itself and stronger than an ordinary pet.

"A late boss must not be weak" (owner 16.10): the soul comes at the level of the hero about to be played
(tq_together.choose_hero), on every difficulty. From the boss's own Legendary level to the hero's, its mana and
attributes move along the game's own monster growth curve (research\\souls\\level_curve.py: 2129 vanilla level
variants - +2.4 %/level at Normal levels 20-40, +2.0 % at 40-60) and its skill levels by 0.165 per level (same
survey), capped by each skill's max level. Life is ONE value like a vanilla pet's: LIFE_ANCHOR (7500 for the median
boss at hero level 85) x how tough this boss is among bosses, held in a corridor (bosses x0.7..x1.5, heroes x0.4..x1:
Nessus' 1282 base life is not paper, Akhenaten's 105000 not immortal) x the same growth curve for the hero's level,
x SoulLife %. On Legendary the pet pak makes the median ~24k (1.6.5; 16.6k before); the game's strongest permanent
pets have 1.9-2.7k base (~8k).

Where souls drop (every vanilla item keeps its exact odds):
  - from the monster itself, a Misc loot slot: the eidolon shard's slot of 1.5.1 if there is one (shared, both odds
    exact), else an empty slot, else a vanilla slot whose chance leaves room. SoulBossChance / SoulHeroChance % per
    kill; a fight with k members dropping at the same level (Pharaoh's Honor Guard x4, Tiamat's 3 stages) gives the
    chance per FIGHT;
  - bosses that drop nothing themselves (the Aesir, Ylva, Mimir, most Eternal Embers bosses): their boss chest, found
    by its name (bosschest10_aesir_01..03 and repeat chests), SoulChestChance % per opening;
  - electrum orbs: SoulOrbChance % per orb for one soul shard of a random boss of the orb's region (Antiquity, Hades,
    Scandia, Atlantis, Jade Emperor, Thebes). Hero monsters are not in the orbs: 300 of them would dilute it to nothing.
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
DEFAULTS = (('souls', 1), ('soulheroes', 1), ('soulbossshards', 3), ('soulheroshards', 2), ('soulbosschance', 15.0),
            ('soulherochance', 12.0), ('soulorbchance', 10.0), ('soulchestchance', 15.0), ('soullife', 100.0),
            ('soulmaxscale', 1.3), ('soultestshop', ''))
LIMITS = {'soulbossshards': (2, 5), 'soulheroshards': (2, 5), 'soulbosschance': (0, 95), 'soulherochance': (0, 95),
          'soulorbchance': (0, 50), 'soulchestchance': (0, 95), 'soullife': (10, 1000), 'soulmaxscale': (0.5, 3)}


def settings():
    """TQTogether.ini: Souls=1, SoulHeroes=1, SoulBossShards=3, SoulHeroShards=2, SoulBossChance=15,
    SoulHeroChance=12, SoulOrbChance=10, SoulChestChance=15, SoulLife=100 (%), SoulMaxScale=1.3,
    SoulTestShop=arachne,nessus (shards sold by the ring merchants - for testing)"""
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
LIFE_ANCHOR, ANCHOR_LEVEL = 7500.0, 85


def anim_fixes(rec):
    """-> [(speed field, old, new, what)]: the animation speeds that bring this creature to RUN_LINE on the ground and
    within ATTACK_LINE / SPECIAL_LINE per attack / skill; empty for a creature already that quick. An animation missing
    from soul_anims.ANIMS is left as it is. The walk of a set is sped up with its run (Tartarus walks to run)."""
    from soul_anims import ANIMS
    F = {vn.lower(): (vn, vals) for vn, vt, vals in rec['vars']}
    val = lambda k, d: (F[k][1] if k in F and F[k][1] else d)
    scale = float(val('scale', [1.0])[0] or 1.0)
    run_stat = float(val('characterrunspeed', [1.0])[-1] or 1.0)
    atk_stat = float(val('characterattackspeed', [1.0])[-1] or 1.0)
    cast_stat = float(val('characterspellcastspeed', [1.0])[-1] or 1.0)   # spells and skill animations (1.6.4)
    out = []
    for low, (name, vals) in sorted(F.items()):
        m = ANIM_SET.match(name)
        if not m or not vals or not isinstance(vals[0], str) or not vals[0]:
            continue
        info = ANIMS.get(vals[0].lower().replace('/', BS))
        if not info:
            continue
        pre, kind, num = m.groups()
        spname = '%s%sAnimSpeed%s' % (pre, kind, num)
        sp = float(val(spname.lower(), [1.0])[0] or 1.0)
        k, what = 1.0, ''
        if kind == 'Run' and info[0] > 0:
            v = info[0] * scale * sp * run_stat
            if v < RUN_LINE - 1e-3:
                k, what = RUN_LINE / v, 'run %.1f -> %.1f m/s' % (v, RUN_LINE)
        elif kind == 'Attack' and info[1] > 0:
            t = info[1] / (sp * atk_stat)
            if t > ATTACK_LINE + 1e-3:
                k, what = t / ATTACK_LINE, 'attack %.1f -> %.1f s' % (t, ATTACK_LINE)
        elif kind == 'SpellAttack' and info[1] > 0:
            t = info[1] / (sp * cast_stat)
            if t > ATTACK_LINE + 1e-3:
                k, what = t / ATTACK_LINE, 'spell %.1f -> %.1f s' % (t, ATTACK_LINE)
        elif kind == 'Special' and info[1] > 0:
            t = info[1] / (sp * cast_stat)
            if t > SPECIAL_LINE + 1e-3:
                k, what = t / SPECIAL_LINE, 'skill %.1f -> %.1f s' % (t, SPECIAL_LINE)
        if k > 1.0 + 1e-6:
            out.append((spname, sp, sp * k, what))
            if kind == 'Run':
                wname = '%sWalkAnimSpeed' % pre
                if (pre + 'walkanim').lower() in F:
                    wsp = float(val(wname.lower(), [1.0])[0] or 1.0)
                    out.append((wname, wsp, wsp * k, what))
    return out


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
            ('demonic elemental', r'demonicelemental'), ('yaoguai', r'yaoguai'))
# electrum orb regions (x4_electrumorb_<region>_<tier>_loot): by the folder of the boss's own records
REGION_DIR = (('records' + BS + 'creature' + BS, '1_antiquity'), ('records' + BS + 'xpack' + BS, '2_hades'),
              ('records' + BS + 'xpack2' + BS, '3_scandia'), ('records' + BS + 'xpack3' + BS, '4_tiamat'))
CHINA_EN = ('feiyi', 'qiong qi', 'sihai', 'huoshen', 'shen ~', 'the ten suns', 'celestial accord', 'colossal fire elemental',
            'sanshou')
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
DROP_FIELDS = ('actorToSpawnOnDeath', 'actorToSpawnOnDeath2', 'treasureProxyName', 'dyingSkillName', 'MonsterMusic',
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
RUN_LINE = 7.0             # m/s on the ground at characterRunSpeed (about 0.85 of a hero without run bonuses)
ATTACK_LINE = 1.6          # s per basic attack: Arachne's slowest is 1.5 (median soul 1.2, Tartarus 2.4)
# 1.6.4 (owner: "the spells stayed as slow"): spells and skill animations play at characterSpellCastSpeed - Tartarus 1.0,
# Arachne 1.3 - and Tartarus casts most often the ones under the old line (lightning cone with the spell animation,
# fire spikes, fire walk). Cast speed at least Arachne's; skills at it within 2.0 s (Arachne's slowest: 2.5 / 1.3 = 1.9)
CAST_LINE = 1.3
SPECIAL_LINE = 2.0         # s per skill animation at the cast speed (Tartarus' meteor 4.3 s)
ANIM_SET = re.compile(r'^(\w+?)(Run|Walk|Attack|SpellAttack|Special)Anim(\d*)$')
BOSS_ONLY_SKILL = re.compile(r'globalproperties_\w*boss|globalproperties_\w*graeae|boss_conversionimmunity')
MISC_W = 100000                # weights of a slot we write: probabilities x MISC_W / chance


def fields(r):
    """{lowercase field name: values} - one pass instead of a scan of ~600 monster fields per lookup"""
    return {vn.lower(): vals for vn, vt, vals in r['vars']}


def misc_slots(r):
    """{slot n: {item value: % per kill}} of a monster's Misc loot (chance x weight / sum of weights of the entries
    that have an item), plus {n: problems} for slots that cannot be read as scalars"""
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
        out[n] = {it: c * float(w[0] or 0) / W for it, w in ents} if c and W else {}
    return out, odd


class Souls(object):
    def __init__(self, b, hero_level=0, hero=''):
        self.b, self.R, self.H, self.hero = b, b.R, int(hero_level or 0), hero
        self.st = settings()
        self.ns = b_ns() + SUB
        self.peek = getattr(b.R, 'peek', None) or b.R.__getitem__   # read-only: no cache
        self._memo = {}
        self.ledger = {'souls': {}, 'misc': {}, 'chests': {}, 'orbs': {}, 'settings': dict(self.st), 'hero_level': self.H}
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
        for k, mc, cls_, tag, drop_ in self.scan():
            if cls_ not in CLASSES or SKIP_KEY.search(k):
                continue
            tag = tag.strip()
            if not tag:
                continue
            en = self.text(tag, 'en').lower()
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
            f['en'] = tag_en.get(t, '')
            f['sid'] = re.sub(r'[^a-z0-9]+', '', t)[:40]
            f['rep'] = max(f['keys'], key=lambda k: self.rep_score(k))
            out.append(f)
        return out

    def scan(self):
        """[(key, classification, Class, name tag, dropItems)] of every Boss / Hero creature record (Builder's
        boss_monsters uses them too); reading a few fields of 15k monster records takes seconds, so the result is kept
        per base database + tweaks in <data>\\cache"""
        if getattr(self, '_rows', None) is not None:
            return self._rows
        R = self.R
        import tweaks
        base = getattr(self.b, 'base_arz', '') or ''
        try:
            st_ = os.stat(base)
            tag_ = '%d_%d_%s' % (st_.st_size, int(st_.st_mtime), hashlib.md5(
                (tweaks.fingerprint() + 'scan v2').encode('utf-8')).hexdigest()[:10])
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
        rows = []
        for k in sorted(R):
            if 'creature' not in k:      # every one: boss_monsters needs the sandbox records too
                continue
            if few is not None:          # a few fields of each record, not all ~600
                F = few(k, ('monsterClassification', 'Class', 'description', 'dropItems'))
            else:
                F = fields(self.peek(k))
            one = lambda f, d='': (F.get(f.lower()) or [d])[0]
            mc = one('monsterClassification') or ''
            if mc in ('Boss', 'Hero'):
                rows.append([k, mc, one('Class') or '', one('description') or '', one('dropItems', 1)])
        if cache:
            try:
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                for old in glob.glob(os.path.join(os.path.dirname(cache), 'souls_scan_*.json')):
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
        return '5_jadeemperor' if any(f['en'].startswith(c) for c in CHINA_EN) else '6_thebes'

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
        # spawn (Typhon of Act III and of the Underworld)
        mult = collections.Counter((k.rsplit(BS, 1)[0], tuple(self.levels(self.fd(k)))) for k in src)
        k_fight = max(mult.values()) if mult else 1
        per = lambda c: 100.0 * (1 - (1 - c / 100.0) ** (1.0 / k_fight)) if c > 0 else 0.0
        p, p0 = per(pct), per(pct0)
        misc = [(k, self.misc_room(self.rec(k), p0)) for k in src]
        misc = [(k, room) for k, room in misc if room]
        chests = []
        also = next((re.compile(c) for e, c in ARENA_CHEST_EN if f['en'].startswith(e)), None)
        if also is not None:          # 1.6.3: fought where loot on the ground vanishes - the reward orb as well
            chests = sorted(k for k in self.chests() if also.search(k.split(BS)[-1]))
        elif not misc and f['kind'] == 'boss':
            rx = next((re.compile(c) for e, c in CHEST_EN if f['en'].startswith(e)), None)
            if rx:
                chests = sorted(k for k in self.chests() if rx.search(k.split(BS)[-1]))
        orb = self.region(f) if f['kind'] == 'boss' else None
        return {'p': p, 'k_fight': k_fight, 'misc': misc, 'chests': chests, 'orb': orb}

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
        n = collections.Counter(f['kind'] for f in live)
        log('  souls: %d bosses, %d hero monsters (hero level %s), %d not built%s' % (
            n['boss'], n['hero'], self.H or 'unknown - their own', len(self.report) - len(live),
            '' if self.st['souls'] else ' - Souls=0: built, but they drop nowhere'))
        # orb tables per region
        if self.st['soulorbchance'] > 0 and self.dropping('boss'):
            by = collections.defaultdict(list)
            for f in live:
                if f['plan']['orb']:
                    by[f['plan']['orb']].append(f['relic'])
            for reg, relics in sorted(by.items()):
                t = self.table(self.ns + 'orb_%s.dbr' % reg, relics, 'souls of the %s electrum orbs' % reg)
                self.orb_entries[reg] = (t['name'], self.st['soulorbchance'])
                self.ledger['orbs'][reg] = {'table': key_of(t['name']), 'relics': sorted(key_of(x) for x in relics),
                                            'pct': self.st['soulorbchance']}

    def full(self, f, lg):
        t = self.text(f['tag'], lg) or self.text(f['tag'], 'en') or f['sid']
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
            notes.append('engine class %s -> Pet: NOT TESTED in game' % cls)
        setv(pet, 'templateName', 'database' + BS + 'Templates' + BS + 'Pet.tpl')
        setv(pet, 'Class', 'Pet')
        gone = {x.lower() for x in DROP_FIELDS}
        pet['vars'] = [t for t in pet['vars'] if t[0].lower() not in gone and
                       not re.match(r'^(chanceToEquip|loot)(Misc\d|Finger\d)', t[0])]
        setv(pet, 'dropItems', 0, 3)
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
            setv(pet, 'characterSpellCastSpeed', [max(CAST_LINE, x) for x in casts], 1)
            notes.append('cast speed %s -> %s' % ([round(x, 2) for x in casts], [max(CAST_LINE, round(x, 2)) for x in casts]))
        fixes = anim_fixes(pet)
        for spname, old, new, what in fixes:
            setv(pet, spname, math.ceil(new * 1000) / 1000.0, 1)    # up: rounding must not undo it
        if fixes:
            notes.append('faster: ' + '; '.join(sorted({w for _, _, _, w in fixes})))
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
            setv(relic, q, 1 if q == 'amulet' else 0, 3)      # BOOL: Game.dll reads these with the bool getter
        setv(relic, 'levelRequirement', 1, 0)
        setv(relic, 'itemCost', [8000, 8000, 8000] if kind == 'boss' else [4000, 4000, 4000], 0)
        what_ru = 'босса' if kind == 'boss' else 'героя'
        setv(relic, 'description', b.tag('tagTQSoul_%s_relic' % sid, 'Порабощённая душа: %s' % name_ru,
                                         'Enslaved Soul: %s' % name_en))
        setv(relic, 'itemText', b.tag('tagTQSoul_%s_relictext' % sid,
             'Частица порабощённой души %s: %s. Собери %d и вложи в амулет — и душа будет сражаться за тебя, '
             'становясь сильнее вместе с тобой.' % (what_ru, self.full(f, 'ru'), shards),
             'A shard of the enslaved soul of %s. Join %d and set them into an amulet - the soul will fight for you '
             'and grow with you.' % (self.full(f, 'en'), shards)))
        setv(relic, 'FileDescription', 'TQ Together soul relic: %s' % sid)
        shard_t = self.table(self.ns + '%s_soulshard.dbr' % sid, [relic['name']], 'one shard of soul %s' % sid)
        f['relic'], f['shard_table'] = relic['name'], shard_t['name']
        self.ledger['souls'][sid] = {'kind': kind, 'en': f['en'], 'rep': f['rep'], 'pet': key_of(pet['name']),
                                     'call': key_of(call['name']), 'relic': key_of(relic['name']),
                                     'shard_table': key_of(shard_t['name']), 'shards': shards, 'sources': [],
                                     'orb': f['plan']['orb'], 'life': getv(pet, 'characterLife'),
                                     'level': target, 'notes': notes}
        self.report.append((f, pet, notes))

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
                room = self.misc_room(r, pl['p'])       # re-checked: the eidolon shard may have taken the free slot
                if room is None:
                    continue
                self.add_misc(r, room[1], s['shard_table'], pl['p'])
                self.ledger['misc'].setdefault(k, {})[s['shard_table']] = pl['p']
                s['sources'].append('kill %s %.1f%% (%s slot %d)' % (k.split(BS)[-1], pl['p'], room[0], room[1]))
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
        log('  souls drop from %d monster records, %d boss chests, electrum orbs of %d regions' % (
            n_misc, len(by_chest), len(self.ledger['orbs'])))
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
            if it:
                names[tuple(key_of(x) for x in it)] = (j, getv(r, 'lootMisc%dItem%d' % (n, j)))
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

    def add_chest(self, ck, entries):
        """the chest's loot tables are shared with other chests: our own copy per chest, every soul shard added with
        its % per opening (Builder.add_shards: vanilla entries keep their odds)"""
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
                                     'souls': {key_of(t): pct for t, pct in entries}}

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
    return json.dumps({'souls': settings(), 'level': B.HERO_LEVEL}, sort_keys=True)


# ---------------------------------------------------------------------- self-check
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
            if re.search(r'proxy|treasure|OnDeath', vn, re.I) and any(isinstance(x, str) and x for x in v):
                bad.append('soul %s: %s=%s would be put down on death' % (sid, vn, v[0]))
        left = anim_fixes(pet)
        if min(float(x or 0) for x in (getv(pet, 'characterSpellCastSpeed') or [1.0])) < CAST_LINE - 1e-3:
            left = left + [('', 0, 0, 'cast speed %s' % getv(pet, 'characterSpellCastSpeed'))]
        if left:
            bad.append('soul %s: still slow - %s' % (sid, '; '.join(w for _, _, _, w in left[:3])))
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
                if get1(rel, q) != (1 if q == 'amulet' else 0) or t != 3:
                    bad.append('soul %s: fit flag %s=%s type %s (amulet only, bool)' % (sid, q, get1(rel, q), t))
                    break
        if call is not None and (getv(call, 'spawnObjectsTimeToLive') or get1(call, 'petLimit') != 1):
            bad.append('soul %s: summon TTL / petLimit' % sid)
        if not s['sources'] and st['souls'] and (s['kind'] == 'boss' or st['soulheroes']) and \
                all(st[k] == v for k, v in DEFAULTS if k.startswith('soul') and 'chance' in k):
            bad.append('soul %s: built but drops nowhere' % sid)
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
                targets = frozenset(key_of(x) for x in getv(R[soul_t], 'lootName1') or [])
                e = orb_odds.per_container(R, t_new, targets)
                if abs(e - pct / 100.0) > 5e-3:
                    bad.append('chest %s: soul %.4f per opening, want %.4f' % (ck.split(BS)[-1], e, pct / 100.0))
            # against the table as the build has it (a tweak may have changed it before us: Tartarus' loot)
            nf, of = orb_odds.fields(R[t_new]), orb_odds.fields(R[t_old] if t_old in R else baseR[t_old])
            for s_ in range(1, 7):
                chn, cho = float((nf.get('loot%dChance' % s_) or [0])[0]), float((of.get('loot%dChance' % s_) or [0])[0])
                Wn = sum(float((nf.get('loot%dWeight%d' % (s_, j)) or [0])[0]) for j in range(1, 40))
                Wo = sum(float((of.get('loot%dWeight%d' % (s_, j)) or [0])[0]) for j in range(1, 40))
                for j in range(1, 40):
                    x = (of.get('loot%dName%d' % (s_, j)) or [''])[0]
                    if not x:
                        continue
                    pn = chn * float((nf.get('loot%dWeight%d' % (s_, j)) or [0])[0]) / Wn if Wn else 0
                    po = cho * float((of.get('loot%dWeight%d' % (s_, j)) or [0])[0]) / Wo if Wo else 0
                    if abs(pn - po) > 1e-6:
                        bad.append('chest %s slot %d: vanilla %s odds changed' % (ck.split(BS)[-1], s_, x.split(BS)[-1]))
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
        if not n:
            bad.append('orbs of region %s not found' % reg)
    nb = sum(1 for s in ledger['souls'].values() if s['kind'] == 'boss')
    log('souls: %d bosses + %d hero monsters as amulet souls, %d monster records, %d chests, %d orb regions checked' % (
        nb, len(ledger['souls']) - nb, len(ledger['misc']), len(ledger['chests']), len(ledger['orbs'])))
    return bad
