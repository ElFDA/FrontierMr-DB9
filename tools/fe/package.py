#!/usr/bin/env python3
"""Build a distributable Frontier ZIP with the current installer and assets.

MiSTer-DB9 version (repository FrontierMr-DB9, database id frontiermr_db9);
--no-menu leaves out frontier/bin/menu.rbf (the DB9 menu.rbf of the SD is used).

The SD files are those of tools/fe/sd, plus bin/MiSTer, menu.rbf, lib/fe_av.so
(tools/fe/fe_av/build.sh) and the ScreenScraper key (tools/fe/ss_key.py).
--db-url also sets up Frontier's updates through update_all
(frontier/downloader_frontiermr_db9.ini, copied to the SD root by the installer);
--zip-url writes the database, which takes every file from this ZIP published
at that URL (see make_db.py).

A GitHub release of FrontierMr-DB9 (tag on the commit of "publish" made from the
same frontier commit, see publish.py):
  package.py --release v2026.10.26b-db9 --owner USER
uses the public files only and writes in the output folder db.json.zip (for
the "db" branch) and assets/ for the release: the ZIP, downloader_frontiermr_db9.ini
(to start an installation through update_all) and theme_editor.html (for the
PC, standalone: it is not in the ZIP).
"""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import make_db

ROOT = Path(__file__).resolve().parents[2]
REPO = 'FrontierMr-DB9'


def main():
    date = datetime.now(timezone.utc).date().isoformat()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / ('Frontier_' + date))
    parser.add_argument('--menu', type=Path, default=ROOT.parent / 'MisterMenu-db9/output_files/menu.rbf',
                        help="Frontier's menu.rbf (the DB9 menu core with Frontier's patch)")
    parser.add_argument('--no-menu', action='store_true',
                        help='no frontier/bin/menu.rbf: the menu.rbf in the root of the SD (DB9\'s) is used')
    parser.add_argument('--mister', type=Path, default=ROOT / 'bin/MiSTer')
    parser.add_argument('--db-url', help="URL of Frontier's db.json.zip (enables updates through update_all)")
    parser.add_argument('--zip-url', help='URL where the ZIP is published: also writes db.json.zip')
    parser.add_argument('--public', action='store_true', help='only the files of the public version (publish.py)')
    parser.add_argument('--release', metavar='TAG', help='GitHub release of %s: sets the URLs and --public' % REPO)
    parser.add_argument('--owner', help='GitHub account of %s (with --release)' % REPO)
    parser.add_argument('--no-ss-key', action='store_true',
                        help='package without the ScreenScraper key (tools/fe/ss_key.py writes it)')
    args = parser.parse_args()
    if args.release:
        if not args.owner:
            parser.error('--release needs --owner')
        raw = 'https://raw.githubusercontent.com/%s/%s/' % (args.owner, REPO)
        args.db_url = raw + 'db/db.json.zip'
        args.zip_url = 'https://github.com/%s/%s/releases/download/%s/%s' % (
            args.owner, REPO, args.release, args.output.name + '.zip')
        args.public = True
    output = args.output.resolve()
    archive = output.with_name(output.name + '.zip')
    if output.exists() or archive.exists():
        parser.error('Output already exists; choose a new --output path.')
    fe_av = ROOT / 'tools/fe/sd/frontier/lib/fe_av.so'
    for path in (args.mister, fe_av) + (() if args.no_menu else (args.menu,)):
        if not path.is_file() or path.stat().st_size == 0:
            parser.error('Required binary is missing or empty: %s' % path)
    key = ROOT / 'tools/fe/sd/frontier/scraper/ss_dev.key'
    if not args.no_ss_key and subprocess.run([sys.executable, str(ROOT / 'tools/fe/ss_key.py'), '--check']).returncode:
        parser.error('ScreenScraper key missing: run tools/fe/ss_key.py (or --no-ss-key)')

    temp = tempfile.TemporaryDirectory()
    sd = ROOT / 'tools/fe/sd'
    if args.public:
        # the same files as the repository (guides cut, local themes out)
        subprocess.run([sys.executable, str(ROOT / 'tools/fe/publish.py'), '--ref', 'HEAD', '--upstream', 'db9/master',
                        '--export', temp.name], check=True)
        sd = Path(temp.name) / 'tools/fe/sd'
    setup = output / 'SD/frontier_setup'
    setup.mkdir(parents=True)
    ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '.gitignore', '*.bak*', '*~')
    shutil.copytree(sd / 'frontier', setup / 'frontier', ignore=ignore)
    shutil.copytree(sd / 'Scripts', output / 'SD/Scripts', ignore=ignore)
    (setup / 'frontier/bin').mkdir()
    shutil.copy2(args.mister, setup / 'frontier/bin/MiSTer')
    if not args.no_menu:
        shutil.copy2(args.menu, setup / 'frontier/bin/menu.rbf')
    (setup / 'frontier/lib').mkdir(exist_ok=True)
    shutil.copy2(fe_av, setup / 'frontier/lib/fe_av.so')
    if args.no_ss_key:
        (setup / 'frontier/scraper' / key.name).unlink(missing_ok=True)
    else:
        shutil.copy2(key, setup / 'frontier/scraper' / key.name)
    if args.db_url:
        (setup / 'frontier/downloader_frontiermr_db9.ini').write_text(
            '[%s]\ndb_url = %s\n' % (make_db.DB_ID, args.db_url))
    for path in (output / 'SD/Scripts').glob('*.sh'):
        path.chmod(0o755)
    flavour = (("Menu core: the DB9 menu.rbf of your SD, unchanged (a CRT shows the HDMI picture).",
                "Menu core: DB9's menu.rbf, invariato (un CRT mostra l'immagine della HDMI).") if args.no_menu else
               ("Menu core: Frontier's menu.rbf (DB9 + second framebuffer) in frontier/bin: HD on HDMI and 240p on the CRT.",
                "Menu core: il menu.rbf di Frontier (DB9 + secondo framebuffer) in frontier/bin: HD sulla HDMI e 240p sul CRT."))
    for name, text_flavour in (('GUIDA_INSTALLAZIONE_DB9_ita.txt', flavour[1]), ('INSTALL_DB9.txt', flavour[0])):
        text = (ROOT / 'tools/fe/package' / name).read_text().replace('@BUILD_DATE@', date).replace('@FLAVOUR@', text_flavour)
        (output / name.replace('_DB9', '')).write_text(text)
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted((output / 'SD').rglob('*')) + sorted(output.glob('*.txt')):
            if path.is_file():
                z.write(path, path.relative_to(output))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise RuntimeError('ZIP integrity check failed.')
    if args.zip_url:
        make_db.write(make_db.build(archive, args.zip_url), output / 'db.json.zip')
        print('Database:', output / 'db.json.zip')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_name(archive.name + '.sha256').write_text(digest + '  ' + archive.name + '\n')
    if args.release:
        assets = output / 'assets'
        assets.mkdir()
        shutil.copy2(archive, assets / archive.name)
        shutil.copy2(setup / 'frontier/downloader_frontiermr_db9.ini', assets / 'downloader_frontiermr_db9.ini')
        # the theme editor runs on the PC: a file of its own, not in the ZIP for the SD
        shutil.copy2(Path(temp.name) / 'tools/fe/theme_editor.html', assets / 'theme_editor.html')
        print('Release assets:', assets, sorted(p.name for p in assets.iterdir()))
    temp.cleanup()
    print('Package:', archive)
    print('Size: %.1f MiB' % (archive.stat().st_size / 1024**2))
    print('SHA256:', digest)


if __name__ == '__main__':
    main()
