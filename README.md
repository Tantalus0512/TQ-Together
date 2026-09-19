TQ Together 1.0.0
Твои герои — соратники в Titan Quest Anniversary Edition
========================================================

Любой герой из твоих сохранений может сражаться рядом с другими твоими героями. Это не застывшая копия: при каждом
запуске игры через TQ Together соратник пересобирается из ТЕКУЩЕГО сохранения этого героя — уровень,
характеристики, мастерства и умения, надетые вещи с их свойствами. Качаешь того героя в его собственной игре —
растёт и соратник.


ТРЕБОВАНИЯ
----------
- Windows, Titan Quest Anniversary Edition (Steam или GOG) с дополнениями Ragnarok, Atlantis и Eternal Embers.
- Основная кампания, одиночная игра. «Своя игра» (Custom Game) и мультиплеер не поддерживаются.
- Хотя бы один герой 20-го уровня или выше с выбранным мастерством. Соратники делаются из ВСЕХ таких героев,
  включая того, за кого ты играешь (да, можно встретить самого себя).


УСТАНОВКА И ЗАПУСК
------------------
1. Распакуй архив куда угодно (например, на Рабочий стол).
2. Закрой игру и запусти TQTogether.exe. Он сам найдёт игру (Steam, GOG — или один раз спросит папку с TQ.exe),
  соберёт соратников и запустит Titan Quest.
3. Дальше запускай игру через TQTogether.exe. При каждом запуске проверяются сохранения: если любой герой получил
  уровень, очки умений или характеристик или сменил надетые вещи (или герой появился/удалён, или игра обновилась),
  соратники пересобираются — несколько секунд, при самом первом запуске до минуты. Иначе игра стартует сразу.
  Пожалуйста, не закрывай окно, пока оно работает.
  Запуск игры напрямую из Steam/GOG тоже работает — с соратниками прошлой сборки.
  Исключение: после обновления игры или «Проверки целостности» мод выключен до следующего запуска TQTogether.exe —
  не загружай героя с эйдолонами в кольцах, пока не запустишь его.


КАК ЭТО РАБОТАЕТ В ИГРЕ
-----------------------
Эйдолон: [имя героя]
  Реликвия из двух осколков. Соедини два осколка одного героя (перетащи один на другой или на кольцо, где уже
  вставлен первый) — собранный эйдолон даёт умение «Призвать соратника: [имя героя]».
  Эйдолоны вставляются ТОЛЬКО в кольца, поэтому соратников одновременно не больше двух.

Где взять
  Легендарные электрумные сферы у торговца электрумом (Eternal Embers): 10% на сферу получить один осколок.
  Осколок принадлежит случайному из твоих героев 20+ уровня (все равновероятны, включая текущего). Чем больше таких
  героев, тем больше сфер нужно, чтобы собрать два осколка конкретного героя.
  Остальное содержимое сфер не меняется — у всех прочих предметов прежний шанс.
  Обычные и эпические сферы, боссы и торговцы эйдолонов не дают.

Соратник
  - выглядит как твой герой: тело, цвет, надетые вещи (сами вещи и их свойства); у него те же уровень,
    характеристики и умения;
  - сам применяет умения: ауры и баффы на тебя, атаки, приёмы с оружием;
  - есть обычная панель питомца (слева вверху): здоровье и энергия, стиль боя (обычный / агрессивный /
    оборонительный), отзыв;
  - держится рядом, быстро вступает в бой и не роняет свои вещи.

Что НЕ переносится
  - амулет и артефакт (у существ нет таких слотов);
  - реликвии и талисманы, вставленные в вещи героя (сами вещи и их свойства переносятся);
  - неактивный набор оружия;
  - умения, которые сами призывают питомцев; умения под оружие, которого у героя нет в руках;
  - активные умения сверх того, что тянет ИИ существа (до 5 атак, 4 ауры, 3 баффа союзникам, 1 лечение);
    из нескольких взаимоисключающих трансов остаётся один, самого высокого уровня.
  Что получил каждый соратник и почему часть умений не взята — build\companions.txt в папке данных.

Удалённые герои
  Если удалить героя, его соратник пропадёт при следующем запуске TQ Together. Все эйдолоны и осколки этого героя —
  в кольцах, инвентаре или тайнике — станут «Угасшим эйдолоном» без эффекта, сохранения не ломаются.


ФИОЛЕТОВЫЕ КОЛЬЦА
-----------------
Игра не разрешает вставлять реликвии в эпические и легендарные (фиолетовые) вещи, эйдолоны подчиняются тому же
правилу. Если хочешь вставлять их в фиолетовые кольца — поставь отдельный мод, снимающий это ограничение для
всех реликвий (например, «Enchanting for Epic and Legendary Items» на Nexus). В TQ Together он не входит и не нужен.


УДАЛЕНИЕ
--------
Запусти «Uninstall TQ Together.bat» (или TQTogether.exe --uninstall) и введи YES — вернутся оригинальные файлы игры
(файл, который игра обновила уже после установки мода, останется как есть). Сначала сделай копию сохранений: что
игра сделает с эйдолонами, вставленными в вещи, после удаления мода, не проверялось.


ФАЙЛЫ
-----
- Изменяемые файлы игры: Database\database.arz и Text\Text_*.arc. Оригиналы лежат рядом как *.tqtogether-base,
  каждая сборка начинается с них. Если обновление игры или «Проверка целостности» заменит файл, TQ Together это
  заметит и возьмёт новый файл за основу.
- Папка данных (несколько МБ): Документы\My Games\Titan Quest - Immortal Throne\TQ Together
  (build\companions.txt — что получил каждый соратник; tq_together.log — журнал последнего запуска;
  registry.json — герои, которых знает TQ Together, чтобы эйдолоны удалённых героев угасали, а не ломались).
- TQTogether.ini (необязательно, рядом с exe): GamePath=D:\Games\Titan Quest Anniversary Edition
- Названия предметов и умений — на русском для русской игры и на английском для всех остальных языков.


ЕСЛИ ЧТО-ТО НЕ ТАК
------------------
- «No permission to write into the game folder» — запусти TQTogether.exe от имени администратора.
- Игра не найдена — TQ Together один раз спросит папку с TQ.exe и запомнит её в TQTogether.ini.
- «Нужно дополнение Eternal Embers» — в папке игры нет Resources\XPack4, установи дополнение.
- «TQ Together уже запущен» — ещё работает другое его окно, дождись его или закрой.
- Вместо названий видно tagTQComp_... — в папке игры нет ArchiveTool.exe или он сработал с ошибкой,
  смотри tq_together.log.
- Антивирус ругается — программа упакована PyInstaller, на такие программы антивирусы иногда ошибочно реагируют.
  Полный исходный код лежит в папке src.
- Другое — пришли файл tq_together.log из папки данных.

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

Nexusmods page: https://www.nexusmods.com/titanquestanniversaryedition/mods/127
