"""A successful fresh compile must not hide a stale published paper."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('paper_artifact', ROOT / 'docs/paper_artifact.py')
paper_artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper_artifact)


class PaperArtifact(unittest.TestCase):
    def test_receipt_detects_source_generated_and_pdf_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = list(paper_artifact.SOURCE_FILES) + [
                'paper/figures/headline.tex', 'docs/assets/fonts/body.ttf',
                'SPEC.md', 'paper/generated/body.tex', 'paper/generated/repetitions.dat',
                str(paper_artifact.PDF),
            ]
            for name in paths:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            paper_artifact.record(root)
            paper_artifact.verify(root)
            for name in ('paper/benchmark.md', 'paper/generated/body.tex', str(paper_artifact.PDF)):
                with self.subTest(path=name):
                    path = root / name
                    original = path.read_bytes()
                    path.write_bytes(original + b'changed')
                    with self.assertRaisesRegex(SystemExit, 'stale or changed'):
                        paper_artifact.verify(root)
                    path.write_bytes(original)
            extra = root / 'paper/generated/table-new.tex'
            extra.write_text('unrecorded generated content')
            with self.assertRaisesRegex(SystemExit, 'generated'):
                paper_artifact.verify(root)

    def test_missing_receipt_requires_canonical_build(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SystemExit, 'run python docs/build_latex.py'):
                paper_artifact.verify(Path(directory))
