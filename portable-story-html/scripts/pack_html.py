#!/usr/bin/env python3
"""Inline a built HTML entry and its local assets into one portable HTML file."""

from __future__ import annotations

import argparse
import base64
import html
from html.parser import HTMLParser
import mimetypes
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


SKIP_SCHEMES = {"data", "blob", "http", "https", "mailto", "tel", "javascript", "about"}
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
CSS_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*)?(['\"])(.*?)\1\s*\)?\s*([^;]*);",
    re.IGNORECASE,
)


def mime_type(path: Path) -> str:
    overrides = {
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".wasm": "application/wasm",
    }
    return overrides.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type(path)};base64,{encoded}"


class PackError(RuntimeError):
    pass


class Resolver:
    def __init__(self, root: Path, allow_missing: bool = False):
        self.root = root.resolve()
        self.allow_missing = allow_missing
        self.css_stack: set[Path] = set()

    @staticmethod
    def is_embedded_or_external(value: str) -> bool:
        raw = value.strip()
        if not raw or raw.startswith(("#", "//")):
            return True
        return urlsplit(raw).scheme.lower() in SKIP_SCHEMES

    def resolve(self, value: str, base_dir: Path) -> Path | None:
        if self.is_embedded_or_external(value):
            return None
        parsed = urlsplit(value.strip())
        path_text = unquote(parsed.path)
        candidate = (self.root / path_text.lstrip("/")) if path_text.startswith("/") else (base_dir / path_text)
        candidate = candidate.resolve()
        if not candidate.is_file():
            if self.allow_missing:
                return None
            raise PackError(f"Missing local asset: {value} (resolved to {candidate})")
        return candidate

    def inline_reference(self, value: str, base_dir: Path) -> str:
        path = self.resolve(value, base_dir)
        return data_url(path) if path else value

    def inline_srcset(self, value: str, base_dir: Path) -> str:
        items = []
        for item in value.split(","):
            parts = item.strip().split(None, 1)
            if not parts:
                continue
            url = self.inline_reference(parts[0], base_dir)
            items.append(url if len(parts) == 1 else f"{url} {parts[1]}")
        return ", ".join(items)

    def inline_css(self, css: str, base_dir: Path) -> str:
        def import_replace(match: re.Match[str]) -> str:
            target, media = match.group(2), match.group(3).strip()
            imported = self.resolve(target, base_dir)
            if imported is None:
                return match.group(0)
            if imported in self.css_stack:
                raise PackError(f"Circular CSS import: {imported}")
            self.css_stack.add(imported)
            body = self.inline_css(imported.read_text(encoding="utf-8"), imported.parent)
            self.css_stack.remove(imported)
            return f"@media {media}{{{body}}}" if media else body

        css = CSS_IMPORT_RE.sub(import_replace, css)

        def url_replace(match: re.Match[str]) -> str:
            value = match.group(2).strip()
            return f'url("{self.inline_reference(value, base_dir)}")'

        return CSS_URL_RE.sub(url_replace, css)


def attrs_to_text(attrs: list[tuple[str, str | None]]) -> str:
    rendered = []
    for name, value in attrs:
        if value is None:
            rendered.append(name)
        else:
            rendered.append(f'{name}="{html.escape(value, quote=True)}"')
    return (" " + " ".join(rendered)) if rendered else ""


class Inliner(HTMLParser):
    MEDIA_TAG_ATTRS = {
        "img": {"src"},
        "source": {"src"},
        "video": {"src", "poster"},
        "audio": {"src"},
        "track": {"src"},
        "embed": {"src"},
        "input": {"src"},
        "object": {"data"},
    }

    def __init__(self, resolver: Resolver, html_dir: Path):
        super().__init__(convert_charrefs=False)
        self.resolver = resolver
        self.html_dir = html_dir
        self.output: list[str] = []
        self.style_buffer: list[str] | None = None
        self.style_attrs: list[tuple[str, str | None]] = []
        self.skip_end_tag: str | None = None

    def handle_decl(self, decl: str) -> None:
        self.output.append(f"<!{decl}>")

    def handle_comment(self, data: str) -> None:
        self._append(f"<!--{data}-->")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        attr_map = {k.lower(): v for k, v in attrs}

        if lower == "base":
            return
        if lower == "meta" and (attr_map.get("http-equiv") or "").lower() == "content-security-policy":
            return
        if lower == "link":
            rel = set((attr_map.get("rel") or "").lower().split())
            href = attr_map.get("href") or ""
            if "stylesheet" in rel:
                path = self.resolver.resolve(href, self.html_dir)
                if path:
                    css = self.resolver.inline_css(path.read_text(encoding="utf-8"), path.parent)
                    media = attr_map.get("media")
                    media_attr = f' media="{html.escape(media, quote=True)}"' if media else ""
                    self.output.append(f"<style{media_attr}>{css}</style>")
                    return
            if rel.intersection({"icon", "apple-touch-icon", "mask-icon", "preload"}) and href:
                attrs = [(k, self.resolver.inline_reference(v, self.html_dir) if k.lower() == "href" and v else v) for k, v in attrs]
        elif lower == "script" and attr_map.get("src"):
            path = self.resolver.resolve(attr_map["src"] or "", self.html_dir)
            if path:
                code = path.read_text(encoding="utf-8").replace("</script", "<\\/script")
                kept = [(k, v) for k, v in attrs if k.lower() not in {"src", "integrity", "crossorigin", "async", "defer"}]
                self.output.append(f"<script{attrs_to_text(kept)}>{code}</script>")
                self.skip_end_tag = "script"
                return
        elif lower == "style":
            self.style_buffer = []
            self.style_attrs = attrs
            return

        allowed = self.MEDIA_TAG_ATTRS.get(lower, set())
        rewritten = []
        for name, value in attrs:
            key = name.lower()
            if value is not None and key in allowed:
                value = self.resolver.inline_reference(value, self.html_dir)
            elif value is not None and key == "srcset" and lower in {"img", "source"}:
                value = self.resolver.inline_srcset(value, self.html_dir)
            elif value is not None and key == "style":
                value = self.resolver.inline_css(value, self.html_dir)
            rewritten.append((name, value))
        self.output.append(f"<{tag}{attrs_to_text(rewritten)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.skip_end_tag == tag.lower():
            self.skip_end_tag = None
        elif tag.lower() not in {"base", "link", "meta", "img", "source", "input", "track", "embed"}:
            self.output.append(f"</{tag}>")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if self.skip_end_tag == lower:
            self.skip_end_tag = None
            return
        if lower == "style" and self.style_buffer is not None:
            css = self.resolver.inline_css("".join(self.style_buffer), self.html_dir)
            self.output.append(f"<style{attrs_to_text(self.style_attrs)}>{css}</style>")
            self.style_buffer = None
            self.style_attrs = []
            return
        self._append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._append(data)

    def handle_entityref(self, name: str) -> None:
        self._append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._append(f"&#{name};")

    def handle_pi(self, data: str) -> None:
        self._append(f"<?{data}>")

    def handle_unknown_decl(self, data: str) -> None:
        self._append(f"<![{data}]>")

    def _append(self, value: str) -> None:
        if self.style_buffer is not None:
            self.style_buffer.append(value)
        else:
            self.output.append(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Intermediate HTML entry")
    parser.add_argument("output", type=Path, help="Portable output HTML")
    parser.add_argument("--root", type=Path, help="Build root for absolute /asset paths")
    parser.add_argument("--allow-missing", action="store_true", help="Leave missing references unchanged")
    args = parser.parse_args()

    input_path = args.input.resolve()
    if not input_path.is_file():
        print(f"Input HTML not found: {input_path}", file=sys.stderr)
        return 2
    root = (args.root or input_path.parent).resolve()
    resolver = Resolver(root, allow_missing=args.allow_missing)
    parser_impl = Inliner(resolver, input_path.parent)
    try:
        parser_impl.feed(input_path.read_text(encoding="utf-8"))
        parser_impl.close()
    except (OSError, UnicodeError, PackError) as exc:
        print(f"Packing failed: {exc}", file=sys.stderr)
        return 1

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(parser_impl.output), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
