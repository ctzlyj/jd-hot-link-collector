"""Task-local artifact author adapter; openpyxl implementation replacing the missing shared office runtime."""
import json
import os
import sys
from pathlib import Path


def write_artifact(spec):
    stage = Path(os.environ['JD_COLLECTOR_STATE_DIR']).resolve()
    output = Path(spec['output']).resolve()
    if not output.is_relative_to(stage / 'packages'):
        raise ValueError('ARTIFACT_OUTPUT_OUTSIDE_TASK_PACKAGE')
    manifest = output.parent / 'artifact_workbook_spec.json'
    manifest.write_text(json.dumps([spec], ensure_ascii=False), encoding='utf-8')
    sys.path.insert(0, str(Path(__file__).parent))
    from workbook_author_openpyxl import write_artifact as author
    return author(spec)


def main():
    scripts = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(scripts))
    import package_live
    package_live.write_workbook = write_artifact
    package_live.main()


if __name__ == '__main__':
    main()

