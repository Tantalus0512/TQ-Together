# -*- coding: utf-8 -*-
"""Build the TQ Together release from this repository.

    py -3 -m pip install -r requirements-build.txt
    py -3 build_exe.py

Result: dist/TQ Together <version>/ (TQTogether.exe + readmes + source) and dist/TQ_Together_<version>.zip.
The program uses the Python standard library only. Networking, crypto and compression modules the tool does not
use are excluded on purpose, so the build contains no network code at all."""
import os, sys, shutil, subprocess, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'src')
sys.path.insert(0, SRC)
import paths

VER = paths.VERSION
NAME = 'TQ Together %s' % VER
DIST = os.path.join(HERE, 'dist')
WORK = os.path.join(HERE, 'build')
MODULES = ['paths', 'installer', 'build_companions', 'verify_companions', 'tweaks', 'orb_odds', 'hero_power', 'souls', 'soul_anims', 'arz',
           'arz_lazy', 'tqlib', 'chr_reader']
EXCLUDE = ['ssl', '_ssl', 'socket', '_socket', 'select', 'selectors', 'urllib', 'http', 'email', 'xml', 'xmlrpc',
           'ftplib', 'smtplib', 'mailbox', 'bz2', '_bz2', 'lzma', '_lzma', '_zstd', 'compression', 'decimal',
           '_decimal', 'unicodedata', '_hashlib', 'tkinter', 'asyncio', 'multiprocessing', 'sqlite3', 'pydoc',
           'unittest', 'doctest']


def version_file(path):
    v = tuple(int(x) for x in VER.split('.')) + (0,) * (4 - len(VER.split('.')))
    open(path, 'w', encoding='utf-8').write('''VSVersionInfo(
  ffi=FixedFileInfo(filevers=%(v)r, prodvers=%(v)r, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'TQ Together'),
      StringStruct('FileDescription', 'TQ Together - companions from your saves for Titan Quest Anniversary Edition'),
      StringStruct('FileVersion', '%(s)s'),
      StringStruct('InternalName', 'TQTogether'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'TQTogether.exe'),
      StringStruct('ProductName', 'TQ Together'),
      StringStruct('ProductVersion', '%(s)s')])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
''' % {'v': v, 's': VER})


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    vf = os.path.join(WORK, 'version.txt')
    version_file(vf)
    # --onefile (1.6.6): the onedir build carried _internal\base_library.zip, an archive inside the mod archive, which
    # Nexus Mods rejects ("we reject any upload that features additional archives inside the mod structure")
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--console', '--onefile',
           '--name', 'TQTogether', '--distpath', os.path.join(WORK, 'pyi_dist'), '--workpath', os.path.join(WORK, 'pyi'),
           '--specpath', WORK, '--paths', SRC, '--version-file', vf, '--noupx']
    cmd += sum([['--hidden-import', m] for m in MODULES], [])
    cmd += sum([['--exclude-module', m] for m in EXCLUDE], [])
    cmd += [os.path.join(SRC, 'tq_together.py')]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit('PyInstaller failed')

    out = os.path.join(DIST, NAME)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    shutil.copy2(os.path.join(WORK, 'pyi_dist', 'TQTogether.exe'), os.path.join(out, 'TQTogether.exe'))
    for f in ('README_EN.txt', 'README_RU.txt', 'CHANGELOG_EN.txt', 'CHANGELOG_RU.txt'):
        shutil.copy2(os.path.join(HERE, 'docs', f), os.path.join(out, f))
    with open(os.path.join(out, 'Uninstall TQ Together.bat'), 'w', newline='\r\n', encoding='ascii') as f:
        f.write('@echo off\n"%~dp0TQTogether.exe" --uninstall\n')
    with open(os.path.join(out, 'TQTogether.ini.example'), 'w', encoding='utf-8') as f:
        f.write('; Rename to TQTogether.ini to change a setting (README: Difficulty).\n'
                '; Переименуйте в TQTogether.ini, чтобы поменять настройку (README: Сложность).\n'
                '; Only if TQ Together cannot find the game by itself / только если игра не находится сама:\n'
                '; GamePath=D:\\Games\\Titan Quest Anniversary Edition\n'
                '; party (default) | power | off\n'
                '; Difficulty=party\n'
                '; one companion = this many players / один соратник = столько игроков\n'
                '; CompanionPlayers=1\n'
                '; Enslaved boss souls (README: Enslaved boss souls) - shards per soul. Do not change them once you collect: a soul half done\n'
                '; with the old number would complete without its summon.\n'
                '; Порабощённые души боссов (README: Порабощённые души) - осколков на душу. Не меняйте, когда уже собираете: недособранная душа\n'
                '; со старым числом соберётся без призыва.\n'
                '; SoulBossShards=3\n'
                '; SoulHeroShards=2\n'
                '; % per kill / за убийство; % per boss chest opening / за сундук босса; % per electrum orb / за сферу\n'
                '; SoulBossChance=15\n'
                '; SoulHeroChance=12\n'
                '; SoulChestChance=15\n'
                '; SoulOrbChance=20\n'
                '; soul life, % / здоровье душ, %\n'
                '; SoulLife=100\n'
                '; the average boss soul\'s basic attack, % of your hero\'s damage per second (0 = the boss\'s own damage) /\n'
                '; базовая атака средней души, % от урона в секунду героя (0 - собственный урон босса)\n'
                '; SoulDamage=30\n'
                '; no soul animation faster than this many times the boss\'s own (1 = the boss\'s own speeds) /\n'
                '; ни одна анимация души не быстрее, чем во столько раз от самого босса (1 - скорости самого босса)\n'
                '; SoulSpeedMax=2\n'
                '; 0 = no soul drops (souls already collected keep working) / 0 = души не падают (собранные работают)\n'
                '; Souls=1\n'
                '; SoulHeroes=1\n')
    shutil.copytree(SRC, os.path.join(out, 'src'), ignore=shutil.ignore_patterns('__pycache__'))
    # Nexus Mods rejects an archive inside the mod archive (support, 16.10.2026): none may ship
    inner = [os.path.relpath(os.path.join(r, fn), out) for r, ds, fs in os.walk(out) for fn in fs
             if fn.lower().endswith(('.zip', '.7z', '.rar', '.pyz', '.tar', '.gz', '.cab', '.arc'))]
    if inner:
        raise SystemExit('archives inside the package (Nexus rejects them): %s' % inner)
    zp = os.path.join(DIST, 'TQ_Together_%s.zip' % VER)
    if os.path.exists(zp):
        os.remove(zp)
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, dirs, files in os.walk(out):
            for fn in files:
                p = os.path.join(root, fn)
                z.write(p, os.path.relpath(p, DIST))
    print('package:', zp, '%.1f MB' % (os.path.getsize(zp) / 1e6))


if __name__ == '__main__':
    main()
