"""Regenerate the team PDF from its Markdown source."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


REPORT_DIR = Path(__file__).resolve().parent


def main() -> None:
    source = REPORT_DIR / "final_dataset_experiments.md"
    target = REPORT_DIR / "final_dataset_experiments.pdf"
    css = REPORT_DIR / "report.css"
    with tempfile.TemporaryDirectory(prefix="ugrp-report-") as temp_dir:
        html = Path(temp_dir) / "report.html"
        subprocess.run(["pandoc", str(source), "-s", "-c", str(css), "-o", str(html)], check=True)
        subprocess.run(["wkhtmltopdf", "--enable-local-file-access", "--page-size", "A4",
                        "--margin-top", "18", "--margin-bottom", "18", "--margin-left", "17",
                        "--margin-right", "17", str(html), str(target)], check=True)
    print(target)


if __name__ == "__main__":
    main()
