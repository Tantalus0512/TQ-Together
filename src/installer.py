# -*- coding: utf-8 -*-
"""Game files we replace: Database\\database.arz and every Text\\Text_XX.arc.
  - the first run keeps an untouched copy next to each file (<file>.tqtogether-base) and every build starts from it;
  - if the game (an update, "verify files", another mod) replaced a file since our last install, the new file
    becomes the base - so an update never gets silently reverted;
  - a base that already contains our records is refused: we would build on top of ourselves.
State (md5 of what we installed) lives in Documents\\My Games\\Titan Quest - Immortal Throne\\TQ Together."""
import os, sys, json, glob, shutil, hashlib, subprocess
import paths

NS_BYTES = b'tqmod\\companions\\'     # our record names inside database.arz (string table is not compressed)
DEV_SUFFIX = '.tqmod-backup'           # backups of the author's development builds - only ever used once, as a base
TEXT_HOST = 'commonequipment.txt'      # text file inside Text_XX.arc that the engine always loads
TEXT_MARK = '// ---- TQ Together ----'
OUR_TEXT_MARKS = (TEXT_MARK, '// ---- TQMod tags ----')   # the second one: the author's development builds


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def fsync_file(p):
    with open(p, 'rb+') as f:
        f.flush()
        os.fsync(f.fileno())


def safe_copy(src, dst):
    """copy next to the target, then swap in one step: a full disk or a crash never leaves a half-written game file.
    1.9.1: the copy is flushed to disk before the swap and read back after it; a mismatch puts the old file back"""
    tmp = dst + '.tqtogether-tmp'
    old = dst + '.tqtogether-old'
    if os.path.exists(old):                  # left by a crash between the two swaps below
        if os.path.exists(dst):
            os.remove(old)
        else:
            os.replace(old, dst)
    want = md5(src)
    try:
        shutil.copy2(src, tmp)
        fsync_file(tmp)
        had = os.path.exists(dst)
        if had:
            os.replace(dst, old)
        try:
            os.replace(tmp, dst)
            ok = md5(dst) == want
        except PermissionError:              # no write access: said as such by the callers
            if had:
                os.replace(old, dst)
            raise
        except OSError:
            ok = False
        if not ok:
            if had:
                os.replace(old, dst)
            elif os.path.exists(dst):
                os.remove(dst)
            raise OSError('%s: the copy read back differs from %s - the previous file is kept' % (dst, src))
        if had:
            os.remove(old)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


SAFETY_KEEP = 10


def backup_saves(log, why):
    """1.9.1: insurance before every install, uninstall and atelier write - the heroes (SaveData\\Main\\_*\\Player.chr)
    and the transfer stash (SaveData\\Sys\\winsys.dx?) into <data>\\safety\\<time> <why>\\, only when their content
    changed since the last copy (md5), the last SAFETY_KEEP copies kept. If the game ever runs on a clean
    database.arz (Steam verify/update, started past TQ Together), items on our records vanish from these files.
    -> the new folder, or None when nothing changed. Raises SystemExit when the copy cannot be made."""
    main = paths.saves_dir()
    sysd = os.path.join(os.path.dirname(main), 'Sys')
    files = sorted(glob.glob(os.path.join(glob.escape(main), '_*', 'Player.chr'))) + \
        sorted(glob.glob(os.path.join(glob.escape(sysd), 'winsys.dx?')))
    if not files:
        return None
    root = os.path.join(paths.data_dir(), 'safety')
    rel = lambda p: os.path.relpath(p, os.path.dirname(main))
    try:
        sums = {rel(p): md5(p) for p in files}
        olds = sorted(d for d in (os.listdir(root) if os.path.isdir(root) else [])
                      if os.path.isfile(os.path.join(root, d, 'manifest.json')))
        if olds:
            try:
                with open(os.path.join(root, olds[-1], 'manifest.json'), encoding='utf-8') as f:
                    if json.load(f).get('files') == sums:
                        return None
            except (OSError, ValueError):
                pass
        import time
        dst = os.path.join(root, '%s %s' % (time.strftime('%Y%m%d_%H%M%S'), why))
        try:
            for p in files:
                q = os.path.join(dst, rel(p))
                os.makedirs(os.path.dirname(q), exist_ok=True)
                shutil.copy2(p, q)
                if md5(q) != sums[rel(p)]:
                    raise OSError('%s: the copy differs' % q)
            with open(os.path.join(dst, 'manifest.json'), 'w', encoding='utf-8') as f:     # last: marks it whole
                json.dump({'why': why, 'files': sums}, f, ensure_ascii=False, indent=1)
        except OSError:
            shutil.rmtree(dst, ignore_errors=True)
            raise
        olds.append(os.path.basename(dst))
        keep = set(sorted(olds)[-SAFETY_KEEP:])
        for d in os.listdir(root):          # older copies, and any half-made one left by a crash
            if d not in keep and os.path.isdir(os.path.join(root, d)):
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)
    except OSError as e:
        raise SystemExit('Could not back up the saves before changing anything (%s) - nothing was changed.\n'
                         'Не удалось сделать страховочную копию сохранений - ничего не изменено.' % e)
    log('  saves backed up / копия сохранений: %s' % dst)
    return dst


def no_write_access(game):
    return ('No permission to write into the game folder:\n  %s\n'
            'Run TQTogether.exe as administrator (right click > Run as administrator).\n'
            'Нет прав на запись в папку игры - запустите TQTogether.exe от имени администратора.' % game)


def is_arc(f):
    """a text/resource archive (by its magic) - the ONLY kind of file ArchiveTool may ever be given: on anything
    else it silently writes an empty 2048-byte archive over it"""
    try:
        with open(f, 'rb') as h:
            return h.read(3) == b'ARC'
    except Exception:
        return False


def arc_intact(f):
    """1.8.1: the archive's table of contents lies inside the file (a cut-off copy fails; the magic and the size alone
    passed a half-written archive)"""
    try:
        import struct
        size = os.path.getsize(f)
        with open(f, 'rb') as h:
            magic, ver, nfiles, nparts, parts_sz, names_sz, toc_off = struct.unpack('<4s6I', h.read(28))
        return magic == b'ARC\x00' and nfiles > 0 and 28 <= toc_off and \
            toc_off + parts_sz + names_sz + nfiles * 44 <= size
    except Exception:
        return False


def valid_file(f):
    """a half-written copy must never become the base"""
    if is_arc(f):
        return os.path.getsize(f) > 4096 and arc_intact(f)
    from arz_lazy import valid_arz
    return valid_arz(f)


def short_path(p):
    """ArchiveTool cannot open paths outside the ANSI code page (e.g. a Greek/CJK user name): use the 8.3 name"""
    try:
        p.encode('mbcs', 'strict')
        return p
    except Exception:
        pass
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024):
            return buf.value
    except Exception:
        pass
    return p


def has_our_records(arz):
    with open(arz, 'rb') as f:
        return NS_BYTES in f.read().lower()


class Installer(object):
    def __init__(self, game, log=print):
        self.game, self.log = game, log
        # one state per game folder: a Steam and a GOG copy on the same PC never mix their md5s
        tag = hashlib.md5(os.path.normcase(os.path.normpath(game)).encode('utf-8')).hexdigest()[:8]
        self.state_path = os.path.join(paths.data_dir(), 'install_state_%s.json' % tag)
        self.state = self._load_state()
        self.arz = os.path.join(game, 'Database', 'database.arz')
        self.texts = sorted(glob.glob(os.path.join(glob.escape(game), 'Text', 'Text_*.arc')))   # 1.8.1: "... [GOG]"
        self.tool = os.path.join(game, 'ArchiveTool.exe')

    def _load_state(self):
        """1.8.1: an unreadable state (cut off by a crash) is a lost state - every game file is judged by its content
        then (test_lifecycle step 4) - instead of stopping every start and the uninstall with a traceback"""
        if not os.path.exists(self.state_path):
            return {}
        try:
            with open(self.state_path, encoding='utf-8') as f:
                s = json.load(f)
            if isinstance(s, dict):
                return s
        except (ValueError, OSError):
            pass
        self.log('  ! %s was unreadable - starting from the game files themselves' % os.path.basename(self.state_path))
        return {}

    def save_state(self):
        tmp = self.state_path + '.tmp'          # 1.8.1: written aside, then swapped in one step
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=1)
        os.replace(tmp, self.state_path)

    def files(self):
        return [self.arz] + self.texts

    def base(self, f):
        return f + paths.BASE_SUFFIX

    # ------------------------------------------------------------------ ownership (by content, not by state)
    def _extract_host(self, arc, work):
        if not is_arc(arc):
            return None, None
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        self._run([short_path(self.tool), short_path(arc), '-extract', short_path(work), TEXT_HOST])
        host = os.path.join(work, TEXT_HOST)
        if not os.path.exists(host):
            return None, None
        raw = open(host, 'rb').read()
        return host, (raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8', 'replace'))

    def ours(self, f):
        """does this game file contain anything of ours?"""
        if not is_arc(f):
            return has_our_records(f)
        if not os.path.exists(self.tool):
            return False
        work = os.path.join(paths.data_dir(), 'text_check')
        try:
            host, text = self._extract_host(f, work)
            return bool(text) and any(m in text for m in OUR_TEXT_MARKS)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def clean_text_copy(self, arc, dst):
        """dst = arc with our text block removed (for a base that got our tags by mistake)"""
        work = os.path.join(paths.data_dir(), 'text_check')
        try:
            host, text = self._extract_host(arc, work)
            cut = min([text.find(m) for m in OUR_TEXT_MARKS if m in text] or [-1])
            if host is None or cut < 0:
                return False
            with open(host, 'wb') as f:
                f.write(b'\xff\xfe' + (text[:cut].rstrip('\r\n') + '\r\n').encode('utf-16-le'))
            tmp = dst + '.tqtogether-tmp'
            shutil.copy2(arc, tmp)
            if not is_arc(tmp):
                os.remove(tmp)
                return False
            self._run([short_path(self.tool), short_path(tmp), '-replace', TEXT_HOST, '.', '9'], cwd=short_path(work))
            os.replace(tmp, dst)
            return True
        finally:
            shutil.rmtree(work, ignore_errors=True)

    # ------------------------------------------------------------------ bases
    def prepare(self):
        """make sure every managed file has an untouched base; -> base database.arz"""
        inst = self.state.get('installed', {})
        clean = self.state.setdefault('clean_bases', {})
        for f in self.files():
            b = self.base(f)
            name = os.path.basename(f)
            try:
                if not os.path.exists(b):
                    dev = f + DEV_SUFFIX
                    safe_copy(dev if os.path.exists(dev) else f, b)
                    self.log('  saved the original %s' % name)
                elif os.path.exists(f):
                    cur = md5(f)
                    if cur != inst.get(name) and cur != md5(b) and valid_file(f) and not self.ours(f):
                        safe_copy(f, b)          # the game (an update, Verify) or another mod replaced it
                        self.log('  %s was updated by the game or another mod - using it as the new base' % name)
                    elif cur != inst.get(name) and cur != md5(b) and not valid_file(f):
                        self.log('  ! %s looks damaged - keeping the saved original' % name)
                # the base itself must be clean; checked once per base version
                mb = md5(b)
                # 1.8.1: an archive is judged clean only when ArchiveTool can look inside (without it ours() says no)
                if clean.get(name) != mb and (not is_arc(b) or os.path.exists(self.tool)):
                    if self.ours(b):
                        self._heal_base(f, b, name)
                        mb = md5(b)
                    clean[name] = mb
            except PermissionError:
                raise SystemExit(no_write_access(self.game))
        self.save_state()
        return self.base(self.arz)

    def _heal_base(self, f, b, name):
        dev = f + DEV_SUFFIX
        if os.path.exists(dev) and not self.ours(dev):
            safe_copy(dev, b)
            self.log('  %s: the saved original contained TQ Together data - restored it from %s' % (name, dev))
        elif not is_arc(b):
            raise SystemExit(
                'The saved original database.arz contains TQ Together records.\n'
                'Restore the original game files (Steam: Properties > Installed Files > Verify integrity;\n'
                'GOG Galaxy: Manage installation > Verify / Repair) and run TQ Together again.')
        elif self.clean_text_copy(b, b):
            self.log('  %s: removed TQ Together texts from the saved original' % name)
        else:
            self.log('  ! %s: the saved original contains TQ Together texts and could not be cleaned' % name)

    def check_base(self, f):
        """1.9.1: a saved original about to go over a game file must be whole and the one prepare() checked"""
        b = self.base(f)
        name = os.path.basename(f)
        rec = self.state.get('clean_bases', {}).get(name)
        if not valid_file(b) or (rec and md5(b) != rec):
            raise SystemExit(
                'The saved original %s is damaged - nothing was changed.\n'
                'Steam: Properties > Installed Files > Verify integrity of game files (GOG Galaxy: Verify / Repair), '
                'then run TQ Together again.\n'
                'Сохранённый оригинал %s повреждён - ничего не изменено. Сделайте в Steam «Свойства > Установленные '
                'файлы > Проверить целостность файлов игры» и запустите TQ Together снова.' % (
                    os.path.basename(b), os.path.basename(b)))

    def installed_intact(self):
        inst = self.state.get('installed', {})
        return bool(inst) and all(os.path.exists(f) and md5(f) == inst.get(os.path.basename(f)) for f in self.files())

    # ---------------------------------------------------------------- install
    def install(self, build_arz, text_ru, text_en):
        """copy the built database, merge our text tags into every Text_XX.arc (RU text into Text_RU, EN elsewhere)"""
        if game_running():                          # 1.9.1: asked again right before writing
            raise SystemExit(GAME_RUNNING)
        for arc in self.texts:                      # 1.9.1: every original we copy from is whole, before anything
            self.check_base(arc)
        backup_saves(self.log, 'install')
        try:
            safe_copy(build_arz, self.arz)
        except PermissionError:
            raise SystemExit(no_write_access(self.game))
        work_root = os.path.join(paths.data_dir(), 'text_work')
        n = want = 0
        for arc in self.texts:
            lang = os.path.basename(arc)[5:-4].upper()
            add = text_ru if lang == 'RU' else text_en
            safe_copy(self.base(arc), arc)          # always from the pristine archive: tags never stack up
            if not add:
                continue
            want += 1
            if not os.path.exists(self.tool) or not is_arc(arc):
                continue
            work = os.path.join(work_root, lang)
            shutil.rmtree(work, ignore_errors=True)
            os.makedirs(work, exist_ok=True)
            # ArchiveTool stores the path it is given: always relative, from inside the folder
            self._run([short_path(self.tool), short_path(self.base(arc)), '-extract', short_path(work), TEXT_HOST])
            host = os.path.join(work, TEXT_HOST)
            if not os.path.exists(host):
                self.log('  ! %s: %s not found, names stay untranslated' % (os.path.basename(arc), TEXT_HOST))
                continue
            raw = open(host, 'rb').read()
            base = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8', 'replace')
            merged = base.rstrip('\r\n') + '\r\n' + TEXT_MARK + '\r\n' + add
            with open(host, 'wb') as f:
                f.write(b'\xff\xfe' + merged.encode('utf-16-le'))
            # 1.8.1: ArchiveTool rewrites the archive in place - it works on a copy in our data folder, and the game
            # file is swapped in one step (a closed window or a power cut in the middle left a cut-off Text_XX.arc
            # in the game, and the next start took it for the game's own new version)
            staged_dir = os.path.join(work_root, lang + '_arc')
            os.makedirs(staged_dir, exist_ok=True)
            staged = os.path.join(staged_dir, os.path.basename(arc))
            shutil.copy2(self.base(arc), staged)
            if not self._run([short_path(self.tool), short_path(staged), '-replace', TEXT_HOST, '.', '9'],
                             cwd=short_path(work)) or md5(staged) == md5(self.base(arc)):
                self.log('  ! %s: ArchiveTool did not add our texts - kept the original' % os.path.basename(arc))
                continue
            listing = subprocess.run([short_path(self.tool), short_path(staged), '-list'], capture_output=True,
                                     text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
            if any(':' in l or l.startswith('/') for l in listing.splitlines()):
                self.log('  ! %s: ArchiveTool wrote absolute paths - kept the original' % os.path.basename(arc))
                continue
            if not (is_arc(staged) and arc_intact(staged)):
                self.log('  ! %s: ArchiveTool left a broken archive - kept the original' % os.path.basename(arc))
                continue
            safe_copy(staged, arc)
            n += 1
        shutil.rmtree(work_root, ignore_errors=True)
        if not os.path.exists(self.tool):
            self.log('  ! ArchiveTool.exe not found in the game folder - item names will show as tags')
        self.state['installed'] = {os.path.basename(f): md5(f) for f in self.files()}
        # 1.8.1: texts that did not go in for want of ArchiveTool are tried again once it is back (they were taken as
        # installed for good); a failure with the tool there is not retried on every start (--rebuild does)
        self.state['texts_ok'] = n >= want
        self.state['texts_no_tool'] = n < want and not os.path.exists(self.tool)
        self.save_state()
        self.log('  installed (texts in %d languages%s)' % (n, '' if n >= want else ', %d failed' % (want - n)))
        return n >= want

    def _run(self, args, cwd=None):
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if r.returncode != 0:
            self.log('  ! ArchiveTool: %s %s' % (r.stdout[-200:], r.stderr[-200:]))
        return r.returncode == 0

    # -------------------------------------------------------------- uninstall
    def uninstall(self):
        """put the originals back - but never over a file the game (an update, Verify) replaced after our install.
        -> list of game files that still hold our data and could not be restored (empty = clean)"""
        if game_running():                          # 1.9.1: asked again right before writing
            raise SystemExit(GAME_RUNNING)
        n = 0
        inst = self.state.get('installed', {})
        left = []
        plan = []                                   # 1.9.1: decide first, check the originals, then change anything
        for f in self.files():
            b = self.base(f)
            name = os.path.basename(f)
            if not os.path.exists(b):
                # 1.8.1: no saved original (deleted by hand) - say so instead of "removed"
                if os.path.exists(f) and (md5(f) == inst.get(name) or (not is_arc(f) and has_our_records(f))):
                    left.append(name)
                continue
            # by content: a file with our records/texts goes back to the original, anything else (a game update
            # after our install) stays as it is. 1.8.1: exactly what we installed is ours without asking ArchiveTool;
            # an archive it cannot read (the tool is gone) keeps its saved original
            ours = os.path.exists(f) and (md5(f) == inst.get(name) or self.ours(f))
            if not ours and os.path.exists(f) and is_arc(f) and not os.path.exists(self.tool):
                self.log('  ! %s: ArchiveTool.exe is missing, cannot tell if it holds our texts - kept %s' % (
                    name, os.path.basename(b)))
                continue
            plan.append((f, b, ours or not os.path.exists(f)))
        for f, b, copy in plan:
            if copy:
                self.check_base(f)
        backup_saves(self.log, 'uninstall')
        for f, b, copy in plan:
            if copy:
                safe_copy(b, f)
                n += 1
            os.remove(b)
        self.state.pop('installed', None)
        self.state.pop('fingerprint', None)
        self.state.pop('clean_bases', None)
        self.state.pop('texts_ok', None)
        self.state.pop('texts_no_tool', None)
        self.save_state()
        self.log('  restored %d original files' % n)
        return left


def game_running():
    """1.9.1: tasklist's output read as bytes - as text a non-ASCII line (a localized Windows) raised
    UnicodeDecodeError and the game counted as closed"""
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq TQ.exe'], capture_output=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout or b''
        return b'tq.exe' in out.lower()
    except Exception:
        return False


GAME_RUNNING = ('Titan Quest is running - close it first. Nothing was changed.\n'
                'Titan Quest запущен - закройте его. Ничего не изменено.')
