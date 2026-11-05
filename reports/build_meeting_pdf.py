"""Render the dated meeting report without overwriting the earlier interim PDF."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "final_dataset_meeting_2026-10-15.md"
TARGET = ROOT / "final_dataset_meeting_2026-10-15.pdf"


def main():
    with tempfile.TemporaryDirectory(prefix="ugrp-meeting-") as folder:
        html = Path(folder) / "report.html"
        subprocess.run(["pandoc", str(SOURCE), "-s", "-M", "pagetitle=최종 데이터셋 추천 구조 검증",
                        "-c", str(ROOT / "report.css"), "-o", str(html)], check=True)
        subprocess.run(["wkhtmltopdf", "--enable-local-file-access", "--page-size", "A4",
                        "--footer-center", "[page] / [topage]", "--footer-font-size", "8",
                        "--margin-top", "18", "--margin-bottom", "18", "--margin-left", "17",
                        "--margin-right", "17", str(html), str(TARGET)], check=True)
    print(TARGET)


if __name__ == "__main__":
    main()
