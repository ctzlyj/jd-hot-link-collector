"""Release package hygiene: git-tracked files contain no personal paths or caches."""
import re
import subprocess
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]

PERSONAL_PATTERNS = [
    re.compile(r'caotong\.888'),
    re.compile(r'D:\\Miniconda'),
    re.compile(r'D:\\CodexTools'),
]

RUN_ARTIFACT_NAMES = ['browser_context.json', 'runner_state.json', 'keyword_tasks.json',
                      'input_audit.json', 'package_report.json', 'independent_validation.json']


def git_tracked_files():
    try:
        out = subprocess.run(['git', 'ls-files'], cwd=str(SKILL_ROOT),
                             capture_output=True, text=True, timeout=30).stdout.strip()
        return [SKILL_ROOT / f for f in out.split('\n') if f.strip()]
    except Exception:
        return []


class TestReleaseHygiene(unittest.TestCase):
    def test_git_tracked_files_have_no_personal_paths(self):
        for p in git_tracked_files():
            if not p.exists():
                continue
            rel = p.relative_to(SKILL_ROOT)
            if rel.name == 'test_release_hygiene.py':
                continue
            try:
                text = p.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            for pattern in PERSONAL_PATTERNS:
                found = pattern.search(text)
                if found:
                    self.fail(f"Personal path '{found.group()}' in git-tracked file {rel}")

    def test_gitignore_covers_caches_and_artifacts(self):
        gi = SKILL_ROOT / '.gitignore'
        self.assertTrue(gi.exists(), '.gitignore must exist')
        text = gi.read_text(encoding='utf-8')
        for pattern in ['__pycache__', '.pytest_cache', 'node_modules', '*.pyc', '*.log',
                        '.collector_state', 'browser_context.json']:
            self.assertIn(pattern, text, f'.gitignore must cover {pattern}')

    def test_no_run_artifacts_tracked(self):
        for p in git_tracked_files():
            name = p.relative_to(SKILL_ROOT).name
            for artifact in RUN_ARTIFACT_NAMES:
                self.assertNotEqual(name, artifact, f"Run artifact '{name}' is git-tracked")
            self.assertFalse(name.endswith('.log'), f"Log file '{name}' is git-tracked")
            self.assertFalse(name.endswith('.pyc'), f"Compiled file '{name}' is git-tracked")


if __name__ == '__main__':
    unittest.main()
