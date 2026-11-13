# -*- coding: utf-8 -*-
"""TQ Together - your other characters as companions in Titan Quest Anniversary Edition.

Double-click TQTogether.exe to play: it rebuilds the companions from your current saves (only when something
changed), installs them into the game and starts Titan Quest.
  TQTogether.exe --uninstall   restore the original game files
  TQTogether.exe --rebuild     rebuild even if nothing changed
  TQTogether.exe --no-launch   do not start the game afterwards
  TQTogether.exe --atelier     new looks for items in the TQVault vault "Ателье" / "Atelier" (atelier.py, 1.9.0)
"""
import os, sys, re, json, glob, time, hashlib, traceback, subprocess

import paths

try:
    if not sys.stdout.isatty():                    # piped output: keep Cyrillic readable
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
LOG_LINES = []


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    LOG_LINES.append(s)


def write_log():
    try:
        with open(os.path.join(paths.data_dir(), 'tq_together.log'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(LOG_LINES) + '\n')
    except Exception:
        pass


def pause(msg='Press Enter to close / Нажмите Enter, чтобы закрыть'):
    """-> False when nobody can answer (no console input)"""
    try:
        input('\n' + msg)
        return True
    except Exception:
        return False


def to_number(v):
    """an ini value as a number: as Python reads it ('.65', '1e3', decimal comma), else the number it starts with
    ('2 ; two players'); None if there is none (1.8.1)"""
    import math
    v = (v or '').strip()
    try:
        x = float(v.replace(',', '.'))
        return x if math.isfinite(x) else None
    except ValueError:
        pass
    m = re.match(r'[-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)', v)
    return float(m.group(0).replace(',', '.')) if m else None


def remember_game(folder, d):
    """GamePath=d in folder's TQTogether.ini. 1.8.1: every other line stays (the file was rewritten with GamePath
    alone, and Difficulty, Life.<hero> and the soul settings were gone)"""
    p = os.path.join(folder, 'TQTogether.ini')
    lines = []
    if os.path.exists(p):
        with open(p, encoding='utf-8-sig', errors='replace') as f:
            lines = f.read().splitlines()
    out, done = [], False
    for line in lines:
        if not line.strip().startswith((';', '#')) and line.split('=', 1)[0].strip().lower() == 'gamepath':
            if not done:
                out.append('GamePath=%s' % d)
                done = True
            continue
        out.append(line)
    if not done:
        out = (out or ['; TQ Together settings']) + ['GamePath=%s' % d]
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    os.replace(tmp, p)


def ask_game():
    log('Titan Quest Anniversary Edition was not found automatically.')
    log('Игра не найдена автоматически.')
    while True:
        try:
            d = input('Paste the game folder (the one with TQ.exe) / Вставьте путь к папке игры (где TQ.exe): ').strip().strip('"')
        except EOFError:
            return None
        if d.lower().endswith('.exe'):
            d = os.path.dirname(d)
        if paths.is_game(d):
            for folder in (paths.app_dir(), paths.data_dir()):
                try:
                    remember_game(folder, d)
                    break
                except OSError:
                    continue
            return d
        log('  no TQ.exe + Database\\database.arz there / там нет TQ.exe и Database\\database.arz')


def fingerprint(base_arz):
    """everything a build depends on: tool version, the base database, every save, the companion registry"""
    h = hashlib.md5(paths.VERSION.encode())
    st = os.stat(base_arz)
    h.update(('%d %d' % (st.st_size, int(st.st_mtime))).encode())
    import build_companions as B
    h.update(B.inputs_fingerprint().encode())
    reg = os.path.join(paths.data_dir(), 'registry.json')
    if os.path.exists(reg):
        h.update(open(reg, 'rb').read())
    return h.hexdigest()


def choose_hero(args, base_arz=None, hero=None):
    """Which hero is about to be played (Enter = the one saved last) and how strong the monsters get. TQTogether.ini:
    Difficulty=party (1.4.0, the default): every companion the hero can summon - a completed eidolon in one of his worn
      rings - counts as CompanionPlayers (default 1) more players, and monsters, champions and bosses get the game's own
      co-op scaling for that party size on every difficulty (Legendary: +50 % life per player, bosses +100 %).
    Difficulty=power (AutoLife=1 in older ini files): Legendary monster life from the party's damage per second:
      x = (dps / AutoLifeBase) ^ AutoLifePower, between 1 and AutoLifeMax, damage x^AutoDamagePower, bosses
      x AutoLifeBoss on top - for heroes geared far beyond the game's own curve. Life.<hero>=<x> sets x by hand.
      1.8.5: dps = hero_power.combat_strength on the database with the tweaks - damage against a typical Legendary
      monster with crits, on-hit buffs and weapon-pool attacks (the character window's number missed those: a hero
      with Battle Rage hits 4.5x his window), AutoLifeBase 960 -> 3200 for that scale.
      1.8.6: the hero's own summons hit x^AutoPetPower (default 1) harder on Legendary and take the monsters' extra
      damage in life and defence - they kill and last as on the game's Legendary (0 = summons as in the game).
    Difficulty=off: vanilla monsters. The question is asked whenever there is more than one hero (his pet bonuses are
    cancelled on the companions, 1.2.0)."""
    import build_companions as B
    st = paths.settings()
    lives = {k[len('life.'):]: v for k, v in st.items() if k.startswith('life.')}

    def num(k, d):
        """1.8.1: the number at the start of the value ('2 ; two players', decimal comma); anything else is the default
        with a note - a stray word stopped TQ Together with a traceback"""
        v = (st.get(k) or '').strip()
        if not v:
            return float(d)
        x = to_number(v)
        if x is None:
            log('  ! TQTogether.ini: %s=%s is not a number - using %g' % (k, v, d))
            return float(d)
        return x
    raw_mode = (st.get('difficulty') or '').strip().lower()
    mode = raw_mode.split(';')[0].split()[0] if raw_mode.split(';')[0].split() else ''
    if mode not in ('party', 'power', 'off'):
        if mode:
            log('  ! TQTogether.ini: Difficulty=%s is not party, power or off' % st.get('difficulty'))
        auto = st.get('autolife', '0').strip().lower().split(';')[0].strip()
        mode = 'power' if auto not in ('', '0', '0.0', 'off', 'false', 'no') or lives else 'party'
    heroes = []
    saves = paths.saves_dir()
    for d in os.listdir(saves) if os.path.isdir(saves) else []:
        p = os.path.join(saves, d, 'Player.chr')
        if d.startswith('_') and os.path.isfile(p):
            heroes.append((os.path.getmtime(p), d[1:], p))
    heroes.sort(reverse=True)
    paths_of = {h: p for _, h, p in heroes}
    heroes = [h for _, h, _ in heroes]
    if not heroes:      # 1.8.1: said, not silent (a wrong Windows account or Documents folder shows up here)
        log('No characters in %s - companions and souls come once you have heroes there.' % saves)
        log('В %s нет персонажей - соратники появятся, когда там будут герои.' % saves)
        return
    _, folders = B.load_registry()
    folder_of = {c: f for f, c in folders.items()}

    def members(h):
        """[(name, save path)] - the hero first, then every companion he can summon (1.1.2)"""
        out = [(h, paths_of[h])]
        try:
            worn = B.parse_equipment(paths_of[h])
        except OSError:
            worn = []
        for it in worn:
            m = re.search(r'companions\\([a-z0-9_]+)_relic\.dbr$', (it.get('relic') or '').lower())
            if not m or not it.get('relic_bonus'):          # only a completed eidolon summons
                continue
            f = folder_of.get(m.group(1))
            p = os.path.join(saves, f, 'Player.chr') if f else ''
            if p and os.path.isfile(p) and f[1:].lower() != h.lower():
                out.append((next((x for x in heroes if x.lower() == f[1:].lower()), f[1:]), p))
        return out

    def souls_of(h):
        """1.6.0: completed boss souls in the hero's worn amulet - each one more companion"""
        try:
            worn = B.parse_equipment(paths_of[h])
        except OSError:
            return 0
        return sum(1 for it in worn for rel, bon in (('relic', 'relic_bonus'), ('relic2', 'relic_bonus2'))
                   if re.search(r'companions\\souls\\[a-z0-9_]+_soul\.dbr$', (it.get(rel) or '').lower()) and it.get(bon))

    per = min(5.0, max(0.0, num('companionplayers', 1.0)))
    extra = lambda h: min(5.0, (len(members(h)) - 1 + souls_of(h)) * per)
    soul_note = lambda h: ' + %d soul / душа' % souls_of(h) if souls_of(h) else ''
    import hero_power as H
    if base_arz:
        H.use_db(base_arz, tweaked=True)        # 1.8.5: the database the game will run
    measured, said = {}, []
    cache = os.path.join(paths.data_dir(), 'cache', 'power.json')

    def fight(p):
        """hero_power.combat_strength (cached) or None"""
        if p not in measured:
            try:
                measured[p] = H.measure(p, cache)
            except Exception as e:                       # a build the calculator does not know: counts as nothing
                log('  (damage of %s not measured: %s / урон не посчитан)' % (os.path.basename(os.path.dirname(p)), e))
                measured[p] = None
            if H.TWEAK_ERROR and not said:
                said.append(1)
                log('  (a tweak does not apply - damage measured without the tweaks / твик не встаёт: %s)' % H.TWEAK_ERROR)
        return measured[p]
    dps = lambda p: fight(p)['dps'] if fight(p) else 0
    if mode == 'power':
        base, power, cap = num('autolifebase', 3200), num('autolifepower', 0.65), num('autolifemax', 50)
        if base <= 0:           # 1.8.1: 0 divided, a negative base gave a complex number
            log('  ! TQTogether.ini: AutoLifeBase must be above 0 - using 3200')
            base = 3200.0

        def life(h):
            try:
                if h.lower() in lives:
                    x = to_number(lives[h.lower()])
                    return max(0.1, x) if x is not None else 1.0
                dmg = sum(dps(p) for _, p in members(h))
                return round(min(cap, max(1.0, (dmg / base) ** power)), 1) if dmg > 0 else 1.0
            except (ValueError, OSError, ZeroDivisionError, OverflowError):
                pass
            return 1.0
        show = lambda h: '%s -> monster life on Legendary x%g / здоровье монстров на Легенде x%g%s' % (
            ' + '.join('%s %.0f' % (n, dps(p)) for n, p in members(h)), life(h), life(h),
            ', вручную' if h.lower() in lives else '')
        note = ('   (numbers = damage per second against a typical Legendary monster: crits, on-hit buffs and weapon-pool '
                'attacks in, spells out\n    урон в секунду по обычному монстру Легенды: с критом, баффами на удар и '
                'приёмами оружия, без заклинаний)')

        def breakdown(n, f):
            """1.8.5: where a hero's number comes from (the log and build\\companions.txt)"""
            if not f:
                return '  %s: not measured / не посчитан' % n
            pct = lambda a, b: '%+.0f%%' % (100.0 * (a / b - 1)) if b > 0 else '-'
            return ('  %s: window / окно %d/s; per hit on a Legendary monster / за удар по монстру Легенды %d (hit / '
                    'попадание %.0f%%, crit / крит x%.2f, on-hit buffs / баффы на удар %s, weapon pool / приёмы %s) x '
                    '%.2f/s = %d/s' % (n, f['window_dps'], f['swing'], 100 * f['hit'], f['crit'],
                                       pct(f['buff_swing'], f['window_swing']), pct(f['swing'], f['buff_swing']),
                                       f['swings'], f['dps']))
    else:
        show = lambda h: '%s%s -> %s' % (' + '.join(n for n, _ in members(h)), soul_note(h),
                                        'vanilla monsters / обычные монстры' if mode == 'off' or extra(h) <= 0 else
                                        'monsters as for %g players / монстры как для %g игроков' % (1 + extra(h), 1 + extra(h)))
        note = None
    forced = hero or next((a.split('=', 1)[1] for a in sys.argv[1:] if a.lower().startswith('--hero=')), None)
    pick = next((h for h in heroes if forced and h.lower() == forced.lower()), None)
    if pick is None and len(heroes) == 1:
        pick = heroes[0]
    if pick is None:
        log('\nWho do you play? / Кем играешь? (Enter = %s)' % heroes[0])
        if note:
            log(note)
        for i, h in enumerate(heroes, 1):
            log('  %d  %s  (%s)' % (i, h, show(h)))
        try:
            ans = input('> ').strip()
        except EOFError:
            ans = ''
        pick = heroes[int(ans) - 1] if ans.isdigit() and 1 <= int(ans) <= len(heroes) else heroes[0]
    B.HERO_NAME = pick
    try:                                       # 1.6.0: boss souls come at the hero's level
        B.HERO_LEVEL = int(B.read_char(paths_of[pick])['level'])
    except Exception:
        B.HERO_LEVEL = 0
    # 1.7.0: ... and hit a share of his damage per second (SoulDamage). 1.8.5: the same measure as the difficulty -
    # on a typical Legendary monster, with the tweaks (was the character window on the clean database); a build the
    # calculator does not know: 0, the souls keep the boss's damage
    B.HERO_DPS = float(dps(paths_of[pick]))
    if mode == 'power':
        B.HERO_LIFE = life(pick)
        team = [(n, fight(p)) for n, p in members(pick)]
        B.HERO_BOSS = max(0.1, num('autolifeboss', 1))
        B.HERO_DAMAGE = round(max(1.0, B.HERO_LIFE) ** max(0.0, num('autodamagepower', 0.3)), 2)
        B.PET_POWER = max(0.0, num('autopetpower', 1.0))     # 1.8.6: the hero's summons keep pace (hero_pets)
        head = 'Hero / Герой: %s (damage per second / урон в секунду: %s), monster life x%g%s, bosses x%g, damage x%g' % (
            pick, ' + '.join('%s %d' % (n, f['dps'] if f else 0) for n, f in team), B.HERO_LIFE,
            ' (Life.%s, by hand / вручную)' % pick if pick.lower() in lives else '', B.HERO_LIFE * B.HERO_BOSS,
            B.HERO_DAMAGE)
        if B.PET_POWER > 0:
            px = round(max(1.0, B.HERO_LIFE) ** B.PET_POWER, 2)
            head += ', pets x%g / питомцы x%g' % (px, px)
        B.DIFFICULTY_NOTE = [head] + [breakdown(n, f) for n, f in team]
        for line in B.DIFFICULTY_NOTE:
            log(line)
        B.PARTY_EXTRA = 0.0
    else:
        B.PARTY_EXTRA = round(extra(pick), 3) if mode == 'party' else 0.0
        B.HERO_LIFE, B.HERO_BOSS, B.HERO_DAMAGE, B.PET_POWER = 1.0, 1.0, 1.0, 0.0
        B.DIFFICULTY_NOTE = ['Hero / Герой: %s' % show(pick)]
        log(B.DIFFICULTY_NOTE[0])


def build_install(inst, base, args, force=False):
    """rebuild (when anything changed, or force) + self-check + install -> True; a failed self-check stops here"""
    fp = fingerprint(base)
    # 1.8.1: texts that failed to go in last time for want of ArchiveTool are tried again once it is there
    texts_ok = not (inst.state.get('texts_no_tool') and os.path.exists(inst.tool))
    if not force and '--rebuild' not in args and inst.state.get('fingerprint') == fp and inst.installed_intact() \
            and texts_ok:
        log('Nothing changed since the last start - companions are up to date. / Изменений нет, соратники актуальны.')
        return True
    log('Building companions from your saves - please do not close this window ...')
    log('Собираю соратников из сохранений - пожалуйста, не закрывайте это окно ...')
    import build_companions as B, verify_companions
    B.LOG = LOG_LINES
    b = B.Builder(base)
    b.run()
    problems = verify_companions.check(b.db.arz.records, base, log, touched=b.tweak_touched, gear=b.gear_ledger,
                                       souls=b.soul_ledger)
    problems += verify_companions.string_table(os.path.join(B.OUT, 'database.arz'))
    if problems:
        log('\n'.join(problems))
        raise SystemExit('Self-check failed - nothing was installed. / Самопроверка не прошла, ничего не установлено.')
    inst.install(os.path.join(B.OUT, 'database.arz'), B.text_payload('ru'), B.text_payload('en'))
    inst.state['fingerprint'] = fingerprint(base)     # the build rewrote the registry
    inst.state['hero'] = B.HERO_NAME                  # 1.9.0: the atelier rebuilds for the same hero
    inst.save_state()
    if paths.frozen():                                 # the copy in the game folder is what counts
        try:
            os.remove(os.path.join(B.OUT, 'database.arz'))
        except OSError:
            pass
    names = [r[0] for r in b.report]
    log('Companions / Соратники: %s' % (', '.join(names) if names else
        'none yet (a character needs level 20 and a mastery) / пока нет (нужен 20-й уровень и мастерство)'))
    log('Report / Отчёт: %s' % os.path.join(B.OUT, 'companions.txt'))
    return True


def single_instance():
    """exclusive lock on a file in the data folder; None if another TQ Together holds it"""
    import msvcrt
    try:
        f = open(os.path.join(paths.data_dir(), 'tq_together.lock'), 'a+')
    except OSError as e:        # 1.8.1: not "already running" - the data folder is not writable
        raise SystemExit('Cannot write into %s (%s).\nНет доступа на запись в эту папку (антивирус, OneDrive, права).'
                         % (paths.data_dir(), e))
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        return f
    except OSError:
        f.close()
        return None


def cleanup_old_cache():
    """1.0 dev builds kept a 365 MB pickle of the whole database - not used any more"""
    for p in glob.glob(os.path.join(glob.escape(paths.data_dir()), 'cache', 'base_*.pickle')):
        try:
            os.remove(p)
        except OSError:
            pass


def launch(game):
    if paths.is_steam(game):
        log('Starting Titan Quest through Steam ... / Запускаю Titan Quest через Steam ...')
        os.startfile('steam://rungameid/%s' % paths.STEAM_APPID)
    else:
        log('Starting Titan Quest ... / Запускаю Titan Quest ...')
        subprocess.Popen([os.path.join(game, 'TQ.exe')], cwd=game)


def main():
    args = set(a.lower() for a in sys.argv[1:])
    log('%s %s' % (paths.APP, paths.VERSION))
    game = paths.find_game()
    if game and paths.STALE_GAMEPATH:       # 1.8.1: the search found it - the ini gets the new path, once
        for folder in (paths.app_dir(), paths.data_dir()):
            p = os.path.join(folder, 'TQTogether.ini')
            try:
                if os.path.exists(p) and re.search(r'(?im)^\s*gamepath\s*=', open(p, encoding='utf-8-sig',
                                                                                   errors='replace').read()):
                    remember_game(folder, game)
            except OSError:
                pass
        log('  TQTogether.ini: GamePath=%s held no game - now %s / путь к игре в ini обновлён' % (
            paths.STALE_GAMEPATH, game))
    game = game or ask_game()
    if not game:
        raise SystemExit('Game folder not set / Папка игры не задана.')
    if not paths.has_dlc(game):
        raise SystemExit('The Eternal Embers DLC is required (Resources\\XPack4 not found in %s).\n'
                         'Нужно дополнение Eternal Embers (в папке игры нет Resources\\XPack4).' % game)
    log('Game / Игра:   %s' % game)
    log('Saves / Сейвы: %s' % paths.saves_dir())

    lock = single_instance()
    if lock is None:
        raise SystemExit('TQ Together is already running in another window. / TQ Together уже запущен в другом окне.')
    import installer
    while installer.game_running():
        log('Titan Quest is running - close it first. / Titan Quest запущен - закройте его.')
        if not pause('Press Enter when the game is closed / Нажмите Enter, когда игра закрыта'):
            raise SystemExit('Close Titan Quest and start TQ Together again. / Закройте игру и запустите TQ Together снова.')

    inst = installer.Installer(game, log)
    if '--uninstall' in args:
        log('\nThis restores the original game files. Eidolons set into items may disappear from them.')
        log('Это вернёт оригинальные файлы игры. Эйдолоны, вставленные в вещи, могут из них пропасть.')
        looks, unchecked = {}, None
        try:                                    # 1.9.0: items with a new look live on our records
            import transmog
            looks = transmog.referenced()
        except Exception as e:                  # 1.9.1: said, and a separate confirmation (was swallowed)
            unchecked = e
        if unchecked is not None:
            log('\nCould not check the saves and TQVault vaults for items from the Atelier (%s). Items with a new look '
                'would DISAPPEAR without TQ Together.' % unchecked)
            log('Не удалось проверить сохранения и хранилища TQVault на вещи из «Ателье» (%s). Вещи с новым обликом '
                'без TQ Together ПРОПАДУТ.' % unchecked)
        if looks:
            log('\n%d item record(s) with a new look (Atelier) are still in use, e.g. in %s. Without TQ Together these '
                'items DISAPPEAR. First put them into the last bag of the vault "Ателье" in TQVault and run Atelier.bat '
                '- they get their own look back.' % (len(looks), next(iter(looks.values()))))
            log('Вещи с новым обликом из ателье (%d) ещё лежат у героев или в хранилищах. Без TQ Together они ПРОПАДУТ. '
                'Сначала положите их в последнюю сумку хранилища «Ателье» в TQVault и запустите Atelier.bat - им '
                'вернётся родной облик.' % len(looks))
        word = 'YES' if unchecked is None else 'YES, NO CHECK'
        try:
            ok = input('Type %s to continue / Введите %s для продолжения: ' % (word, word)).strip().upper() == word
        except EOFError:
            ok = False
        if ok:
            left = inst.uninstall()
            import shutil
            shutil.rmtree(os.path.join(paths.data_dir(), 'cache'), ignore_errors=True)
            shutil.rmtree(os.path.join(paths.data_dir(), 'build'), ignore_errors=True)
            if left:            # 1.8.1: no saved original to put back - not "removed"
                log('These game files still hold TQ Together and their saved originals are gone: %s' % ', '.join(left))
                log('Restore them: Steam - Properties > Installed Files > Verify integrity; GOG Galaxy - Verify / Repair.')
                log('В этих файлах игры остался мод, а сохранённых оригиналов нет: %s.' % ', '.join(left))
                log('Верните их проверкой целостности файлов в Steam (или GOG Galaxy).')
            else:
                log('Done. TQ Together is removed. / Готово, мод удалён.')
        else:
            log('Cancelled. / Отменено.')
        pause()
        return

    cleanup_old_cache()
    base = inst.prepare()
    if '--atelier' in args:              # 1.9.0: new looks for items in the TQVault vault "Ателье" (atelier.py)
        import atelier

        def build():
            choose_hero(args, base, hero=inst.state.get('hero'))     # the hero of the last build: same difficulty
            return build_install(inst, base, args, force=True)
        atelier.run(game, inst, build, log, pause)
        write_log()
        pause()
        return
    choose_hero(args, base)
    build_install(inst, base, args)
    if '--no-launch' not in args:
        launch(game)
        write_log()
        time.sleep(4)


if __name__ == '__main__':
    try:
        main()
        write_log()
    except SystemExit as e:
        if e.code not in (None, 0):
            log(str(e.code))
            write_log()
            pause()
        sys.exit(0 if e.code in (None, 0) else 1)
    except Exception:
        log(traceback.format_exc())
        log('Something went wrong. The log is in / Что-то пошло не так. Лог: %s' %
            os.path.join(paths.data_dir(), 'tq_together.log'))
        write_log()
        pause()
        sys.exit(1)
