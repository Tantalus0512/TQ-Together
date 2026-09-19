TQ Together 1.0.0
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
  - has your hero's body, colours, worn gear (items and their affixes), level, attributes and skills;
  - uses its skills by itself: auras and buffs on you, attacks, weapon techniques;
  - has the usual pet panel (top left): health and energy, stance (normal / aggressive / defensive), dismiss;
  - follows you, reacts quickly and does not drop its gear.

What is NOT transferred
  - the amulet and the artifact (creatures have no slots for them);
  - relics and charms set into the hero's gear (the items themselves and their affixes are transferred);
  - the inactive weapon set;
  - skills that summon pets of their own; skills that need a weapon the hero is not holding;
  - active skills beyond what the creature AI can use (up to 5 attacks, 4 toggled auras, 3 buffs on allies,
    1 heal); of several exclusive trances only the highest-level one is kept.
  What each companion got and why a skill was left out: build\companions.txt in the data folder.

Deleted heroes
  When you delete a hero, their companion disappears with the next start of TQ Together. Every eidolon and shard
  of that hero - in rings, inventory or stash - becomes a "Faded Eidolon" without any effect, so saves stay valid.


EPIC / LEGENDARY RINGS
----------------------
The game does not allow relics in Epic or Legendary (purple) items. Eidolons follow the same rule.
If you want them in purple rings, use a separate mod that lifts this restriction for all relics
(for example "Enchanting for Epic and Legendary Items" on Nexus). It is not part of TQ Together and not required.


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
