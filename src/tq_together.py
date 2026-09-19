# -*- coding: utf-8 -*-
"""TQ Together - your other characters as companions in Titan Quest Anniversary Edition.

Double-click TQTogether.exe to play: it rebuilds the companions from your current saves (only when something
changed), installs them into the game and starts Titan Quest.
  TQTogether.exe --uninstall   restore the original game files
  TQTogether.exe --rebuild     rebuild even if nothing changed
  TQTogether.exe --no-launch   do not start the game afterwards
"""
import os, sys, json, glob, time, hashlib, traceback, subprocess

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
    try:
        input('\n' + msg)
    except Exception:
        pass


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
                    with open(os.path.join(folder, 'TQTogether.ini'), 'w', encoding='utf-8') as f:
                        f.write('; TQ Together settings\nGamePath=%s\n' % d)
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


def single_instance():
    """exclusive lock on a file in the data folder; None if another TQ Together holds it"""
    import msvcrt
    try:
        f = open(os.path.join(paths.data_dir(), 'tq_together.lock'), 'a+')
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        return f
    except OSError:
        return None


def cleanup_old_cache():
    """1.0 dev builds kept a 365 MB pickle of the whole database - not used any more"""
    for p in glob.glob(os.path.join(paths.data_dir(), 'cache', 'base_*.pickle')):
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
    game = paths.find_game() or ask_game()
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
        pause('Press Enter when the game is closed / Нажмите Enter, когда игра закрыта')

    inst = installer.Installer(game, log)
    if '--uninstall' in args:
        log('\nThis restores the original game files. Eidolons set into items may disappear from them.')
        log('Это вернёт оригинальные файлы игры. Эйдолоны, вставленные в вещи, могут из них пропасть.')
        try:
            ok = input('Type YES to continue / Введите YES для продолжения: ').strip().upper() == 'YES'
        except EOFError:
            ok = False
        if ok:
            inst.uninstall()
            import shutil
            shutil.rmtree(os.path.join(paths.data_dir(), 'cache'), ignore_errors=True)
            shutil.rmtree(os.path.join(paths.data_dir(), 'build'), ignore_errors=True)
            log('Done. TQ Together is removed. / Готово, мод удалён.')
        else:
            log('Cancelled. / Отменено.')
        pause()
        return

    cleanup_old_cache()
    base = inst.prepare()
    fp = fingerprint(base)
    if '--rebuild' not in args and inst.state.get('fingerprint') == fp and inst.installed_intact():
        log('Nothing changed since the last start - companions are up to date. / Изменений нет, соратники актуальны.')
    else:
        log('Building companions from your saves - please do not close this window ...')
        log('Собираю соратников из сохранений - пожалуйста, не закрывайте это окно ...')
        import build_companions as B, verify_companions
        B.LOG = LOG_LINES
        b = B.Builder(base)
        b.run()
        problems = verify_companions.check(b.db.arz.records, base, log)
        if problems:
            log('\n'.join(problems))
            raise SystemExit('Self-check failed - nothing was installed. / Самопроверка не прошла, ничего не установлено.')
        inst.install(os.path.join(B.OUT, 'database.arz'), B.text_payload('ru'), B.text_payload('en'))
        inst.state['fingerprint'] = fingerprint(base)     # the build rewrote the registry
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
