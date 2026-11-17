"""Regenerate or verify the hashed lock files from the requirements*.txt ranges.

  python lock_requirements.py                 # update locks after editing requirements*.txt
  python lock_requirements.py -P pillow       # also move a package to its newest allowed version
  python lock_requirements.py --check         # CI: fail if a lock is out of date

requirements.lock      -> Docker image (web, Celery). requirements-dev.lock -> CI and local venv.
Locks are universal (Linux and Windows) and target Python 3.13; existing pins are kept
unless the ranges no longer allow them or -P asks for an upgrade.
"""
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCKS = [
    ('requirements.lock', ['requirements-share.txt', 'requirements-cache.txt', 'requirements-server.txt'], []),
    # Dev tools are constrained to the runtime lock, so both files pin the same app versions.
    ('requirements-dev.lock', ['requirements-dev.txt', 'requirements-share.txt', 'requirements-server.txt'], ['-c', 'requirements.lock']),
]
COMMON = ['--universal', '--python-version', '3.13', '--generate-hashes', '--no-header', '--annotation-style', 'line', '-q']


def compile_lock(workdir, output, inputs, extra, upgrades):
    # Relative paths only: uv writes them into the "# via -c ..." annotations.
    subprocess.run([sys.executable, '-m', 'uv', 'pip', 'compile', *inputs, *extra, *COMMON, *upgrades, '-o', output],
                   cwd=workdir, check=True)


def main(args):
    check = '--check' in args
    upgrades = [a for a in args if a != '--check']
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) if check else HERE
        if check:
            # Compile copies (current pins act as preferences) and compare with the originals.
            for source in [*HERE.glob('requirements*.txt'), *HERE.glob('requirements*.lock')]:
                shutil.copy(source, target / source.name)
        for name, inputs, extra in LOCKS:
            compile_lock(target, name, inputs, extra, upgrades)
        if check:
            stale = [name for name, _, _ in LOCKS if not filecmp.cmp(HERE / name, target / name, shallow=False)]
            if stale:
                sys.exit(f'Out of date: {", ".join(stale)}. Run: python lock_requirements.py')
            print('Lock files match requirements*.txt')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)  # uv already printed why resolution failed
