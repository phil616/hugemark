"""Build only the two supported release archives from an explicit binary."""
import argparse
from pathlib import Path
import shutil
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package(platform, binary, output):
    binary, output = Path(binary), Path(output)
    if not binary.is_file():
        raise FileNotFoundError(binary)
    name = f'hugemark-{platform}-amd64'
    windows = platform == 'windows'
    script = 'hugemark-init.ps1' if windows else 'hugemark-init.sh'
    executable = name + ('.exe' if windows else '')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (name + ('.zip' if windows else '.tar.gz'))
    with tempfile.TemporaryDirectory(prefix='hugemark-package-') as temp:
        folder = Path(temp) / name
        folder.mkdir()
        shutil.copyfile(binary, folder / executable)
        (folder / executable).chmod(0o755)
        for relative in [script, 'gui.py', 'desktop.py', 'initialize_environment.py',
                         'requirements-gui.txt', 'assets/desktop.qss',
                         'assets/fonts/NotoSansCJKsc-Regular.otf']:
            destination = folder / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        (folder / script).chmod(0o755 if not windows else 0o644)
        shutil.copyfile(ROOT / 'docs/release-guide.md', folder / 'README.md')
        # One notice document includes licenses of assets shipped in this archive.
        notices = [(ROOT / 'LICENSE').read_text(encoding='utf-8')]
        for title, path in [('Bundled Noto CJK font — SIL OFL', 'assets/fonts/OFL.txt'),
                            ('Embedded MathJax / Mermaid', 'assets/vendor/LICENSES.txt')]:
            notices.append(f'\n\n===== {title} =====\n\n' + (ROOT / path).read_text(encoding='utf-8'))
        (folder / 'LICENSE.txt').write_text(''.join(notices), encoding='utf-8')
        if windows:
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(folder.rglob('*')):
                    if path.is_file():
                        bundle.write(path, path.relative_to(folder.parent).as_posix())
        else:
            with tarfile.open(archive, 'w:gz') as bundle:
                bundle.add(folder, arcname=name)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', choices=['linux', 'windows'], required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('dist'))
    args = parser.parse_args()
    print(package(args.platform, args.binary, args.output))
