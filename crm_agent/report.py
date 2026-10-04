"""Step 4: write the review page (one self-contained HTML file, opens offline)."""
import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("review_template.html")


def render(run, path, standalone=True):
    body = TEMPLATE.read_text()
    data = json.dumps(run, default=str).replace("</", "<\\/")
    body = body.replace("/*__DATA__*/null", data)
    if standalone:
        body = f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n{body}\n</html>\n'
    Path(path).write_text(body)
    return path
