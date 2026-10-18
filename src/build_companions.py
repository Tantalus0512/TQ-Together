# -*- coding: utf-8 -*-
"""Companions: your OTHER saved characters as permanent summoned allies (TQ AE), 18.09.2026.

  py -3 build_companions.py            build from the CURRENT saves -> build\\database.arz
  py -3 build_companions.py --install  build + install (game must be closed)
  start_tq.bat                         rebuild from fresh saves, install, launch the game

What it does: every saved character (level >= 20, a mastery chosen) becomes a companion that another character
can summon - with its level, attributes, skills (AI-wired by skill class) and worn gear, rebuilt from the save
on every launch, so levelling that character levels the companion too.
  - gear (1.0.3): the pet wears personal copies of the worn item records with everything else on the gear baked in -
    affixes (Epic/Legendary too), relics and charms at their shard count, completion bonuses, and the amulet and
    the artifact (a creature has no slot for them); verify_companions 7i checks every attribute sum
  - the companion is a Class Pet record (pet panel: health/mana, stance, dismiss) on the player's body
  - "Eidolon: <name>": a 2-shard relic that fits rings only (two rings = at most two companions); completing it
    rolls the completion bonus (an affix) that grants "Summon Companion: <name>" - like vanilla relic bonuses
    that grant Wraith Lord etc. Drops from electrum orbs of every difficulty (ORB_CHANCE % per orb, 1.5.0) and from
    the bosses themselves (BOSS_CHANCE % per kill, 1.5.1), vanilla odds kept
  - deleted characters leave inert "faded" records (registry.json) so items holding their relic stay valid;
    once nothing anywhere refers to them (saves, stashes, TQVault, backups: scan_roots) they are dropped
Checks: verify_companions.py (run by --install; ALL CHECKS PASSED or nothing is installed).
"""
import os, sys, re, struct, glob, hashlib, collections, json

sys.path.insert(0, r'D:\TQMod\tools')
from tqlib import DB, get1, getv, setv, delv, key_of, BS, write_text_file, load_game_text
from arz_lazy import LazyArz
import paths
from chr_reader import read_char
import orb_odds

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(paths.data_dir(), 'build') if paths.frozen() else os.path.join(HERE, 'build')
NS = ('records' + BS + 'tqmod' + BS + 'companions' + BS).lower()
SAVES = paths.saves_dir()
MIN_LEVEL = 20
MAX_SKILLS = 33   # Game.dll loads skillName1..33 (audit 18.09); vanilla creatures use <= 17, so 18+ carry only passives
PET_SRC = 'records\\xpack2\\skills\\item skills\\pet\\doppelgangerpet.dbr'
SUMMON_SRC = 'records\\xpack2\\skills\\item skills\\summon_doppel.dbr'
RING_SRC = 'records\\item\\equipmentring\\c01_ring01.dbr'
PC ={'male': 'records\\xpack\\creatures\\pc\\malepc01.dbr', 'female': 'records\\xpack\\creatures\\pc\\femalepc01.dbr'}
SLOT_BY_CLASS = [   # item Class -> monster loot slot(s)
    (r'^ArmorProtective_Head', ['Head']), (r'^ArmorProtective_UpperBody', ['Torso']),
    (r'^ArmorProtective_LowerBody', ['LowerBody']), (r'^ArmorProtective_Forearm', ['Forearm']),
    (r'^ArmorJewelry_Ring', ['Finger1', 'Finger2']),
    (r'^WeaponHunting_Bow|^WeaponMagical_Staff|^WeaponArmor_Shield', ['LeftHand']),
    (r'^Weapon', ['RightHand', 'LeftHand']),
]
GEAR_SLOTS = ['Torso', 'Head', 'LowerBody', 'Forearm', 'Finger1', 'Finger2', 'RightHand', 'LeftHand']  # merge order
# Gear baking (1.0.3). A monster wears bare item records, so everything else on the hero's gear is baked into personal
# copies of the worn records: affixes (Epic/Legendary too), relics and charms at their shard count, completion bonuses,
# and the amulet and the artifact, which a creature has no slot for. Only attribute fields move (the same names the
# engine reads from affix tables); visuals, requirements and prices stay the worn item's own.
STAT_FIELD = re.compile(r'^(character|defensive|offensive|retaliation|skill|augment|itemSkill|racialBonus|petBonus|'
                        r'shieldBlock)')
NOT_STAT = re.compile(r'^(characterBaseAttackSpeed(Tag)?|characterAttackSpeed|characterRunSpeed|characterSpellCastSpeed)$'
                      r'|Requirement$|ReqReduction$')
# field = <attribute><role>; roles that describe HOW an attribute applies must match before two can be summed
ROLES = ('DurationMin', 'DurationMax', 'DrainMin', 'DrainMax', 'DamageRatio', 'Chance', 'Global', 'XOR', 'Min', 'Max')
SHAPE_ROLES = ('DurationMin', 'DurationMax', 'DamageRatio', 'Chance', 'Global', 'XOR')
GLOBAL_CHANCE = {'offensive': 'offensiveGlobalChance', 'retaliation': 'retaliationGlobalChance'}
# a weapon's own base damage / a shield's block: bonuses must not melt into them
WEAPON_BASE = re.compile(r'^(offensivephysical|offensivebase\w+|offensivepierceratio|defensiveblock)$')
AUGMENT = re.compile(r'^augment(Skill|Mastery)(Name|Level)(\d)$')
AUGMENT_SLOTS = (1, 2)      # vanilla items use augment{Skill,Mastery}Name1..2 only
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
    # blink: 0.5 s timeout let the AI throw knives before Phantom Strike landed (owner 24.09) - 3 s to finish it
    'Skill_AttackSpellTeleportSelf': ('LongRange', 5, 11, 0), 'Skill_AttackWeaponBlink': ('AnyRange', 99, 10, 3.0),
    'Skill_BuffSelfImmobilize': ('ShortRange', 20, 10, 0), 'Skill_AttackInherent': ('ShortRange', 40, 5, 1),
    'Skill_AttackWeaponRangedSpread': ('AnyRange', 34, 2, 1),
}
SPECIAL_DEFAULT = ('AnyRange', 40, 6, 1)
NO_COOLDOWN_DELAY = 8.0     # s between uses of an AI attack whose skill has no cooldown (owner 24.09)
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
ORB_CHANCE = 40.0      # 1.5.0: % per electrum orb (one opening) to give one eidolon shard of a random companion
                       # (2 shards = 1 eidolon); TQTogether.ini EidolonOrbChance. Up to 1.4.0 '10' was per ITEM of
                       # an orb, ~38 % per Legendary orb in fact - the default keeps that.
ORB_TIERS = ('_1n_', '_2e_', '_3l_')   # 1.5.0: Normal, Epic and Legendary orbs (x4_ElectrumOrb_*_<tier>_Loot)
BOSS_CHANCE = 20.0     # 1.5.1: % per boss kill, dropped by the boss itself; TQTogether.ini EidolonBossChance
                       # (1.5.0 put 10 % into the boss chests instead)
AGGR_CONTROLLER = dict(FAST_CONTROLLER, MaxPursuitDistance=32.0, TeleportToLeaderDistance=30.0, WanderDistance=7.0)
# 1.1.9: Eylin's companion spent Regrowth on herself and it was on cooldown when the hero needed it: heal the leader
# (the hero) early, the others at 70 %, with the satyr shaman's 1 s heal delay (vanilla heal-casters, 148 monsters)
HEAL_CONTROLLER = {'healLeaderHealthPercentage': 85, 'healAllyHealthPercentage': 80}
HEAL_DELAY = 1.0
# 1.3.5: a healer heals an ally ONLY on its call for help (ControllerMonsterState::HealAllyWhenAttacked 0x10047c90 from
# AllyAttacked; Character::DoDistressCall 0x100e9dc0 reaches non-foes within distressCallRange). The hero always calls
# (Player::ShouldUseDistressCall 0x10207290 = true); a creature only while maxDistressCalls lasts - read ONCE at load and
# never refilled (Character::UnderAttack 0x100dcc86) - and distressCallTime ms apart. The doppel's 4 calls / 10 s / 10 m
# left Eylin blind to Temun (owner 25.09). Other companions also answer the call (ChanceToRespondToDistressCall).
DISTRESS = (('distressCall', 3, 1), ('distressCallRange', 1, 20.0), ('distressCallTime', 0, 2000),
            ('maxDistressCalls', 0, 1000000))
GAP_SRC = 'records\\xpack\\game\\gameengine.dbr'   # monsterLevelGapFixer: level the game adds per difficulty
PET_PANEL_SRC = 'records\\xpack2\\quests\\npc\\non speaking\\side\\x2sq23_ylva_companion.dbr'  # humanoid pet icon
PET_RANGE_SRC = 'records\\xpack3\\skills\\item skills\\pet\\pet_atl_lobster.dbr'        # ring-summoned permanent pet
RELIC_LOOK_SRC = 'records\\xpack\\item\\relics\\01_act4_shadeofhektor.dbr'              # «Сущность духа Гектора»
SUMMON_FX_SRC = 'records\\skills\\spirit\\wraithlordsummons.dbr'
# base speeds come from the hero's own body record (1.0.4): the doppel's 1.2 attack / 1.5 run made the companion strike
# 1.6x faster than the hero with the same gear; 1.0.5: cast speed too (the doppel's 1.5 cast at half the hero's 2.8)
BASE_SPEEDS = ('characterAttackSpeed', 'characterRunSpeed', 'characterSpellCastSpeed')
# the engine caps a HERO's speed (gameengine playerXSpeedCapMax, %) but a creature only at 400-500 %, so the companion
# is held to the hero's caps here: static gear+passive bonuses are trimmed, and a speed buff from an item gets a personal
# copy whose speed stops at the cap - on the hero the rest is cut by the engine, the buff's other effects stay (1.0.5:
# Artemis' Battle Dance keeps its dodge, its +80 % run is cut to what is left under the hero's +66 %)
SPEED_KINDS = {'Attack': 'playerAttackSpeedCapMax', 'SpellCast': 'playerSpellCastSpeedCapMax', 'Run': 'playerRunSpeedCapMax'}
# 1.1.3: the hero's avoidance caps (absolute %) apply to the companion too - a creature has none
DODGE_KINDS = {'Dodge': ('characterDodgePercent', 'playerDodgePercentCap'),
               'Deflect': ('characterDeflectProjectile', 'playerDodgeProjectilePercentCap')}
DODGE_FIELD = {f: k for k, (f, c) in DODGE_KINDS.items()}
# 1.1.3: resistances - a hero gets the difficulty penalty (playergamebalanceattributes: -40 Epic, -100 Legendary) and
# the cap gameengine playerDefenseCap; a creature neither, so the companion stood at 130-173 % and took no damage
RESISTS = ('defensiveFire', 'defensiveCold', 'defensiveLightning', 'defensivePoison', 'defensivePierce', 'defensiveLife',
           'defensiveBleeding', 'defensivePhysical')
ELEMENTAL = ('defensiveFire', 'defensiveCold', 'defensiveLightning')      # defensiveElementalResistance adds to each
PLAYER_PAK = 'records\\game\\playergamebalanceattributes.dbr'
SPEED_CHILD = re.compile(r'^(buffSkillName|skillCastName)$')


def enemy_debuff(r):
    """1.3.2: a buff the game puts on ENEMIES (Deathchill aura, Plague's Fatigue ...): its negative speed slows them,
    not the caster (debufSkill flag, SkillBuff_Debuf* / SkillBuff_Contageous classes)"""
    cls = (get1(r, 'Class', '') or '').lower()
    return bool(float(get1(r, 'debufSkill', 0) or 0)) or cls.startswith('skillbuff_debuf') or cls == 'skillbuff_contageous'
# 1.0.6 parity with the hero (Game.dll audit 24.09):
# - a Pet adds petgamebalanceattributes (attack speed -10/0/+10 %, run +14/+20/+26 % by difficulty) that a hero does not
#   get: cancelled by the companion's own passive, one skill level per difficulty (skillLevel [1,2,3])
# - Character::GetAttackSpeed = (body + weapon base) x (1 + mods); the cap is Max% x BODY only, 350 for a hero, 400 for
#   a creature: the body is scaled by 350/400 and the difference moved onto the weapon base -> same swing, same cap
# - the AI casts at most 5 attacks (literal field names in Game.dll); further attacks are cast from the companion's gear
#   by an item auto-cast controller (SkillAutoCastController 'AttackEnemy'), classes with vanilla item precedent only
AUTOCAST_CLASSES = {'Skill_AttackRadius', 'Skill_AttackProjectileFan', 'Skill_AttackWave', 'Skill_AttackBuffRadius',
                    'Skill_AttackProjectileAreaEffect', 'Skill_DropProjectileTelekinesis', 'Skill_AttackProjectileRing',
                    'Skill_AttackSpellChaos', 'Skill_AttackChain', 'Skill_AttackProjectileBurst', 'Skill_AttackBuff',
                    'Skill_DispelMagic', 'Skill_AttackProjectile', 'Skill_AttackRadiusLightning'}
# 1.1.7 item auto-cast -> creature skills (convert_autocast); sources = vanilla records of that class that pets use
ONHIT_BUFF_SRC = 'records\\xpack\\skills\\dream\\distortionfield.dbr'                     # Skill_PassiveOnHitBuffSelf
ONHIT_AOE_SRC = 'records\\skills\\storm\\stormsurge.dbr'                                  # Skill_OnHitAttackRadius
LOWLIFE_SRC = 'records\\skills\\nature\\wolf_petskill_survivalinstinct.dbr'              # Skill_PassiveOnLifeBuffSelf
PROC_STRIP = re.compile(r'^(character|defensive|offensive|retaliation|racialBonus|petBonus|augment|damageAbsorption)|'
                        r'^(charFxPakSelfNames|'
                        r'targetFxPakName|radiusEffectName|skillActivatedSound|skillDeactivatedSound|skillHitSound|'
                        r'skillActivatedAuraName|'      # wolf Survival Instinct: points at a record missing in vanilla
                        r'skillCastAuraName|skillManaCost|skillActiveManaCost|buffSkillName|skillLifeBonus|skillManaBonus|'
                        r'skillBonusEffectName|onHitActivationChance)$')
PROC_BUFF_FIELDS = r'^(character|defensive|offensive|retaliation|damageAbsorption)'
PROC_FX = ('charFxPakSelfNames', 'skillActivatedSound', 'skillHitSound')
PASSIVE_SRC = 'records\\quests\\rewards\\jg10 - chirons reward legendary.dbr'   # a plain Skill_Passive, all weapon flags
# 1.0.9 party burden (TQTogether.ini PartyBurden=<%>, default 0 = off): every companion carries a toggled aura that
# lowers the whole party's total damage by that %, one aura per companion (records per cid, so two companions stack) -
# with companions the enemies last longer, alone the game stays vanilla (the engine cannot scale monsters by pets)
BURDEN_TOGGLE_SRC = 'records\\skills\\nature\\heartofoak.dbr'          # a plain ally aura: toggle + SkillBuff_Passive
BURDEN_BUFF_SRC = 'records\\skills\\nature\\heartofoakbuff.dbr'
BURDEN_RADIUS = 30.0


HERO_LIFE = 1.0   # 1.1.0: set by tq_together.choose_hero - Legendary monster/boss life x this (vanilla solo = 1)
HERO_BOSS = 1.0   # 1.1.3: bosses x this on top (TQTogether.ini AutoLifeBoss) - Nessus fell like a trash mob
HERO_DAMAGE = 1.0  # 1.1.5: Legendary monster damage modifiers and offensive ability x this (= life ^ AutoDamagePower)
HERO_NAME = ''     # 1.2.0: the hero about to be played (choose_hero): his pet bonuses are cancelled on the companions
PARTY_EXTRA = 0.0  # 1.4.0: extra players the summoned companions count as (choose_hero, TQTogether.ini Difficulty=party)
HERO_LEVEL = 0     # 1.6.0: level of the hero about to be played (choose_hero) - boss souls come at this level
HERO_DPS = 0.0     # 1.7.0: his character-window damage per second (choose_hero) - boss souls hit SoulDamage % of it


def party_burden():
    try:
        return max(0, min(90, int(float(paths.settings().get('partyburden', '0') or 0))))
    except ValueError:
        return 0


def drop_chances():
    """1.5.0: (% per electrum orb, % per boss chest) - TQTogether.ini EidolonOrbChance / EidolonBossChance, 0 = none"""
    st = paths.settings()
    out = []
    for k, d in (('eidolonorbchance', ORB_CHANCE), ('eidolonbosschance', BOSS_CHANCE)):
        try:
            out.append(min(95.0, max(0.0, float((st.get(k) or str(d)).replace(',', '.')))))
        except ValueError:
            out.append(d)
    return tuple(out)


def boss_monsters(R, rows=None):
    """[(key, record)] of every monster classified Boss that drops loot itself (dropItems not 0). rows: the souls'
    scan of Boss/Hero records [(key, classification, Class, tag, dropItems)] - the same answer without reading
    10k monster records again"""
    if rows is not None:
        return [(k, R[k]) for k, mc, cls, tag, drop in rows
                if mc == 'Boss' and str(drop) not in ('0', 'False') and k in R]
    out = []
    few = getattr(R, 'fields', None)      # 1.6.0: two fields per record, nothing cached (the save re-encodes the cache)
    for k in sorted(R):
        if 'creature' not in k:
            continue
        if few is not None:
            F = few(k, ('monsterClassification', 'dropItems'))
            mc, drop = (F.get('monsterclassification') or [''])[0], (F.get('dropitems') or [1])[0]
        else:
            mc, drop = get1(R[k], 'monsterClassification', ''), get1(R[k], 'dropItems', 1)
        if (mc or '') != 'Boss' or str(drop) in ('0', 'False'):
            continue
        out.append((k, R[k]))
    return out


def free_misc_slot(r):
    """the first Misc loot slot (1..3) a monster leaves empty: no item and no chance -> its number, else None"""
    for n in (1, 2, 3):
        if float(get1(r, 'chanceToEquipMisc%d' % n, 0) or 0):
            continue
        if any(x for j in range(1, 7) for x in (getv(r, 'lootMisc%dItem%d' % (n, j)) or [])):
            continue
        return n
    return None
# how many vanilla creatures start a chainInitialSkill from a special attack of this class (survey 24.09)
CHAIN_PRECEDENT = {'Skill_AttackSpell': 33, 'Skill_SpawnPetMonster': 21, 'Skill_BuffSelfToggled': 18,
                   'Skill_BuffSelfDuration': 15, 'Skill_AttackSpellTeleportSelf': 13, 'Skill_AttackProjectileAreaEffect': 11,
                   'Skill_AttackProjectileSpawnPet': 6, 'Skill_AttackWeaponRangedSpread': 4, 'Skill_SpawnPet': 3,
                   'Skill_BuffOther': 3, 'Skill_AttackProjectileRing': 3, 'Skill_AttackRadius': 3, 'Skill_AttackWave': 3,
                   'Skill_AttackWeaponCharge': 2, 'Skill_AttackProjectile': 2, 'Skill_AttackWeaponBlink': 2,
                   'Skill_AttackChain': 1, 'Skill_AttackProjectileBurst': 1, 'Skill_DefensiveGround': 1}
REGISTRY = os.path.join(paths.data_dir(), 'registry.json')   # every companion ever built: cid -> name
# inert record that is ALWAYS built: the installer recognises its own database by records under NS, and with no
# companion and no tombstone left there would be none (installed db taken for a game update, 1.0.1 lifecycle test)
MARKER = NS + 'tqtogether_marker.dbr'
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


EQUIP_STR = {'baseName': 'base', 'prefixName': 'prefix', 'suffixName': 'suffix', 'relicName': 'relic',
             'relicBonus': 'relic_bonus', 'relicName2': 'relic2', 'relicBonus2': 'relic_bonus2'}
EQUIP_INT = {'var1': 'shards', 'var2': 'shards2'}


def parse_equipment(path):
    """Exact equipped items: the stream after 'equipmentCtrlIOStreamVersion' lists slots in order
    (head, amulet, torso, legs, forearm, ring, ring, weapon set 0 R/L, weapon set 1 R/L, artifact);
    after every item comes 'itemAttached' - 1 = worn now (the inactive weapon set has 0).
    Every key is int32 length + ascii; a string value follows as int32 length + ascii (empty = length 0),
    var1/var2 (shards of relic 1/2) as int32."""
    raw = open(path, 'rb').read()
    i = raw.find(b'equipmentCtrlIOStreamVersion') - 4
    n = len(raw)
    items, cur = [], None
    while 0 <= i and i + 4 <= n:
        l = i32(raw, i)
        if 1 <= l <= 200 and i + 4 + l <= n and re.fullmatch(rb'[ -~]+', raw[i + 4:i + 4 + l]):
            tok = raw[i + 4:i + 4 + l].decode('latin1')
            j = i + 4 + l
            if tok in ('storedType', 'skillName'):          # the hot-bar section starts: equipment is over
                break
            if tok in EQUIP_STR and j + 4 <= n:
                sl = i32(raw, j)
                if not 0 <= sl <= 400 or j + 4 + sl > n:
                    i = j
                    continue
                val = raw[j + 4:j + 4 + sl].decode('latin1')
                if tok == 'baseName':
                    cur = {'base': val, 'prefix': '', 'suffix': '', 'relic': '', 'relic_bonus': '', 'shards': 0,
                           'relic2': '', 'relic_bonus2': '', 'shards2': 0, 'attached': False}
                elif cur is not None:
                    cur[EQUIP_STR[tok]] = val
                i = j + 4 + sl
                continue
            if (tok in EQUIP_INT or tok == 'itemAttached') and j + 4 <= n:
                val = i32(raw, j)
                if tok == 'itemAttached':
                    if cur is not None and cur['base']:
                        cur['attached'] = val == 1
                        items.append(cur)
                    cur = None
                elif cur is not None:
                    cur[EQUIP_INT[tok]] = val
                i = j + 4
                continue
            i = j
            continue
        i += 1
    return [it for it in items if it['attached']]


def greatest_damage(path):
    """the hero's biggest single hit so far (statistics 'greatestDamageInflicted', a float right after the key); 0 if
    the save has none yet"""
    raw = open(path, 'rb').read()
    key = b'greatestDamageInflicted'
    i = raw.find(key)
    while i >= 4:
        if i32(raw, i - 4) == len(key) and i + len(key) + 4 <= len(raw):
            v = struct.unpack_from('<f', raw, i + len(key))[0]
            return v if v == v and 0 <= v < 1e9 else 0.0
        i = raw.find(key, i + 1)
    return 0.0


def split_role(field):
    """'offensiveSlowFireDurationMin' -> ('offensiveSlowFire', 'DurationMin'); a bare attribute -> (field, '')"""
    for r in ROLES:
        if field.endswith(r) and len(field) > len(r):
            return field[:-len(r)], r
    return field, ''


def stat_fields(rec, idx=0):
    """{field: (type, value)}: the attributes a record gives; per-shard arrays (relics, charms) read at idx"""
    out = {}
    for vn, vt, vals in rec['vars']:
        if not vals or not STAT_FIELD.match(vn) or NOT_STAT.search(vn):
            continue
        if vn == 'racialBonusRace':                     # a LIST of races, all of them count
            races = tuple(sorted(set(x for x in vals if x)))
            if races:
                out[vn] = (vt, races)
            continue
        v = vals[min(max(idx, 0), len(vals) - 1)]
        if v not in (0, 0.0, ''):
            out[vn] = (vt, v)
    return out


def stat_units(fields):
    """split a record's attributes into units that must move together:
    ('g', attribute) one attribute with its roles; ('global', family) all attributes of a 'one of these, X% chance'
    block plus its chance; ('skill',) the granted skill; ('aug', Skill|Mastery, n); ('race',); ('pet',)"""
    units = collections.OrderedDict()
    flagged = collections.defaultdict(set)              # family -> attributes marked Global
    for f, (vt, v) in fields.items():
        attr, role = split_role(f)
        if role == 'Global' and f.startswith(tuple(GLOBAL_CHANCE)):
            flagged['offensive' if f.startswith('offensive') else 'retaliation'].add(attr.lower())
    for f, (vt, v) in sorted(fields.items()):
        attr, role = split_role(f)
        m = AUGMENT.match(f)
        if f.startswith('itemSkill'):
            u = ('skill',)
        elif m:
            u = ('aug', m.group(1), int(m.group(3)))
        elif f.startswith('racialBonus'):
            u = ('race',)
        elif f == 'petBonusName':
            u = ('pet',)
        elif f in GLOBAL_CHANCE.values():
            u = ('global', 'offensive' if f.startswith('offensive') else 'retaliation')
        else:
            fam = 'offensive' if f.startswith('offensive') else 'retaliation' if f.startswith('retaliation') else ''
            u = ('global', fam) if fam and attr.lower() in flagged[fam] else ('g', attr.lower())
        units.setdefault(u, {})[f] = (vt, v)
    return units


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
        self.base_arz = base_arz
        self.db = DB(LazyArz.load(base_arz))   # lazy: ~100 MB instead of several GB
        self.R = self.db.arz.records
        self.vt = {'ru': load_game_text('ru'), 'en': load_game_text('en')}
        self.text = {'ru': [], 'en': []}
        self.report = []
        self.cids = set()
        self.registry, self.folders = load_registry()
        self.known = set(self.registry)
        self.gear_ledger = {}      # pet record -> what its gear was baked from (verify_companions 7i)
        self.soul_ledger = None    # 1.6.0: boss souls built and where they drop (souls.check)
        self.hero_run = {}         # 1.7.0: hero name -> run speed bonus % from gear and passives within the cap (souls)
        self.hero_speed = {}       # 1.7.5: hero name -> {'Attack'|'SpellCast'|'Run': bonus %} the same way (souls)

    def tag(self, name, ru, en):
        self.text['ru'].append((name, ru)); self.text['en'].append((name, en))
        return name

    def clone(self, src, dst):
        return self.db.clone(src, dst.lower())

    # ------------------------------------------------------------ gear
    def label(self, rec):
        """in-game name of an item, relic or affix for the report ('[fs]x[ms]y' gendered texts -> the masculine form)"""
        for f in ('itemNameTag', 'description', 'lootRandomizerName'):
            t = self.vt['ru'].get(get1(rec, f, '') or '')
            if t:
                forms = dict(re.findall(r'\[(\w\w)\]([^\[]*)', t))
                return (forms.get('ms') or next(iter(forms.values()), '') or t).strip() if forms else t
        return rec['name'].split(BS)[-1]

    def gear_sources(self, it):
        """[(label, record, shard index)] on one worn item besides its base: affixes, relics/charms at their shard
        count, completion bonuses (the relic record holds per-shard arrays, var1 = shards set in). Our own eidolons
        stay out: a companion does not summon companions."""
        out = []
        for what, f, shards, relic in (('prefix', 'prefix', None, None), ('suffix', 'suffix', None, None),
                                       ('relic', 'relic', 'shards', None), ('bonus', 'relic_bonus', None, 'relic'),
                                       ('relic', 'relic2', 'shards2', None), ('bonus', 'relic_bonus2', None, 'relic2')):
            name = it.get(f)
            r = self.R.get(key_of(name)) if name else None
            if r is None or key_of(r['name']).startswith(NS):
                continue
            idx = (int(it.get(shards) or 0) - 1) if shards else 0
            if shards and not 0 <= idx < 16:              # var1 is the shard count; nonsense = read the first step
                idx = 0
            owner = self.R.get(key_of(it.get(relic) or '')) if relic else None   # a bonus is named after its relic
            out.append(('%s «%s»' % (what, self.label(owner if owner is not None else r)), r, idx))
        return out

    @staticmethod
    def merge_unit(t, unit, key, weapon):
        """-> [(field, type, value)] that put unit into record t, or None if it does not fit there.
        An attribute t lacks is copied as is; one it has is summed only when both apply it the same way (same chance,
        duration, global flag...), otherwise the unit tries another item."""
        have = {vn: (vt, vals) for vn, vt, vals in t['vars'] if vals and any(x not in (0, 0.0, '') for x in vals)}
        kind = key[0]
        if kind == 'skill':
            return None if get1(t, 'itemSkillName', '') else [(f, vt, v) for f, (vt, v) in unit.items()]
        if kind == 'pet':
            return None if get1(t, 'petBonusName', '') else [(f, vt, v) for f, (vt, v) in unit.items()]
        if kind == 'aug':
            what = key[1]
            name = next((v for f, (vt, v) in unit.items() if 'Name' in f), '')
            lvl = next((v for f, (vt, v) in unit.items() if 'Level' in f), 0)
            for n in AUGMENT_SLOTS:                           # same skill already there: add the levels
                if key_of(get1(t, 'augment%sName%d' % (what, n), '') or '') == key_of(name):
                    return [('augment%sLevel%d' % (what, n), 0, int(get1(t, 'augment%sLevel%d' % (what, n), 0) or 0) + int(lvl))]
            for n in AUGMENT_SLOTS:
                if not get1(t, 'augment%sName%d' % (what, n), ''):
                    return [('augment%sName%d' % (what, n), 2, name), ('augment%sLevel%d' % (what, n), 0, int(lvl))]
            return None
        if kind == 'race':
            races = unit.get('racialBonusRace', (2, ()))[1]
            mine = tuple(sorted(set(x for x in (getv(t, 'racialBonusRace') or []) if x)))
            if not mine:
                return [(f, vt, list(v) if f == 'racialBonusRace' else v) for f, (vt, v) in unit.items()]
            if mine != races:
                return None
            return [(f, vt, float(get1(t, f, 0) or 0) + v) for f, (vt, v) in unit.items() if f != 'racialBonusRace']
        if kind == 'global':
            gc = GLOBAL_CHANCE[key[1]]
            attrs = {split_role(f)[0].lower() for f in unit if f != gc}
            if gc in have or any(split_role(f)[0].lower() in attrs for f in have):
                return None
            return [(f, vt, v) for f, (vt, v) in unit.items()]
        # one attribute with its roles
        attr = key[1]
        mine = {f: have[f] for f in have if STAT_FIELD.match(f) and split_role(f)[0].lower() == attr}
        if not mine:
            return [(f, vt, v) for f, (vt, v) in unit.items()]
        if weapon and WEAPON_BASE.match(attr):
            return None
        if any(len(vals) > 1 for vt, vals in mine.values()):
            return None
        roles = {split_role(f)[1] for f in list(mine) + list(unit)}
        cur = {split_role(f)[1]: (f, vt, vals[0]) for f, (vt, vals) in mine.items()}
        new = {split_role(f)[1]: (f, vt, v) for f, (vt, v) in unit.items()}
        for r in roles & set(SHAPE_ROLES):
            a, b = (cur[r][2] if r in cur else 0), (new[r][2] if r in new else 0)
            if abs(float(a) - float(b)) > 1e-6:
                return None
        out = []
        for r, (f, vt, v) in new.items():
            if r in SHAPE_ROLES:
                continue
            base_f, base_vt, base_v = cur.get(r, (f, vt, 0))
            out.append((base_f, base_vt, (base_v or 0) + v))
        return out

    def bake_gear(self, cid, pet, equipped):
        """the pet wears personal copies of the hero's worn records with everything else on the gear baked in; item
        auto-cast skills become the companion's own skills (procs); the attack-speed cap is made the hero's.
        -> (gear lines for the report, lines about what could not be transferred, ledger for the self-check)"""
        targets, homeless, used = collections.OrderedDict(), [], set()
        for it in equipped:
            base = self.R.get(key_of(it['base']))
            if base is None:
                homeless.append((it, None))
                continue
            cls = get1(base, 'Class', '') or ''
            slots = next((s for rx, s in SLOT_BY_CLASS if re.search(rx, cls)), None)
            slot = next((s for s in (slots or []) if s not in used), None)
            if slot is None:
                homeless.append((it, base))
                continue
            used.add(slot)
            targets[slot] = {'item': it, 'orig': base, 'rec': base, 'weapon': cls.startswith('Weapon'), 'added': []}
        order = [s for s in GEAR_SLOTS if s in targets]
        armour_first = [s for s in order if not targets[s]['weapon']] + [s for s in order if targets[s]['weapon']]
        lost, sources, skills, adjust = [], [], [], {}

        def own(s):
            t = targets[s]
            if t['rec'] is t['orig']:                          # first change: make the personal copy
                t['rec'] = self.clone(t['orig']['name'], NS + 'gear\\%s_%s.dbr' % (cid, s.lower()))
            return t['rec']

        def put(label, key, unit, rec, idx, prefer):
            for s in prefer + [x for x in armour_first if x not in prefer]:
                t = targets[s]
                ops = self.merge_unit(t['rec'], unit, key, t['weapon'])
                if ops is None:
                    continue
                for f, vt, v in ops:
                    setv(own(s), f, v, vt)
                if label not in t['added']:
                    t['added'].append(label)
                return
            lost.append((label, key, sorted(unit), rec['name'], idx))

        def place(label, rec, idx, prefer):
            sources.append((rec['name'], idx))
            for key, unit in stat_units(stat_fields(rec, idx)).items():
                if key == ('skill',):                          # granted skills wait for the speed check below
                    skills.append((label, key, unit, rec, idx, prefer))
                else:
                    put(label, key, unit, rec, idx, prefer)

        for s in order:
            t = targets[s]
            for label, rec, idx in self.gear_sources(t['item']):
                place(label, rec, idx, [s])
        for it, base in homeless:
            if base is None:
                lost.append(('«%s»' % it['base'].split(BS)[-1], ('missing record',), [], it['base'], 0))
                continue
            name = self.label(base)
            place('«%s»' % name, base, 0, [])
            for label, rec, idx in self.gear_sources(it):
                place('%s (%s)' % (label, name), rec, idx, [])
        # speed: the hero's caps. A speed buff from an item that would lift the companion past them is not given
        # (the worn item's own one included); then static gear + passive bonuses are trimmed down to the caps.
        budget = self.speed_budget()
        static = self.static_speed(pet, [targets[s]['rec'] for s in order])
        room = {k: max(0.0, budget[k] - static[k]) for k in list(SPEED_KINDS) + list(DODGE_KINDS)}
        self.last_speed = {k: min(static[k], budget[k]) for k in SPEED_KINDS}    # 1.7.0/1.7.5: the boss souls keep up
        self.last_run_bonus = self.last_speed['Run']
        trim = []

        def capped(sk, lv, label):
            """the item skill as the companion gets it: itself, or a personal copy whose speed stops at the hero cap.
            Buffs share the room left under the caps (the highest level counts: a buff's level may rise)"""
            bonus = self.speed_bonus(sk, 99, buffs_only=True)
            if not any(v > room[k] + 1e-6 for k, v in bonus.items()):
                for k, v in bonus.items():
                    room[k] = max(0.0, room[k] - v)
                return sk
            trim.append('%s: %s - its speed held to the hero cap' % (label, self.skill_label(sk)))
            return self.trim_speed(cid, sk, room)

        for s in order:
            t = targets[s]
            sk = get1(t['rec'], 'itemSkillName', '')
            if sk:
                new = capped(sk, int(get1(t['rec'], 'itemSkillLevel', 1) or 1), '%s «%s»' % (s, self.label(t['orig'])))
                if new != sk:
                    setv(own(s), 'itemSkillName', new)
        for label, key, unit, rec, idx, prefer in skills:
            sk = unit.get('itemSkillName', (2, ''))[1]
            new = capped(sk, int(unit.get('itemSkillLevel', (0, 1))[1] or 1), label) if sk else sk
            put(label, key, dict(unit, itemSkillName=(2, new)) if new != sk else unit, rec, idx, prefer)
        # 1.1.7: an item auto-cast never fires on a creature (Game.dll: Monster::Load equips the gear inside
        # Character::Load 0x101d9b21, before SetAsControllingManager 0x101da504 creates SkillServices, so AddItemSkill
        # skips AddAutoCastController at 0x102576ff - vanilla monsters too). Each such item skill becomes a skill of the
        # companion itself of a class the engine runs without controllers; the dead controller leaves the gear copy.
        procs = []
        for s in order:
            r = targets[s]['rec']
            sk, ctl = get1(r, 'itemSkillName', ''), get1(r, 'itemSkillAutoController', '')
            skr = self.R.get(key_of(sk)) if sk else None
            if skr is not None and any(float(get1(skr, f, 0) or 0) for f in ('offensiveTauntMin', 'offensiveTauntMax')):
                # 1.3.2: the no-taunt rule (owner 24.09) holds for item skills too (e.g. Batter granted by an item)
                for f in ('itemSkillName', 'itemSkillLevel', 'itemSkillAutoController'):
                    delv(own(s), f)
                trim.append('%s: %s - not transferred, taunt: enemies would chase the companion instead of you'
                            % (s, self.skill_label(sk)))
                continue
            if not (sk and ctl):
                continue
            conv = self.convert_autocast(cid, sk, int(get1(r, 'itemSkillLevel', 1) or 1), ctl)
            for f in ('itemSkillName', 'itemSkillLevel', 'itemSkillAutoController'):
                delv(own(s), f)
            if isinstance(conv, str):
                trim.append('%s: %s - not transferred, %s' % (s, self.skill_label(sk), conv))
            else:
                procs.append(conv)
                trim.append('%s: %s -> the companion\'s own %s' % (s, self.skill_label(sk), conv[3]))
        # the attack-speed cap: a hero's is 350 % of his BODY speed, a creature's 400 %; scale the body down by the
        # ratio and give the difference to the weapon(s) - body + weapon, i.e. the swing, stay exactly the hero's
        ge = self.R[key_of(GAP_SRC)]
        ratio = float(get1(ge, 'playerAttackSpeedCapMax')) / float(get1(ge, 'monsterAttackSpeedCapMax'))
        hands = [s for s in ('RightHand', 'LeftHand') if s in targets and targets[s]['weapon']
                 and get1(targets[s]['orig'], 'Class', '') != 'WeaponArmor_Shield']
        body = float(get1(pet, 'characterAttackSpeed'))
        parity = None
        if ratio < 1 and hands:
            new_body, delta = body * ratio, body * (1 - ratio)   # dual wield halves the weapon sum: +delta on each
            setv(pet, 'characterAttackSpeed', new_body, 1)
            for s in hands:
                r = own(s)
                setv(r, 'characterBaseAttackSpeed', float(get1(r, 'characterBaseAttackSpeed', 0) or 0) + delta, 1)
            parity = {'body': new_body, 'delta': delta, 'slots': hands}
            trim.append('attack-speed cap as a hero\'s: body %.4f -> %.4f, %s base speed +%.4f' % (
                body, new_body, '/'.join(hands), delta))
        for k in list(SPEED_KINDS) + list(DODGE_KINDS):
            over = static[k] - budget[k]
            if over > 1e-6 and armour_first:
                f = DODGE_KINDS[k][0] if k in DODGE_KINDS else 'character%sSpeedModifier' % k
                r = own(armour_first[0])
                setv(r, f, float(get1(r, f, 0) or 0) - over, 1)
                adjust[f] = adjust.get(f, 0.0) - over
                trim.append('%s %+.0f%% -> %+.0f%% (trimmed on %s)' % (k, static[k], budget[k], armour_first[0]))
        speed = ', '.join('%s %+.0f%% (hero cap %+.0f%%)' % (k, min(static[k], budget[k]), budget[k])
                          for k in list(SPEED_KINDS) + list(DODGE_KINDS))
        gear = ['speed bonuses from gear and passives: ' + speed] + ['  ' + x for x in trim]
        for s in order:
            t = targets[s]
            if t['rec'] is not t['orig']:
                setv(t['rec'], 'FileDescription', 'TQ Together companion gear: %s %s' % (cid, s))
            setv(pet, 'chanceToEquip%s' % s, 100.0, 1)
            setv(pet, 'chanceToEquip%sItem1' % s, 100, 0)
            setv(pet, 'loot%sItem1' % s, [t['rec']['name']] * 3)
            gear.append('%s: %s%s' % (s, self.label(t['orig']), (' + ' + '; '.join(t['added'])) if t['added'] else ''))
        lost_lines = ['%s: %s (%s)' % (label, key[0] if key[0] != 'g' else key[1], ', '.join(fs) or 'nowhere to put it')
                      for label, key, fs, _, _ in lost]
        ledger = {'slots': {s: targets[s]['orig']['name'] for s in order},
                  'worn': {s: targets[s]['rec']['name'] for s in order},
                  'sources': sources, 'lost': [(rn, idx, fs) for _, _, fs, rn, idx in lost], 'adjust': adjust,
                  'attack': parity, 'procs': procs}
        return gear, lost_lines, ledger

    def convert_autocast(self, cid, skill, level, controller):
        """an item skill with an auto-cast controller as a skill the creature runs itself (vanilla pet precedents):
          hit + self buff        -> Skill_PassiveOnHitBuffSelf (Distortion Field): chance, duration, cooldown after it
          hit + attack / area    -> Skill_OnHitAttackRadius (Storm Surge, 15 pets): a toggle, needs a buff-self slot
          low health + heal/buff -> Skill_PassiveOnLifeBuffSelf (wolf Survival Instinct, 20 pets): below 25 % (the
                                    engine's LowHealth threshold); no chance roll there, so cooldown / chance instead
          on equip + a toggle    -> the skill itself in a buff-self slot
        -> (record name, level, needs a toggle slot, what) or a reason string"""
        s, c = self.R.get(key_of(skill)), self.R.get(key_of(controller))
        if s is None or c is None:
            return 'missing record'
        trig = get1(c, 'triggerType', '') or ''
        chance = float(get1(c, 'chanceToRun', 0) or 0) or 100.0
        cls = get1(s, 'Class', '') or ''
        leaf = s['name'].split(BS)[-1].lower()[:-4]

        def at(rec, f):
            v = getv(rec, f) or [0]
            return float(v[min(max(level, 1), len(v)) - 1] or 0)

        def fresh(src, tag):
            r = self.clone(src, NS + 'gear\\%s_%s_%s.dbr' % (cid, tag, leaf))
            for vn, vt, vals in list(r['vars']):
                if PROC_STRIP.match(vn):
                    delv(r, vn)
            setv(r, 'skillMaxLevel', 1, 0)
            return r

        def stats(r, pat):
            child = self.R.get(key_of(get1(s, 'buffSkillName', '') or ''))
            for src in [x for x in (s, child) if x is not None]:
                for vn, vt, vals in src['vars']:
                    if vt in (0, 1) and vals and re.match(pat, vn):
                        v = at(src, vn)
                        if v:
                            setv(r, vn, int(v) if vt == 0 else v, vt)
            for f in PROC_FX:
                if get1(s, f, ''):
                    setv(r, f, get1(s, f))

        dur, cd = at(s, 'skillActiveDuration'), at(s, 'skillCooldownTime')
        if trig.startswith('HitBy') and 'BuffSelf' in cls:
            r = fresh(ONHIT_BUFF_SRC, 'onhit')
            stats(r, PROC_BUFF_FIELDS)
            setv(r, 'onHitActivationChance', chance, 1)
            setv(r, 'skillActiveDuration', dur or 5.0, 1)
            setv(r, 'skillCooldownTime', max(0.0, cd - dur), 1)    # its cooldown starts when the buff ends
            return r['name'], 1, False, 'on-hit buff (%g%%)' % chance
        if trig.startswith('HitBy') and re.match(r'Skill_(Attack|Defensive|DispelMagic)', cls):
            r = fresh(ONHIT_AOE_SRC, 'onhitaoe')
            stats(r, r'^(offensive|retaliation)')
            if get1(s, 'excludeRacialDamage', 0):
                setv(r, 'excludeRacialDamage', 1, 3)
            setv(r, 'onHitActivationChance', chance, 1)
            setv(r, 'skillCooldownTime', cd, 1)
            setv(r, 'skillTargetRadius', at(s, 'skillTargetRadius') or (at(s, 'projectileExplosionRadius') + 1.0) or 4.0, 1)
            setv(r, 'expansionTime', 0.2, 1)
            if get1(s, 'targetFxPakName', ''):
                setv(r, 'radiusEffectName', get1(s, 'targetFxPakName'))
            return r['name'], 1, True, 'on-hit area effect (%g%%)' % chance
        if trig == 'LowHealth' and re.search(r'BuffSelf|GiveBonus', cls):
            r = fresh(LOWLIFE_SRC, 'lowlife')
            stats(r, PROC_BUFF_FIELDS + r'|^skill(Life|Mana)Bonus$')
            if get1(s, 'skillBonusEffectName', ''):
                setv(r, 'skillBonusEffectName', get1(s, 'skillBonusEffectName'))
            setv(r, 'lifeMonitorPercent', 25.0, 1)
            setv(r, 'skillActiveDuration', dur or 0.5, 1)
            setv(r, 'skillCooldownTime', cd * 100.0 / chance, 1)   # no chance roll in this class: rarer instead
            return r['name'], 1, False, 'low-health effect'
        if trig == 'OnEquip' and 'Toggled' in cls:
            return s['name'], level, True, 'toggle'
        return 'a creature has no equivalent of %s on %s' % (trig, cls)

    def party_scale(self, extra):
        """1.4.0: the summoned companions count as `extra` more players - monsters, champions and bosses get the game's
        own co-op scaling (every game-balance pak of the engine except the player's / pets': 18 values per field,
        index players-1 + 6*difficulty, Normal, Epic and Legendary alike). Solo now reads the column of 1+extra players,
        2 players that of 2+extra ... capped at 6; a fraction lies between two columns (CompanionPlayers=1.5)."""
        if extra <= 1e-6:
            return
        ge = self.R[key_of(GAP_SRC)]
        done = set()
        for vn, vt, vals in ge['vars']:
            if not vn.lower().endswith('attributepak') or vn.lower() in ('playerattributepak', 'petattributepak') \
                    or not vals or not vals[0]:
                continue
            r = self.R.get(key_of(vals[0]))
            if r is None or r['name'].lower() in done:
                continue
            done.add(r['name'].lower())
            n, life = 0, None
            for f, t, v in list(r['vars']):
                if t not in (0, 1) or len(v) != 18:
                    continue
                new = list(v)
                for d in range(3):
                    for p in range(6):
                        x = min(p + extra, 5.0)
                        lo = int(x)
                        a, b = float(v[d * 6 + lo]), float(v[d * 6 + min(lo + 1, 5)])
                        val = a + (b - a) * (x - lo)
                        new[d * 6 + p] = val if t == 1 else int(round(val))
                if new != list(v):
                    setv(r, f, new, t)
                    n += 1
                    if f == 'characterLifeModifier':
                        life = (v[12], new[12])
            if n:
                self.db.mark(r['name'])
                log('  party: %s as for %g players, %d fields%s' % (
                    r['name'].split(BS)[-1], 1 + extra, n,
                    ', life on Legendary %+.0f%% -> %+.0f%%' % life if life else ''))

    def hero_life(self, mult):
        """Legendary monster and boss life x mult for the hero about to be played: the game's own game-balance tables
        (gameengine monsterAttributePak / monsterBossAttributePak, index players-1+6*difficulty), every party size"""
        self.life_mult = mult
        ge = self.R[key_of(GAP_SRC)]
        for f, m in (('monsterAttributePak', mult), ('monsterBossAttributePak', mult * HERO_BOSS)):
            if abs(m - 1.0) < 1e-6:
                continue
            r = self.R.get(key_of(get1(ge, f, '') or ''))
            vals = getv(r, 'characterLifeModifier') if r is not None else None
            if not vals or len(vals) < 13:
                continue
            new = [((1 + v / 100.0) * m - 1) * 100.0 if i >= 12 else v for i, v in enumerate(vals)]
            setv(r, 'characterLifeModifier', new, 1)
            self.db.mark(r['name'])
            log('  hero difficulty: %s life on solo Legendary %+.0f%% -> %+.0f%%' % (r['name'].split(BS)[-1], vals[12], new[12]))
        # 1.1.5: damage too, slower than life - every damage modifier of the table (their % becomes (1+%)*f) and the
        # offensive ability (x f), so a hero 85 in full gear is actually hit
        if abs(HERO_DAMAGE - 1.0) < 1e-6:
            return
        for f in ('monsterAttributePak', 'monsterBossAttributePak'):
            r = self.R.get(key_of(get1(ge, f, '') or ''))
            if r is None:
                continue
            n = 0
            for vn, vt, vals in list(r['vars']):
                if vt != 1 or len(vals) < 13:
                    continue
                if re.match(r'^offensive\w*Modifier$', vn):
                    setv(r, vn, [((1 + v / 100.0) * HERO_DAMAGE - 1) * 100.0 if i >= 12 else v for i, v in enumerate(vals)], 1)
                    n += 1
                elif vn == 'characterOffensiveAbility':
                    setv(r, vn, [v * HERO_DAMAGE if i >= 12 else v for i, v in enumerate(vals)], 1)
                    n += 1
            self.db.mark(r['name'])
            log('  hero difficulty: %s damage x%.2f (%d fields)' % (r['name'].split(BS)[-1], HERO_DAMAGE, n))

    def make_burden(self, cid, name, pct):
        """toggled ally aura on the companion: the whole party (hero, companions) deals pct % less total damage"""
        buff = self.clone(BURDEN_BUFF_SRC, NS + '%s_burden_buff.dbr' % cid)
        for vn, vt, vals in list(buff['vars']):
            if STAT_FIELD.match(vn) and not re.match(r'^skill(DisplayName|BaseDescription|UpBitmapName|DownBitmapName|'
                                                       r'MaxLevel|Tier|UltimateLevel|MasteryLevelRequired|TargetRadius|'
                                                       r'Connection)', vn) or \
                    re.match(r'^(skillCastAuraName|targetFxPakName|skillActivatedSound|skillDeactivatedSound|'
                             r'cameraShakeAmplitude|skillActiveManaCost)$', vn):
                delv(buff, vn)
        setv(buff, 'offensiveTotalDamageModifier', [-float(pct)], 1)
        setv(buff, 'skillTargetRadius', [BURDEN_RADIUS], 1)
        setv(buff, 'skillMaxLevel', 1, 0)
        setv(buff, 'skillUltimateLevel', 1, 0)
        setv(buff, 'skillUpBitmapName', SUMMON_ICON[0])
        setv(buff, 'skillDownBitmapName', SUMMON_ICON[1])
        setv(buff, 'skillDisplayName', self.tag('tagTQComp_%s_burden' % cid, 'Бремя Немезиды: %s' % name,
                                                'Burden of Nemesis: %s' % name))
        setv(buff, 'skillBaseDescription', self.tag('tagTQComp_%s_burdendesc' % cid,
             'Немезида взыскивает за зов героя из иного странствия: пока %s рядом, весь отряд наносит на %d%% '
             'меньше урона.' % (name, pct),
             'Nemesis exacts a price for calling a hero from another journey: while %s is near, the whole party deals '
             '%d%% less damage.' % (name, pct)))
        setv(buff, 'FileDescription', 'TQ Together companion %s: party burden -%d%% total damage' % (cid, pct))
        aura = self.clone(BURDEN_TOGGLE_SRC, NS + '%s_burden.dbr' % cid)
        setv(aura, 'buffSkillName', buff['name'])
        setv(aura, 'FileDescription', 'TQ Together companion %s: party burden aura' % cid)
        return aura

    def static_defense(self, pet, worn):
        """{resist field: %} always-on resistances: worn records + passive / toggled / modifier skills (and the buffs
        they cast) at their level; chance-based resistances left out; elemental resistance counted into fire/cold/
        lightning"""
        tot = collections.Counter()

        def add(r, lv, depth=0):
            if r is None or depth > 3:
                return
            d = {vn: vals for vn, vt, vals in r['vars']}
            for f in RESISTS + ('defensiveElementalResistance',):
                if d.get(f) and not float((d.get(f + 'Chance') or [0])[0] or 0):
                    v = float(d[f][min(max(lv, 1), len(d[f])) - 1])
                    for t in (ELEMENTAL if f == 'defensiveElementalResistance' else (f,)):
                        tot[t] += v
            for f in ('buffSkillName',):
                if d.get(f) and d[f][0]:
                    add(self.R.get(key_of(d[f][0])), lv, depth + 1)
        for r in worn:
            add(r, 1)
        for i in range(1, MAX_SKILLS + 1):
            sk = get1(pet, 'skillName%d' % i, '')
            r = self.R.get(key_of(sk)) if sk else None
            cls_ = get1(r, 'Class', '') or '' if r is not None else ''
            if r is not None and re.search(r'Passive|Toggled|Modifier', cls_) and 'PassiveOn' not in cls_:
                add(r, int(get1(pet, 'skillLevel%d' % i, 1) or 1))
        return tot

    def owner_pet_bonus(self):
        """1.2.0: what the hero about to be played gives EVERY pet (petBonusName on his skills and worn gear, e.g. the
        le_petscaling quest rewards: +100 % life each) - the companion is a hero, not a summon, so its own passive
        cancels it. Known only when TQ Together was told the hero (choose_hero); {} otherwise"""
        tot = collections.Counter()
        path = os.path.join(SAVES, '_' + HERO_NAME, 'Player.chr') if HERO_NAME else ''
        if not path or not os.path.isfile(path):
            return tot
        best = {}
        for sname, lv in read_char(path)['skills']:
            best[key_of(sname)] = max(best.get(key_of(sname), 0), int(lv))
        recs = [(self.R.get(k), lv) for k, lv in best.items()]
        for it in parse_equipment(path):
            recs += [(self.R.get(key_of(it.get(f) or '')), 1) for f in ('base', 'prefix', 'suffix', 'relic_bonus', 'relic_bonus2')]
        for r, lv in recs:
            b = self.R.get(key_of(get1(r, 'petBonusName', '') or '')) if r is not None else None
            if b is None:
                continue
            for f, (vt, v) in stat_fields(b, lv - 1).items():
                if vt in (0, 1):
                    tot[f] += v
        return tot

    def companion_passive(self, cid, rewards, static_def=None, owner_bonus=None):
        """the companion's own passive, levels 1/2/3 = Normal/Epic/Legendary: every quest-reward passive of the hero
        summed (plain attributes, no chances or durations), the pet game-balance pak (petAttributePak, which a hero
        does not get: 1.2.0 ALL of it - DA +600, life +400/+208 %, armor, resists, damage on Legendary - not only the
        speed) cancelled, the played hero's pet bonuses cancelled, and (1.1.3) the hero's difficulty resistance penalty
        added and every resistance trimmed to the hero's cap playerDefenseCap"""
        src = rewards[0][0] if rewards else PASSIVE_SRC
        r = self.clone(self.R[key_of(src)]['name'], NS + '%s_passive.dbr' % cid)
        for vn, vt, vals in list(r['vars']):    # keep the weapon flags (Axe, Bow, ... the passive is active with)
            if STAT_FIELD.match(vn) and (not vn.startswith('skill') or re.match(r'^skill(Cooldown|ManaCost|Projectile)', vn)):
                delv(r, vn)
        tot, types = collections.Counter(), {}
        for k, lv in rewards:
            for f, (vt, v) in stat_fields(self.R[k], int(lv) - 1).items():
                # 1.2.0: attributes only - skillMaxLevel/skillTier/skillUltimateLevel of the rewards were summed too
                if vt in (0, 1) and (not f.startswith('skill') or re.match(r'^skill(Cooldown|ManaCost|Projectile)', f)):
                    tot[f] += v
                    types[f] = vt
        ge = self.R[key_of(GAP_SRC)]
        pak = self.R.get(key_of(get1(ge, 'petAttributePak', '') or ''))
        per_diff = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
        # every component kept apart for the self-check (verify_companions: parts add up, the pak part cancels the pak)
        parts = {c: collections.defaultdict(lambda: [0.0, 0.0, 0.0]) for c in ('rewards', 'pak', 'owner', 'resist')}
        for f, v in tot.items():
            parts['rewards'][f] = [v, v, v]
        for vn, vt, vals in (pak['vars'] if pak is not None else []):
            if vt in (0, 1) and STAT_FIELD.match(vn) and vals and any(vals):
                for d in range(3):                  # index = players - 1 + 6 * difficulty; one player
                    x = -float(vals[min(6 * d, len(vals) - 1)])
                    per_diff[vn][d] += x
                    parts['pak'][vn][d] += x
                types[vn] = vt
        for f, v in (owner_bonus or {}).items():
            for d in range(3):
                per_diff[f][d] -= v
                parts['owner'][f][d] -= v
            types.setdefault(f, 1)
        if static_def is not None:
            pp = {vn: vals for vn, vt, vals in self.R[key_of(PLAYER_PAK)]['vars']}
            cap = float(get1(ge, 'playerDefenseCap'))
            for t in RESISTS:
                rew = tot[t] + (tot['defensiveElementalResistance'] if t in ELEMENTAL else 0.0)
                for d in range(3):
                    pen = float(pp[t][min(6 * d, len(pp[t]) - 1)]) if pp.get(t) else 0.0
                    # the pak's own resist bonus is cancelled above, so it does not count toward the cap
                    excess = max(0.0, static_def[t] + rew + pen - cap)
                    per_diff[t][d] += pen - excess
                    parts['resist'][t][d] += pen - excess
                types[t] = 1
        for f in sorted(set(tot) | set(per_diff)):
            vals = [tot[f] + per_diff[f][d] for d in range(3)] if f in per_diff else [tot[f]] * 3
            if any(vals):
                setv(r, f, [int(x) for x in vals] if types.get(f) == 0 else [float(x) for x in vals], types.get(f, 1))
        setv(r, 'skillMaxLevel', 3, 0)
        setv(r, 'FileDescription', 'TQ Together companion %s: %d quest rewards, pet pak and owner pet bonus cancelled'
             % (cid, len(rewards)))
        self.passive_parts = {c: {f: list(v) for f, v in p.items()} for c, p in parts.items()}
        return r

    def speed_budget(self):
        """{'Attack'|'SpellCast'|'Run': % bonus a hero can have at most} = gameengine playerXSpeedCapMax - 100"""
        ge = self.R[key_of(GAP_SRC)]
        out = {k: float(get1(ge, f)) - 100.0 for k, f in SPEED_KINDS.items()}
        out.update({k: float(get1(ge, c)) for k, (f, c) in DODGE_KINDS.items()})     # dodge caps are absolute %
        return out

    def speed_bonus(self, skill, level, buffs_only=False, depth=0):
        """{kind: %} a skill adds at this level, the buff it casts included; Total speed counts for every kind.
        buffs_only: only temporary buffs and auras count (attacks such as charges move fast only while striking)"""
        out = collections.Counter()
        r = self.R.get(key_of(skill or ''))
        if r is None or depth > 3:
            return out
        cls = get1(r, 'Class', '') or ''
        if buffs_only and depth == 0 and not re.search(r'Buff|PassiveOn', cls) or enemy_debuff(r):
            return out
        for vn, vt, vals in r['vars']:
            m = re.match(r'^character(Attack|SpellCast|Run|Total)SpeedModifier$', vn)
            if m and vals:
                v = float(vals[min(max(level, 1), len(vals)) - 1])
                for k in (SPEED_KINDS if m.group(1) == 'Total' else (m.group(1),)):
                    out[k] += v
            elif vn in DODGE_FIELD and vals:
                out[DODGE_FIELD[vn]] += float(vals[min(max(level, 1), len(vals)) - 1])
            elif SPEED_CHILD.match(vn) and vals and vals[0]:
                out.update(self.speed_bonus(vals[0], level, False, depth + 1))
        return out

    def skill_label(self, skill):
        r = self.R.get(key_of(skill or ''))
        t = self.vt['ru'].get(get1(r, 'skillDisplayName', '') or '') if r is not None else ''
        return t or (skill or '').split(BS)[-1]

    def trim_speed(self, cid, skill, room, depth=0):
        """personal copy of a buff (and of the buff it casts) with every speed bonus cut to what is left under the hero's
        caps (room, % per kind); Total speed is split into the three kinds so each is cut on its own. -> copy's name"""
        src = self.R[key_of(skill)]
        name = NS + 'gear\\%s_%s' % (cid, src['name'].split(BS)[-1].lower())
        if self.R.get(name) is not None:
            return name
        r = self.clone(src['name'], name)
        arr = {vn: list(vals) for vn, vt, vals in r['vars']}
        speed = {k: arr.get('character%sSpeedModifier' % k, []) for k in SPEED_KINDS}
        total = arr.get('characterTotalSpeedModifier', [])
        n = max([len(v) for v in list(speed.values()) + [total]] or [0])
        at = lambda a, i: float(a[min(i, len(a) - 1)]) if a else 0.0
        for k in SPEED_KINDS:
            vals = [min(at(speed[k], i) + at(total, i), room[k]) if at(speed[k], i) + at(total, i) > 0
                    else at(speed[k], i) + at(total, i) for i in range(n)]
            delv(r, 'character%sSpeedModifier' % k)
            if any(vals):
                setv(r, 'character%sSpeedModifier' % k, vals, 1)
            room[k] = max(0.0, room[k] - max(vals + [0.0]))
        delv(r, 'characterTotalSpeedModifier')
        for k, (f, c) in DODGE_KINDS.items():                 # dodge / deflect buffs: cut to the room under the cap
            if arr.get(f):
                vals = [min(float(v), room[k]) if float(v) > 0 else float(v) for v in arr[f]]
                setv(r, f, vals, 1)
                room[k] = max(0.0, room[k] - max(vals + [0.0]))
        for vn, vt, vals in list(r['vars']):
            if SPEED_CHILD.match(vn) and vals and vals[0] and depth < 3 and any(self.speed_bonus(vals[0], 99).values()):
                setv(r, vn, self.trim_speed(cid, vals[0], room, depth + 1))
        setv(r, 'FileDescription', 'TQ Together companion %s: %s with speed held to the hero cap' % (cid, src['name']))
        return name

    def static_speed(self, pet, worn):
        """{kind: %} always-on speed bonuses: worn records + passive / toggled / modifier skills at their level"""
        tot = collections.Counter({k: 0.0 for k in list(SPEED_KINDS) + list(DODGE_KINDS)})
        for r in worn:
            for vn, vt, vals in r['vars']:
                m = re.match(r'^character(Attack|SpellCast|Run|Total)SpeedModifier$', vn)
                if m and vals:
                    for k in (SPEED_KINDS if m.group(1) == 'Total' else (m.group(1),)):
                        tot[k] += float(vals[0])
                elif vn in DODGE_FIELD and vals:
                    tot[DODGE_FIELD[vn]] += float(vals[0])
        self.trees()
        on_self = lambda c: re.search(r'Passive|Toggled', c or '') and 'PassiveOn' not in c
        for i in range(1, MAX_SKILLS + 1):
            sk = get1(pet, 'skillName%d' % i, '')
            r = self.R.get(key_of(sk)) if sk else None
            cls_ = get1(r, 'Class', '') or '' if r is not None else ''
            if r is None or not re.search(r'Passive|Toggled|Modifier', cls_) or 'PassiveOn' in cls_:
                continue
            if MOD_CLASS.search(cls_):
                # 1.3.2: a modifier acts on the character only through a passive / toggle parent (Lucid Dream's Temporal
                # Flux); Plague's Fatigue modifies an attack that slows ENEMIES (Game.dll: Skill_Modifier collectors)
                par = self.R.get(self._tree_parent.get(key_of(sk), ''))
                if par is None or not on_self(get1(par, 'Class', '')):
                    continue
            tot.update(self.speed_bonus(sk, int(get1(pet, 'skillLevel%d' % i, 1) or 1)))
        return tot

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
        """-> ordered [(key, name, level, class, role)] (modifiers right after their parent), dropped [(leaf, why)],
        quest-reward passives [(key, level)], attacks beyond the AI's 5 slots [(key, name, level, class)]"""
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
            if any(get1(r, f, 0) for f in ('offensiveTauntMin', 'offensiveTauntMax')):   # owner 24.09
                dropped.append((leaf, 'taunt: enemies would chase the companion instead of you')); continue
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
        out, used, rewards, overflow = [], collections.Counter(), [], []
        for k in groups:
            lv, c = normal[k]
            ro = role(c)
            if quest(k) and c == 'Skill_Passive':          # 1.0.6: all folded into one passive (frees slots)
                rewards.append((k, lv)); continue
            if ro in CAP and used[ro] >= CAP[ro]:
                if ro == 'attack' and c in AUTOCAST_CLASSES:   # 1.0.6: cast from the companion's gear instead
                    overflow.append((k, self.R[k]['name'], lv, c))
                    for m in mods.get(k, []):
                        dropped.append((m.split(BS)[-1], 'modifier of %s, cast outside the AI slots (not applied)'
                                        % k.split(BS)[-1]))
                    continue
                dropped.append((k.split(BS)[-1], 'no free AI slot for ' + ro)); continue
            if len(out) >= MAX_SKILLS:
                dropped.append((k.split(BS)[-1], 'all %d skill slots full' % MAX_SKILLS)); continue
            used[ro] += 1
            out.append((k, self.R[k]['name'], lv, c, ro))
            for m in sorted(mods.get(k, []), key=lambda m: self._tree_pos.get(m, (999, 0))):
                if len(out) >= MAX_SKILLS:
                    dropped.append((m.split(BS)[-1], 'all %d skill slots full' % MAX_SKILLS)); continue
                out.append((m, self.R[m]['name'], cand[m][0], cand[m][1], 'mod'))
        return out, dropped, rewards, overflow

    def wire_ai(self, pet, chosen):
        for vn, vt, vals in list(pet['vars']):
            if AI_FIELDS.match(vn):
                delv(pet, vn)
        toggles = [x for x in chosen if x[4] == 'toggle']
        if toggles:
            setv(pet, 'initialSkillName', toggles[0][1])
            # 1.1.8: the initial toggle is cast once on summon; if something cuts it (1.1.7: the item-proc aura cast
            # at the first enemy - Blade Honing never came on), nothing re-cast it. The hero's toggles also go to
            # the buff-self slots: the AI casts from there only a toggle that is not active, so a live one stays on
            again = toggles[:3] if len(toggles) <= 3 else toggles[1:4]
            for i, x in enumerate(again):
                setv(pet, 'buffSelf%sSkillName' % ('' if i == 0 else i + 1), x[1])
        for x in [x for x in chosen if x[4] == 'pool'][:1]:
            setv(pet, 'attackSkillName', x[1])
        for i, x in enumerate([x for x in chosen if x[4] == 'buffother'][:3]):
            setv(pet, 'buffOther%sSkillName' % ('' if i == 0 else i + 1), x[1])
        for x in [x for x in chosen if x[4] == 'heal'][:1]:
            setv(pet, 'healSkillName', x[1])
            setv(pet, 'healSkillDelay', HEAL_DELAY, 1)
        wired = []
        for i, x in enumerate([x for x in chosen if x[4] == 'attack'][:5]):
            p = 'specialAttack' + ('' if i == 0 else str(i + 1))
            rng, ch, dl, to = SPECIAL.get(x[3], SPECIAL_DEFAULT)
            # 1.1.4: a skill with no cooldown of its own was spammed and cut Phantom Strike short - the companion waits
            # NO_COOLDOWN_DELAY between its uses, like a hero who also swings in between. 1.1.6: any cooldown shorter
            # than that counts (Throwing Knife: 6 s at level 1 down to 1.6 s at level 12, so 1.1.4 missed it)
            cds = getv(self.R[x[0]], 'skillCooldownTime') or [0]
            if float(cds[min(max(int(x[2]), 1), len(cds)) - 1] or 0) < NO_COOLDOWN_DELAY:
                dl = max(dl, NO_COOLDOWN_DELAY)
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
            if cls != 'Skill_Mastery':            # quest-reward passives: the companion's own passive (1.0.6)
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
        # 1.2.0: every attribute the doppelganger record brings becomes the hero body's (life regen 10/25/50 -> 2, the
        # resist penalty arrays that doubled ours, 4 attack / 4 defense slots -> 8 / 12, race 'Magical' -> none);
        # our own base values (save attributes, speeds, level) are set below
        for vn, vt, vals in list(pet['vars']):
            if vt in (0, 1) and (re.match(r'^(character|defensive|offensive|retaliation)', vn)
                                 or vn in ('numAttackSlots', 'numDefenseSlots')):
                bv = getv(pc, vn)
                if bv:
                    setv(pet, vn, list(bv) if len(bv) > 1 else bv[0], vt)
                else:
                    delv(pet, vn)
        delv(pet, 'characterRacialProfile')
        delv(pet, 'doppelGear')
        setv(pet, 'dropItems', 0, 3)
        setv(pet, 'controller', self.fast_controller())
        setv(pet, 'controllerAggressive', self.fast_controller('aggressive'))
        setv(pet, 'controllerDefensive', self.fast_controller('defensive'))
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
        for f in BASE_SPEEDS:
            setv(pet, f, float(get1(pc, f)), 1)
        for key, field in (('str', 'characterStrength'), ('dex', 'characterDexterity'), ('int', 'characterIntelligence'),
                           ('life', 'characterLife'), ('mana', 'characterMana')):
            if attrs.get(key):
                setv(pet, field, [float(attrs[key])], 1)
        # skills
        for vn, vt, vals in list(pet['vars']):
            if re.match(r'skill(Name|Level)\d+$', vn):
                delv(pet, vn)
        chosen, dropped, rewards, overflow = self.pick_skills(c['skills'], weapons)
        # masteries are not skills a creature can hold: fold their flat bonuses (life, str/dex/int, mana) into the
        # base stats, as the game adds them on top of the save's values
        folded = self.fold_passives(c['skills'], {x[0] for x in chosen})
        for key, field in (('str', 'characterStrength'), ('dex', 'characterDexterity'), ('int', 'characterIntelligence'),
                           ('life', 'characterLife'), ('mana', 'characterMana')):
            if attrs.get(key) or folded.get(key):
                setv(pet, field, [float(attrs.get(key, 0) + folded.get(key, 0))], 1)
        for i, (k, nm, lv, cls, ro) in enumerate(chosen, 1):
            setv(pet, 'skillName%d' % i, nm)
            setv(pet, 'skillLevel%d' % i, [int(lv)], 0)
        wired = self.wire_ai(pet, chosen)
        # 1.0.7: the first attack beyond the AI's 5 slots follows the special attack with the longest delay (vanilla
        # chainInitialSkill/chainNextSkill, 183 monsters): cast by the AI with its animation. The chain ignores
        # cooldowns, so that special's delay is raised to the chained skill's cooldown. The rest: auto-cast from gear
        for f in ('chainInitialSkill', 'chainNextSkill', 'chainBehavior'):
            delv(pet, f)
        if overflow and len(chosen) < MAX_SKILLS - 1:
            k, nm, lv, cls = overflow.pop(0)
            chosen.append((k, nm, lv, cls, 'chain'))
            setv(pet, 'skillName%d' % len(chosen), nm)
            setv(pet, 'skillLevel%d' % len(chosen), [int(lv)], 0)
            specials = [p for p in ('specialAttack', 'specialAttack2', 'specialAttack3', 'specialAttack4', 'specialAttack5')
                        if get1(pet, p + 'SkillName', '')]
            # 1.0.8: after Phantom Strike (a blink, 2 vanilla chains) Flash Powder never came - start the chain from
            # the class vanilla chains start from most often, then the longest delay
            first = max(specials, key=lambda p: (
                CHAIN_PRECEDENT.get(get1(self.R.get(key_of(get1(pet, p + 'SkillName'))) or {'vars': []}, 'Class', ''), 0),
                float(get1(pet, p + 'Delay', 0) or 0)))
            cds = getv(self.R[k], 'skillCooldownTime') or [0]
            cd = float(cds[min(max(int(lv), 1), len(cds)) - 1] or 0)
            setv(pet, first + 'Delay', max(float(get1(pet, first + 'Delay', 0) or 0), cd), 1)
            setv(pet, 'chainInitialSkill', get1(pet, first + 'SkillName'))
            setv(pet, 'chainNextSkill', nm)
            setv(pet, 'chainBehavior', 'UseOnCurrentEnemy')
            wired.append('%s -> chain -> %s' % (get1(pet, first + 'SkillName').split(BS)[-1], nm.split(BS)[-1]))
        burden = party_burden()
        if burden and len(chosen) < MAX_SKILLS - 1:
            aura = self.make_burden(cid, name, burden)
            chosen.append((key_of(aura['name']), aura['name'], 1, 'Skill_BuffRadiusToggled', 'toggle'))
            setv(pet, 'skillName%d' % len(chosen), aura['name'])
            setv(pet, 'skillLevel%d' % len(chosen), [1], 0)
            # cast at once on summon: the burden becomes the initial skill, the hero's own toggles move down
            own_toggles = [get1(pet, f, '') for f in ('initialSkillName', 'buffSelfSkillName', 'buffSelf2SkillName',
                                                       'buffSelf3SkillName')]
            own_toggles = [x for i, x in enumerate(own_toggles) if x and x not in own_toggles[:i]]
            setv(pet, 'initialSkillName', aura['name'])
            for f in ('buffSelfSkillName', 'buffSelf2SkillName', 'buffSelf3SkillName'):
                delv(pet, f)
            for f, x in zip(('buffSelfSkillName', 'buffSelf2SkillName', 'buffSelf3SkillName'), own_toggles):
                setv(pet, f, x)
            for x in own_toggles[3:]:
                dropped.append((x.split(BS)[-1], 'toggle: no AI slot left after the party burden'))
            wired.append('initial: party burden -%d%% damage' % burden)
        # what every vanilla permanent pet has and the doppel clone lacked: pet panel + hover widget, AI range classes
        self.copy_fields(PET_PANEL_SRC, pet, ('showStatusWidgetWhenPet', 'StatusIcon', 'StatusIconRed', 'healSkillDelay'))
        self.copy_fields(PET_RANGE_SRC, pet, ('mediumRangeMin', 'longRangeMin'))
        self.copy_fields(PC[gender], pet, ('actorRadius', 'actorHeight'))
        delv(pet, 'distressCallGroup')
        for f, vt, v in DISTRESS:
            setv(pet, f, v, vt)
        # gear: personal copies of the worn records with affixes, relics, bonuses, amulet and artifact baked in
        for vn, vt, vals in list(pet['vars']):
            if re.match(r'^(chanceToEquip|loot)(Head|Torso|LowerBody|Forearm|Finger1|Finger2|RightHand|LeftHand|Misc\d)', vn):
                delv(pet, vn)
        for k, nm, lv, cls in overflow:        # 1.1.7: item auto-cast does not run on creatures - nowhere to put them
            dropped.append((k.split(BS)[-1], 'no AI slot left (the 5 special attacks and the chain are taken)'))
        self.last_run_bonus, self.last_speed = 0.0, {}
        gear, skipped, self.gear_ledger[pet['name'].lower()] = self.bake_gear(cid, pet, equipped)
        self.hero_run[name] = self.last_run_bonus
        self.hero_speed[name] = dict(self.last_speed)
        # 1.1.7: item auto-cast skills turned into the companion's own skills; area procs are toggles that the AI
        # switches on once (a buff-self slot, BuffSelfBehavior WhenEnemyIsSeen on our controllers)
        led = self.gear_ledger[pet['name'].lower()]
        placed = []
        for nm, lv, toggle, what in led['procs']:
            slot = next((f for f in ('buffSelfSkillName', 'buffSelf2SkillName', 'buffSelf3SkillName')
                         if not get1(pet, f, '')), None) if toggle else 'none'
            if len(chosen) >= MAX_SKILLS - 1 or slot is None:
                # 1.3.2: the hero's own toggles (auras of two masteries) can fill all three buff-self slots; they come
                # first, the item proc stays out - and out of the ledger, so the self-check does not look for it
                dropped.append((nm.split(BS)[-1], 'no skill or buff-self slot left for the item skill'))
                continue
            placed.append((nm, lv, toggle, what))
            chosen.append((key_of(nm), nm, lv, get1(self.R[key_of(nm)], 'Class', ''), 'item proc'))
            setv(pet, 'skillName%d' % len(chosen), nm)
            setv(pet, 'skillLevel%d' % len(chosen), [int(lv)], 0)
            if toggle:
                setv(pet, slot, nm)
        led['procs'] = placed
        # 1.0.6: quest rewards + the pet difficulty bonus cancelled, in one passive at the end of the list (after it no
        # modifier can re-attach to it); one skill level per difficulty
        worn_recs = [self.R[key_of(w)] for w in self.gear_ledger[pet['name'].lower()]['worn'].values()]
        own_passive = self.companion_passive(cid, rewards, self.static_defense(pet, worn_recs),
                                             self.owner_bonus if HERO_NAME and HERO_NAME.lower() != name.lower() else None)
        self.gear_ledger[pet['name'].lower()]['passive'] = self.passive_parts
        if len(chosen) < MAX_SKILLS:
            chosen.append((key_of(own_passive['name']), own_passive['name'], [1, 2, 3], 'Skill_Passive', 'passive'))
            setv(pet, 'skillName%d' % len(chosen), own_passive['name'])
            setv(pet, 'skillLevel%d' % len(chosen), [1, 2, 3], 0)
        else:
            dropped.append((own_passive['name'].split(BS)[-1], 'all %d skill slots full' % MAX_SKILLS))
        title_ru = '%s ~ соратник' % name
        setv(pet, 'description', self.tag('tagTQComp_%s_pet' % cid, title_ru, '%s ~ Companion' % name))
        # 1.3.4: database strings are written as cp1252 - a Cyrillic name becomes '?????' and two heroes with names of the
        # same length would repeat the string (see arz_lazy.save); only the cid (ASCII, unique) goes into the database
        setv(pet, 'FileDescription', 'TQMod companion %s from save (level %d)' % (cid, L))
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
        setv(bon, 'FileDescription', 'TQMod companion relic bonus: %s' % cid)
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
        setv(relic, 'FileDescription', 'TQMod companion relic: %s%s' % (cid, '' if sk is not None else ' (faded)'))
        return relic

    def tombstone(self, cid, name, why='save deleted'):
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
        log('  tombstone: %s (%s)' % (name, why))

    def fast_controller(self, kind='normal'):
        name = NS + ('controller_companion.dbr' if kind == 'normal' else 'controller_companion_%s.dbr' % kind)
        if self.R.get(name) is None:
            if kind == 'defensive':               # 1.1.9: the vanilla defensive stance, only the heal thresholds ours
                c = self.clone(CONTROLLERS[2], name)
            else:
                c = self.clone(CTRL_SRC, name)
                for k, v in (FAST_CONTROLLER if kind == 'normal' else AGGR_CONTROLLER).items():
                    setv(c, k, v, 1)
            for k, v in HEAL_CONTROLLER.items():
                setv(c, k, v, 0)
            setv(c, 'FileDescription', 'TQMod companion: LicheKing %s + fast anger, heals the hero first' % kind)
        return name

    def shard_table(self, relics):
        """records/tqmod/companions/eidolon_shards.dbr: one eidolon shard, every live companion equally likely"""
        shards = self.clone(RELIC_TABLE_SRC, NS + 'eidolon_shards.dbr')   # any record; rebuilt as a FixedWeight table
        for vn, vt, vals in list(shards['vars']):
            delv(shards, vn)
        setv(shards, 'templateName', 'database' + BS + 'Templates' + BS + 'LootItemTable_FixedWeight.tpl')
        setv(shards, 'Class', 'LootItemTable_FixedWeight')
        chunks = [relics[i:i + 30] for i in range(0, len(relics), 30)]   # lootName1..30 per table
        if len(chunks) == 1:
            for i, r in enumerate(relics, 1):
                setv(shards, 'lootName%d' % i, r)
                setv(shards, 'lootWeight%d' % i, 100, 0)
        else:
            setv(shards, 'templateName', 'database' + BS + 'Templates' + BS + 'LootMasterTable.tpl')
            setv(shards, 'Class', 'LootMasterTable')
            for c, chunk in enumerate(chunks, 1):
                t = self.clone(RELIC_TABLE_SRC, NS + 'eidolon_shards_%d.dbr' % c)
                for vn, vt, vals in list(t['vars']):
                    delv(t, vn)
                setv(t, 'templateName', 'database' + BS + 'Templates' + BS + 'LootItemTable_FixedWeight.tpl')
                setv(t, 'Class', 'LootItemTable_FixedWeight')
                for i, r in enumerate(chunk, 1):
                    setv(t, 'lootName%d' % i, r)
                    setv(t, 'lootWeight%d' % i, 100, 0)
                setv(shards, 'lootName%d' % c, t['name'])
                setv(shards, 'lootWeight%d' % c, 100 * len(chunk), 0)
        setv(shards, 'FileDescription', 'TQMod companions: one eidolon shard, companions equally likely')
        return shards

    def add_shard(self, loot, shards, pct):
        return self.add_shards(loot, [(shards['name'], pct)])

    def add_shards(self, loot, entries):
        """put shard tables [(table name, pct)] into a FixedItemLoot record so that ONE opening gives each with its
        pct % (1.5.0): each of the record's N items (numSpawn equations) picks a slot by chance / running total of the
        six chances, so a per-item p_i with mean over N of 1-(1-p_i)^N = pct_i is solved for each, and the chance
        added to one slot is delta = P * total / (1 - P), P = sum of the p_i, split by weight. 1.6.0: several at once
        (the eidolon shard and the soul of the orb's region) - added one after the other, the second would dilute
        the first. Inside that slot every vanilla entry keeps chance x weight / slot weight.
        1.7.8 (owner 18.10: "a heap of electrum orbs, eidolon shards, not one soul shard"): the engine reads SIX entries
        per slot (orb_odds.SLOT_MAX); the soul went in as the 7th or 8th and never dropped - in Hades', Tiamat's and the
        Jade Emperor's orbs the eidolon shard neither, nor any soul of a boss chest. Now what we add is ONE entry: our
        table alone, or a LootMasterTable of our tables by weight (shards_wrap), in a free entry of a slot (the relic
        slot first); with no free entry anywhere it takes one vanilla entry in with ours - by weight, so that entry
        keeps its odds as well."""
        entries = [(t, pct) for t, pct in entries if pct > 0]
        if not entries:
            return False
        SM = orb_odds.SLOT_MAX
        total = sum(float(get1(loot, 'loot%dChance' % s_, 0) or 0) for s_ in range(1, 7))
        slots = []
        for s_ in range(1, 7):
            ch = float(get1(loot, 'loot%dChance' % s_, 0) or 0)
            names = [(j, get1(loot, 'loot%dName%d' % (s_, j), '')) for j in range(1, SM + 1)]
            free = [j for j, x in names if not x]
            names = [(j, x) for j, x in names if x]
            W = sum(float(get1(loot, 'loot%dWeight%d' % (s_, j), 0) or 0) for j, _ in names)
            if ch and W:
                slots.append((0 if free else 1, 0 if any('relic' in x.lower() for _, x in names) else 1, ch, s_, W,
                              free, names))
        if not slots or total <= 0:
            return False
        ns = orb_odds.spawn_counts({vn: vals for vn, vt, vals in loot['vars']})
        ps = []
        for _t, pct in entries:
            lo, hi = 0.0, 1.0
            for _ in range(60):                      # mean over N of 1 - (1 - p)^N is monotone in p
                mid = (lo + hi) / 2
                if sum(1 - (1 - mid) ** n for n in ns) / len(ns) < pct / 100.0:
                    lo = mid
                else:
                    hi = mid
            ps.append((lo + hi) / 2)
        P = sum(ps)
        delta = P * total / (1 - P)
        _, _, ch, s_, W, free, names = min(slots, key=lambda x: x[:4])
        # 1.6.0: small vanilla weights would round our shares coarsely - the slot's weights are scaled up first
        # (chance x weight / slot weight of every vanilla entry does not change)
        smallest = delta * min(ps) / P * W / ch
        if smallest < 2000:
            m = int(-(-2000 // max(smallest, 1e-9)))
            for j, _ in names:
                setv(loot, 'loot%dWeight%d' % (s_, j), int(float(get1(loot, 'loot%dWeight%d' % (s_, j), 0) or 0)) * m, 0)
            W *= m
        # weights are ints; scaled up so that two shards in one slot keep their ratio (eidolon 40 % next to a soul
        # 10 %), the slot chance absorbs the rounding
        mine = [(t, max(1, int(round(delta * p / P * W / ch)))) for (t, pct), p in zip(entries, ps)]
        added = sum(w for _, w in mine)
        if free:
            j = free[0]
            name = mine[0][0] if len(mine) == 1 else self.shards_wrap(loot, s_, mine)['name']
            pos_w = added
        else:
            j, x = names[-1]
            wx = int(float(get1(loot, 'loot%dWeight%d' % (s_, j), 0) or 0))
            name, pos_w = self.shards_wrap(loot, s_, [(x, wx)] + mine)['name'], wx + added
        setv(loot, 'loot%dName%d' % (s_, j), name)
        setv(loot, 'loot%dWeight%d' % (s_, j), pos_w, 0)
        setv(loot, 'loot%dChance' % s_, ch * (W + added) / W, 1)   # every vanilla entry keeps ch*w_i/W exactly
        self.db.mark(loot['name'])
        return True

    def shards_wrap(self, loot, slot, pairs):
        """1.7.8: a LootMasterTable of [(table, weight)] taking ONE entry of `slot` in the loot record (the engine reads
        six per slot): the tables are picked by weight, as they would be side by side in the slot"""
        name = NS + 'shards' + BS + '%s_%d.dbr' % (hashlib.md5(loot['name'].lower().encode('utf-8')).hexdigest()[:10], slot)
        t = self.clone(RELIC_TABLE_SRC, name)
        for vn, vt, vals in list(t['vars']):
            delv(t, vn)
        setv(t, 'templateName', 'database' + BS + 'Templates' + BS + 'LootMasterTable.tpl')
        setv(t, 'Class', 'LootMasterTable')
        for i, (x, w) in enumerate(pairs, 1):
            setv(t, 'lootName%d' % i, x)
            setv(t, 'lootWeight%d' % i, int(w), 0)
        setv(t, 'FileDescription', 'TQ Together: one entry of %s slot %d, %d tables by weight' % (
            loot['name'].split(BS)[-1][:-4], slot, len(pairs)))
        return t

    def eidolon_drops(self, relics, soul_orbs=None):
        """1.5.0: eidolon shards from electrum orbs of every difficulty (EidolonOrbChance % per orb). 1.5.1: and from
        the boss itself when it dies (EidolonBossChance % per kill), owner 15.10 - the chest felt like nothing ever
        dropped: an empty Misc loot slot of every Boss monster (lootMiscN / chanceToEquipMiscN, as ordinary monsters
        carry potions and relics) gets the shard table. Act bosses keep their Misc chances at 0 and give their loot
        through the boss chest, so their own loot is unchanged; bosses that drop nothing themselves (dropItems 0:
        the early stages of multi-stage bosses) are left out.
        1.6.0: soul_orbs {region: (table, % per orb)} - the boss souls of the orb's region go into the same orbs in
        the same addition (souls.py)."""
        orb_pct, boss_pct = drop_chances()
        soul_orbs = soul_orbs or {}
        if not relics and not soul_orbs:
            return
        shards = self.shard_table(relics) if relics else None
        n = 0
        for k in sorted(self.R):
            if 'electrumorbs' in k and k.endswith('_loot.dbr') and any(t in k for t in ORB_TIERS):
                m = re.search(r'x4_electrumorb_(\d_[a-z]+)_', k.split(BS)[-1])
                entries = [(shards['name'], orb_pct)] if shards is not None and orb_pct > 0 else []
                if m and m.group(1) in soul_orbs:
                    entries.append(soul_orbs[m.group(1)])
                if not entries:
                    continue
                if self.add_shards(self.R[k], entries):
                    n += 1
                else:
                    log('  WARNING: no room for eidolons / souls in %s' % k)
        log('  eidolon shards%s in %d electrum orbs (all difficulties), %g%% per orb' % (
            ' and boss souls' if soul_orbs else '', n, orb_pct if shards is not None else 0))
        if boss_pct <= 0 or shards is None:
            return
        done, full = 0, []
        rows = self.souls.scan() if getattr(self, 'souls', None) is not None else None
        for k, r in boss_monsters(self.R, rows):
            n = free_misc_slot(r)
            if n is None:
                full.append(k.split(BS)[-1])
                continue
            setv(r, 'chanceToEquipMisc%d' % n, boss_pct, 1)
            setv(r, 'lootMisc%dItem1' % n, shards['name'])
            setv(r, 'chanceToEquipMisc%dItem1' % n, 1, 0)
            self.db.mark(r['name'])
            done += 1
        log('  eidolon shards from %d boss monsters, %g%% per kill%s' % (
            done, boss_pct, ', %d without a free loot slot left alone' % len(full) if full else ''))

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
        # 1.6.0: merchants only (all 171 vanilla ring merchants sit under npc / merchant paths), a few fields each -
        # R.items() decoded and cached all 74k records, and the save re-encoded them (2 minutes)
        names = ['marketRingTable%d' % i for i in range(1, 9)]
        few = getattr(self.R, 'fields', None)
        for k in list(self.R):
            if 'npc' not in k and 'merchant' not in k:
                continue
            F = few(k, names) if few else {vn.lower(): vals for vn, vt, vals in self.R[k]['vars']}
            for n in names:
                targets.update(key_of(v) for v in (F.get(n.lower()) or []) if isinstance(v, str) and v)
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
        import tweaks                # the player's own database tweaks go under everything we build
        self.tweak_touched, self.tweaks_done = tweaks.apply(self.db, log)
        self.party_scale(PARTY_EXTRA)
        self.hero_life(HERO_LIFE)
        self.owner_bonus = self.owner_pet_bonus()
        if self.owner_bonus:
            log('  pet bonuses of %s cancelled on the companions: %s' % (HERO_NAME, dict(self.owner_bonus)))
        rings, self.relics, active = [], [], {}
        for path in sorted(glob.glob(os.path.join(SAVES, '_*', 'Player.chr'))):
            r = self.companion(path)
            if r:
                rings.append(r)
                active[r.split(BS)[-1][:-len('_ring.dbr')]] = self.report[-1][0]
        reg = dict(self.registry)
        refs = referenced_cids()
        # heroes whose eidolons/rings/summons something still holds, even if the registry was lost
        for cid in refs:
            reg.setdefault(cid, cid)
        # a hero whose save folder is still there keeps his records even if he is not a companion right now
        present = {d.lower() for d in os.listdir(SAVES) if os.path.isfile(os.path.join(SAVES, d, 'Player.chr'))} \
            if os.path.isdir(SAVES) else set()
        has_folder = {cid for folder, cid in self.folders.items() if folder in present}
        gone = []
        for cid, name in sorted(reg.items()):
            if cid in active:
                continue
            if cid in refs:
                self.tombstone(cid, name, 'save deleted, kept: referenced by %s' % refs[cid])
            elif cid in has_folder:
                self.tombstone(cid, name, 'not a companion right now, save folder still there')
            else:
                gone.append(cid)
                log('  removed: %s (deleted, no item anywhere refers to it)' % name)
        for cid in gone:
            del reg[cid]
        self.folders = {f: c for f, c in self.folders.items() if c not in gone}
        reg.update(active)
        self.registry = reg
        m = self.clone(RELIC_BONUS_SRC, MARKER)
        for vn, vt, vals in list(m['vars']):
            if vn not in ('templateName', 'Class'):
                delv(m, vn)
        setv(m, 'FileDescription', 'TQ Together marker: this database was built by TQ Together (inert, never loaded)')
        # 1.6.0: boss souls - records first, then the eidolons and the souls go into the orbs together, then the
        # souls' kill / chest drops (they share the eidolon shard's loot slot of a boss)
        import souls
        self.souls = souls.Souls(self, HERO_LEVEL, HERO_NAME)
        self.souls.build()
        self.eidolon_drops(self.relics, self.souls.orb_entries)
        self.souls.place()
        self.soul_ledger = self.souls.ledger
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
                f.write('   gear (worn records with everything else on the gear baked in):\n' +
                        ''.join('     %s\n' % x for x in gear))
                f.write('   not transferred:\n' + ''.join('     %s\n' % x for x in skipped))
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


SCAN_EXT = ('.chr', '.dxb', '.dxg', '.vault', '.json')
# our record names as items store them: backslashes in saves, doubled in TQVault's JSON, maybe forward slashes
REF_PAT = re.compile(rb'records(?:\\\\|\\|/)+tqmod(?:\\\\|\\|/)+companions(?:\\\\|\\|/)+'
                     rb'([a-z0-9_]+?)_(?:relic_bonus|relic|ring|summon)\.dbr', re.I)


def scan_roots():
    """every place an item of ours can sit: SaveData (heroes and their Backup folders, custom-quest heroes, the
    transfer stash incl. mod stashes, archived heroes), the game's own backup, TQVault vaults, Legendary Start
    backups, plus ScanPaths=dir1;dir2 from TQTogether.ini"""
    user = paths.tq_user_dir()
    mg = os.path.dirname(user)
    roots = [os.path.dirname(SAVES), os.path.join(mg, 'Titan Quest Backup'),
             os.path.join(mg, 'Titan Quest', 'TQVaultData'), os.path.join(mg, 'TQVaultData'),
             os.path.join(user, 'Legendary Start')]
    roots += [p.strip() for p in paths.settings().get('scanpaths', '').split(';') if p.strip()]
    return [r for r in roots if os.path.isdir(r)]


def referenced_cids(roots=None):
    """{cid: first file that refers to it} for every relic / ring / summon record of ours that anything still holds.
    Heroes found here keep their records (a tombstone at least): deleting records under an item breaks the item."""
    out = {}
    for root in (scan_roots() if roots is None else roots):
        for dp, dn, fns in os.walk(root):
            for fn in fns:
                if not fn.lower().endswith(SCAN_EXT):
                    continue
                p = os.path.join(dp, fn)
                try:
                    with open(p, 'rb') as f:
                        data = f.read()
                except OSError:
                    continue
                for m in REF_PAT.finditer(data):
                    out.setdefault(m.group(1).decode().lower(), p)
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
    # which deleted heroes are still referenced decides what is kept and what is cleaned up
    h.update(json.dumps(sorted(referenced_cids())).encode('utf-8'))
    import tweaks
    h.update(tweaks.fingerprint().encode('utf-8'))
    h.update(('party burden %d, hero life %g, boss %g, damage %g, hero %s, party %g, drops %s' % (
        party_burden(), HERO_LIFE, HERO_BOSS, HERO_DAMAGE, HERO_NAME, PARTY_EXTRA, drop_chances())).encode('utf-8'))
    import souls
    h.update(souls.fingerprint().encode('utf-8'))      # 1.6.0: soul settings and the hero's level
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
    b = Builder(base)
    b.run()
    if '--install' in sys.argv:
        if installer.game_running():
            raise SystemExit('Titan Quest is running - close it first.')
        problems = verify_companions.check(os.path.join(OUT, 'database.arz'), base, log, touched=b.tweak_touched,
                                           gear=b.gear_ledger, souls=b.soul_ledger)
        problems += verify_companions.string_table(os.path.join(OUT, 'database.arz'))
        if problems:
            raise SystemExit('\n'.join(problems) + '\nverify failed - not installed.')
        log('ALL CHECKS PASSED')
        inst.install(os.path.join(OUT, 'database.arz'), text_payload('ru'), text_payload('en'))
