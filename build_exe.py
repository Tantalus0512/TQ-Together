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
MODULES = ['paths', 'installer', 'build_companions', 'verify_companions', 'orb_odds', 'arz', 'arz_lazy', 'tqlib',
           'chr_reader']
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
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--console', '--onedir',
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
    shutil.copytree(os.path.join(WORK, 'pyi_dist', 'TQTogether'), out)
    for f in ('README_EN.txt', 'README_RU.txt'):
        shutil.copy2(os.path.join(HERE, 'docs', f), os.path.join(out, f))
    with open(os.path.join(out, 'Uninstall TQ Together.bat'), 'w', newline='\r\n', encoding='ascii') as f:
        f.write('@echo off\n"%~dp0TQTogether.exe" --uninstall\n')
    with open(os.path.join(out, 'TQTogether.ini.example'), 'w', encoding='utf-8') as f:
        f.write('; Rename to TQTogether.ini only if TQ Together cannot find the game by itself.\n'
                '; Переименуйте в TQTogether.ini, только если TQ Together не находит игру сам.\n'
                'GamePath=D:\\Games\\Titan Quest Anniversary Edition\n')
    shutil.copytree(SRC, os.path.join(out, 'src'), ignore=shutil.ignore_patterns('__pycache__'))
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
