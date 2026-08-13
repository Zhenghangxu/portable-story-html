#!/usr/bin/env python3
"""Statically audit a single HTML file for portability, network use, and secrets."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
CSS_IMPORT_RE = re.compile(r"@import\s+(?:url\(\s*)?['\"]?([^'\")\s;]+)", re.IGNORECASE)
MODULE_REF_RE = re.compile(
    r"(?:\bimport\s*(?:\(|[^;]*?\bfrom\s*)|\bexport\s+[^;]*?\bfrom\s*)['\"]([^'\"]+)['\"]",
    re.DOTALL,
)
WORKER_RE = re.compile(r"\b(?:Worker|SharedWorker)\s*\(\s*['\"]([^'\"]+)['\"]")
NETWORK_API_RE = re.compile(r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\b")
NETWORK_LITERAL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b"),
    "credential assignment": re.compile(
        r"(?i)(?:api[_-]?key|client[_-]?secret|access[_-]?token|authorization)\s*[:=]\s*['\"]([^'\"]{16,})['\"]"
    ),
}


def classify_url(value: str) -> str:
    raw = value.strip()
    if not raw or raw.startswith("#"):
        return "embedded"
    if raw.startswith("//"):
        return "external"
    scheme = urlsplit(raw).scheme.lower()
    if scheme in {"data", "blob", "about", "javascript", "mailto", "tel"}:
        return "embedded"
    if scheme in {"http", "https", "ws", "wss", "file"}:
        return "external" if scheme != "file" else "local"
    return "local"


class AuditParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active: list[dict[str, str]] = []
        self.forms: list[str] = []
        self.frames: list[str] = []
        self.inline_scripts: list[str] = []
        self.inline_styles: list[str] = []
        self.network_blocked = False
        self._capture: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        values = {k.lower(): v or "" for k, v in attrs}
        if lower == "meta" and values.get("name", "").lower() == "portable-story-network":
            self.network_blocked = values.get("content", "").lower() == "blocked"
        elif lower == "script":
            if values.get("src"):
                self.active.append({"kind": "script", "url": values["src"]})
            else:
                self._capture, self._buffer = "script", []
        elif lower == "style":
            self._capture, self._buffer = "style", []
        elif lower == "link":
            rel = set(values.get("rel", "").lower().split())
            if rel.intersection({"stylesheet", "icon", "apple-touch-icon", "mask-icon", "preload", "modulepreload", "manifest"}):
                self.active.append({"kind": f"link:{','.join(sorted(rel))}", "url": values.get("href", "")})
        elif lower in {"img", "source", "video", "audio", "track", "embed", "input"} and values.get("src"):
            self.active.append({"kind": lower, "url": values["src"]})
        elif lower == "video" and values.get("poster"):
            self.active.append({"kind": "video-poster", "url": values["poster"]})
        elif lower == "object" and values.get("data"):
            self.active.append({"kind": "object", "url": values["data"]})
        elif lower in {"iframe", "frame"} and values.get("src"):
            self.frames.append(values["src"])
            self.active.append({"kind": lower, "url": values["src"]})
        elif lower == "form" and values.get("action"):
            self.forms.append(values["action"])

        for name, value in attrs:
            if name.lower() == "style" and value:
                self.inline_styles.append(value)
            if name.lower() == "srcset" and value:
                for item in value.split(","):
                    url = item.strip().split(None, 1)[0]
                    if url:
                        self.active.append({"kind": f"{lower}:srcset", "url": url})

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if self._capture == lower:
            content = "".join(self._buffer)
            (self.inline_scripts if lower == "script" else self.inline_styles).append(content)
            self._capture, self._buffer = None, []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)


def audit(path: Path, strict_network: bool, fail_on_secrets: bool) -> tuple[dict, bool]:
    text = path.read_text(encoding="utf-8")
    parser = AuditParser()
    parser.feed(text)
    parser.close()

    errors: list[str] = []
    warnings: list[str] = []

    for ref in parser.active:
        classification = classify_url(ref["url"])
        if classification != "embedded":
            errors.append(f"Active {classification} dependency ({ref['kind']}): {ref['url']}")

    for index, css in enumerate(parser.inline_styles, 1):
        for regex, label in ((CSS_URL_RE, "CSS url"), (CSS_IMPORT_RE, "CSS import")):
            for match in regex.finditer(css):
                value = match.group(2) if regex is CSS_URL_RE else match.group(1)
                if classify_url(value) != "embedded":
                    errors.append(f"{label} dependency in style block {index}: {value}")

    scripts = "\n".join(parser.inline_scripts)
    for regex, label in ((MODULE_REF_RE, "module import"), (WORKER_RE, "worker")):
        for match in regex.finditer(scripts):
            value = match.group(1)
            if classify_url(value) != "embedded":
                errors.append(f"Runtime {label} dependency: {value}")

    for form in parser.forms:
        message = f"Form action can navigate away: {form}"
        (errors if strict_network and classify_url(form) != "embedded" else warnings).append(message)
    for frame in parser.frames:
        if classify_url(frame) != "embedded":
            errors.append(f"Frame dependency: {frame}")

    api_names = sorted(set(NETWORK_API_RE.findall(scripts)))
    network_literals = sorted(set(NETWORK_LITERAL_RE.findall(scripts)))
    if api_names:
        message = f"Network-capable JavaScript APIs present: {', '.join(api_names)}"
        (warnings if parser.network_blocked else errors if strict_network else warnings).append(message)
    if strict_network and not parser.network_blocked:
        errors.append('Missing offline guard marker: <meta name="portable-story-network" content="blocked">')
    if network_literals:
        preview = ", ".join(network_literals[:8])
        message = f"HTTP(S) string literals present ({len(network_literals)}): {preview}"
        warnings.append(message)

    secret_hits = []
    for label, regex in SECRET_PATTERNS.items():
        if regex.search(text):
            secret_hits.append(label)
    if secret_hits:
        message = f"Potential embedded secrets: {', '.join(secret_hits)}"
        (errors if fail_on_secrets else warnings).append(message)

    report = {
        "file": str(path.resolve()),
        "bytes": path.stat().st_size,
        "strict_network": strict_network,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "passed": not errors,
    }
    return report, not errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--strict-network", action="store_true", help="Fail when network-capable APIs or form actions remain")
    parser.add_argument("--fail-on-secrets", action="store_true", help="Fail on high-confidence secret patterns")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    path = args.html.resolve()
    if not path.is_file():
        print(f"HTML file not found: {path}", file=sys.stderr)
        return 2
    try:
        report, passed = audit(path, args.strict_network, args.fail_on_secrets)
    except (OSError, UnicodeError) as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{'PASS' if passed else 'FAIL'}: {report['file']} ({report['bytes']} bytes)")
        for error in report["errors"]:
            print(f"ERROR: {error}")
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
