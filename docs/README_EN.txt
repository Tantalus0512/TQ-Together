TQ Together 1.0.2
Your heroes as companions - Titan Quest Anniversary Edition
===========================================================

Every hero in your saves can fight at the side of your other heroes. Not a copy frozen in time: each time you start
the game through TQ Together, the companion is rebuilt from that hero's CURRENT save - level, attributes, masteries
and skills, worn gear with its affixes. Level up that hero in its own playthrough and the companion grows with it.


REQUIREMENTS
------------
- Windows, Titan Quest Anniversary Edition (Steam or GOG) with the Ragnarok, Atlantis and Eternal Embers DLC.
- The main campaign in single player. Custom Game mods and multiplayer are not supported.
- At least one hero of level 20 or higher with a mastery chosen. Companions are made from ALL such heroes,
  including the one you are playing (so yes, you can meet yourself).


INSTALL AND PLAY
----------------
1. Unpack the archive anywhere (for example to your Desktop).
2. Close the game and run TQTogether.exe. It finds the game (Steam, GOG, or asks once for the folder with TQ.exe),
   builds your companions and starts Titan Quest.
3. From now on, start the game with TQTogether.exe. Every start checks your saves: if any hero gained a level,
   skill or attribute points or changed worn gear (or a hero was added or deleted, or the game was updated),
   the companions are rebuilt - a few seconds, up to a minute on the very first start. Otherwise the game starts
   right away. Please do not close the window while it works.
   Starting the game directly from Steam/GOG also works, with the companions of the last build.
   Exception: after a game update or "Verify integrity" the mod is switched off until you run TQTogether.exe
   again - do not load a hero who has eidolons in rings before that.


HOW IT WORKS IN THE GAME
------------------------
Eidolon: [hero name]
  A relic in two shards. Join two shards of the same hero (drag one onto the other, or onto a ring that already
  holds one) - the completed eidolon grants the skill "Summon Companion: [hero name]".
  Eidolons fit RINGS only, so you can have at most two companions at a time.

Where to get them
  Legendary electrum orbs from the electrum merchant (Eternal Embers): 10% per orb to get one shard. The shard
  belongs to a random one of your level-20+ heroes (all equally likely, the one you play included). The more such
  heroes you have, the more orbs it takes to collect two shards of one particular hero.
  Nothing else in the orbs changes - every other item keeps exactly its original chance.
  Normal and Epic orbs, bosses and merchants do not give eidolons.

The companion
  - has your hero's body, colours, worn gear, level, attributes and skills;
  - gets everything the worn gear gives: items with their affixes (purple ones too), relics and charms set into
    them with their completion bonuses, and the amulet and the artifact. Creatures have no amulet or artifact
    slot, so those are sewn into the companion's other items; what went where is in build\companions.txt;
  - skills that items cast by themselves (a buff when hit, an area effect when struck, a heal at low health)
    become the companion's own skills: the game never runs such item skills on creatures. "On attack" item skills
    and the like cannot be moved this way - the report lists them;
  - strikes, casts and runs as fast as your hero: the hero's base speed, and attack, cast and run speed bonuses
    held to the caps the game puts on a hero (350%, 300% and 166%). Buffs from items (such as Artemis' Battle
    Dance) work, but their speed bonus also stops at the hero's cap;
  - uses its skills by itself: auras and buffs on you, attacks, weapon techniques;
  - has the usual pet panel (top left): health and energy, stance (normal / aggressive / defensive), dismiss;
  - follows you, reacts quickly and does not drop its gear.

What is NOT transferred
  - eidolons in the hero's gear (a companion does not call other companions);
  - the exact roll of an affix: prefixes and suffixes come at their nominal value, not the item's random spread;
  - the inactive weapon set;
  - skills that summon pets of their own; skills that need a weapon the hero is not holding;
  - auras, buffs and heals beyond what the creature AI can use (4 toggled auras, 3 buffs on allies, 1 heal); of
    several exclusive trances only the highest-level one is kept. Attacks beyond the five the AI casts itself are
    not lost: the sixth follows the rarest of the five (a chain, with its animation), the rest are cast
    automatically as the companion hits, with a chance set by the skill's cooldown (no wind-up animation);
  - Taunt: enemies should fight you, not be pulled off onto the companion.
  What each companion got and why a skill was left out: build\companions.txt in the data folder.

Deleted heroes
  When you delete a hero, their companion disappears with the next start of TQ Together. Every eidolon and shard
  of that hero - in rings, inventory or stash - becomes a "Faded Eidolon" without any effect, so saves stay valid.
  Once no item anywhere refers to a deleted hero any more, their leftovers are removed completely (1.0.1+).
  Checked: every save (and its Backup folder), the transfer stash (and mod stashes), archived heroes,
  "Titan Quest Backup" and TQVault vaults. Found anywhere means kept.
  More places: ScanPaths=folder1;folder2 in TQTogether.ini.


EPIC / LEGENDARY RINGS
----------------------
The game does not allow relics in Epic or Legendary (purple) items. Eidolons follow the same rule.
If you want them in purple rings, use a separate mod that lifts this restriction for all relics
(for example "Enchanting for Epic and Legendary Items" on Nexus). It is not part of TQ Together and not required.


DATABASE TWEAKS (for your own changes)
--------------------------------------
TQ Together rebuilds database.arz from a clean copy on every start, so changes made on top of it
would be lost. Put your own changes as *.json files into
  Documents\My Games\Titan Quest - Immortal Throne\TQ Together\tweaks
They are applied to the clean database before the companions. The format is data only: "clone" (a new
record copied from an existing one), "set" (a field with type int/real/string/bool), "del" (remove a
field). The self-check compares field types with the original game and checks every record reference;
if anything is wrong, nothing is installed. A changed file triggers a rebuild on the next start.


UNINSTALL
---------
Run "Uninstall TQ Together.bat" (or TQTogether.exe --uninstall) and type YES. The original game files are restored
(a file the game updated after the mod was installed is left as it is). Back up your saves first: what the game
does with eidolons set into items once the mod is gone has not been tested.


FILES
-----
- Changed game files: Database\database.arz and Text\Text_*.arc. The originals are kept next to them as
  *.tqtogether-base and every build starts from them. If a game update or "Verify integrity" replaces a file,
  TQ Together notices it and uses the new file as its base.
- Data folder (a few MB): Documents\My Games\Titan Quest - Immortal Throne\TQ Together
  (build\companions.txt = what each companion got; tq_together.log = log of the last start; registry.json = the
  heroes TQ Together knows, so eidolons of deleted heroes can fade instead of breaking).
- TQTogether.ini (optional, next to the exe): GamePath=D:\Games\Titan Quest Anniversary Edition
- Difficulty (Difficulty= in TQTogether.ini) - three modes:
  * Difficulty=party (default): every companion the hero can summon (a completed eidolon in one of his worn
    rings) counts as one more player. Monsters, champions and bosses get the game's own co-op scaling for that
    party size, on Normal, Epic and Legendary. On Legendary, for example, every companion gives monsters +50% life
    (bosses +100%), and monster damage grows by 17% for the second player, a little more after that.
    CompanionPlayers=1 - how many players one companion counts as: 1.5 or 2 = harder, 0.5 = easier
    (6 players at most).
  * Difficulty=power: for heroes geared far above the usual curve (items from editors and the like). Legendary
    monster life follows the party's strength - the hero's "damage per second" as in the character window (average
    attack damage x attack speed, read from the save at every start; spells are not included) plus that of the
    companions in his rings: (sum / AutoLifeBase) ^ AutoLifePower, from x1 to AutoLifeMax (defaults 960, 0.65, 50).
    10x the damage -> 4.5x the life, you still kill twice as fast. AutoLifeBoss=2 - bosses twice as tough again.
    AutoDamagePower=0.3 - monster damage and accuracy follow the life factor, slower. Life.<hero name>=10 sets the
    factor by hand. Older settings with AutoLife=1 keep working as before.
  * Difficulty=off: vanilla monsters.
  With more than one hero TQ Together asks at start who you are about to play (Enter = the hero saved last).
  The game reads its database once at start, so after switching heroes or the eidolons in your rings start the
  game through TQTogether.exe again.
- PartyBurden=35 in TQTogether.ini: every summoned companion carries the aura "Burden of Nemesis" - the whole
  party deals 35% less damage (two companions: 70%). Default 0 (off).
- Item and skill names are in Russian for a Russian game and in English for every other language.


TROUBLESHOOTING
---------------
- "No permission to write into the game folder": run TQTogether.exe as administrator.
- The game was not found: TQ Together asks once for the folder with TQ.exe and remembers it in TQTogether.ini.
- "The Eternal Embers DLC is required": the game folder has no Resources\XPack4 - install the DLC.
- "TQ Together is already running": another window of it is still working - wait for it or close it.
- Names show as tagTQComp_...: ArchiveTool.exe is missing from the game folder or failed - see tq_together.log.
- Antivirus warning: the program is packed with PyInstaller, which some antiviruses flag by mistake.
  The full source code is in the src folder.
- Something else: send the file tq_together.log from the data folder.
