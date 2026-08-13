---
name: portable-story-html
description: Convert a specific Storybook/CSF story export into one self-contained HTML file with its component runtime, styles, fonts, images, icons, and optional QA mocks embedded. Use when a user asks to share, export, package, or hand off a story as a portable/offline/single-file HTML artifact that opens directly without Storybook, a server, repository access, installed packages, or internet access.
disable-model-invocation: true
---

# Portable Story HTML

Create a faithful single-file build of one story without changing shipped application code. Use only repository-local tooling and this skill's scripts; do not require another skill, MCP server, browser automation, or external service.

## Required output

Deliver one `.html` file that:

- opens from `file://` in a normal browser;
- contains all required CSS, JavaScript, fonts, images, and icons;
- has no local file dependencies or runtime chunk imports;
- preserves the story's styling and interactions;
- contains no production credentials or unintended network calls;
- keeps QA-only mocks in the temporary artifact entry, not in shipped source.

## Workflow

### 1. Resolve the target

Identify the story file, named export, output path, required viewport/theme, and any requested args or mocks. If the named export is omitted and the file has one obvious story, use it; otherwise ask.

Inspect the repository's package manifest, Storybook configuration, preview annotations, path aliases, style entry points, and framework. Do not install packages unless the user explicitly approves it.

### 2. Create an isolated artifact entry

Create temporary source under a clearly scoped artifact/build directory. Do not edit the story or application source merely to enable the export.

Render the named story through the installed framework and Storybook composition API when available. Otherwise reproduce CSF semantics in this order:

1. merge `meta.args` with `story.args` and explicit user overrides;
2. use `story.render`, then `meta.render`, then `meta.component`;
3. apply story/meta decorators from inside out;
4. reproduce relevant global preview decorators and parameters;
5. import the same global styles, theme wrapper, fonts, and initialization code used by preview.

Read [references/framework-adapters.md](references/framework-adapters.md) for framework-specific entry patterns.
Read [references/style-fidelity.md](references/style-fidelity.md) before assembling reduced styles or declaring the result faithful.

### 3. Keep mocks artifact-only and safe

Place mock data, request interception, storage seeding, and redirect capture in the temporary entry. Never copy real API keys, tokens, cookies, or private endpoints into the output.

For an offline QA artifact:

- replace requested API behavior with deterministic local fixtures;
- block `fetch`, XHR, WebSocket, EventSource, and `sendBeacon` unless the user explicitly needs network access;
- add `<meta name="portable-story-network" content="blocked">` only after installing those guards before application initialization;
- redirect external form/navigation completion to an in-artifact result state;
- preserve the visible interaction flow rather than bypassing it;
- make the mocked trigger values clear in the handoff.

Read [references/security-and-portability.md](references/security-and-portability.md) before packaging any story that normally authenticates, fetches, uploads, redirects, or submits forms.

### 4. Build one runtime bundle

Use the repository's installed bundler. Configure a single entry and disable code splitting, lazy chunks, source maps, and public-path dependencies.

- Prefer a programmatic bundler API if the CLI wrapper is missing.
- Alias framework singletons such as React/Vue to the repository root when nested dependencies could duplicate them.
- Convert imported assets to inline/data URLs at build time where practical.
- Compile the repository's actual style entry rather than approximating the story CSS.
- Preserve the original stylesheet cascade order. Base/library styles must precede the repository's theme/global overrides exactly as they do in Storybook.
- If the global style entry fails only because unrelated components contain broken asset paths, compile the smallest repository-authored style closure that includes the target's framework reset, library global/base styles, theme variables/global utilities, and every target style module in their original relative order. Do not hand-recreate the CSS. Record omitted global styles in the handoff.
- Do not rely on CDN scripts, remote fonts, Storybook manager assets, or a service worker.

The intermediate build should contain an HTML entry plus one JS bundle and zero or more CSS/assets. It does not need to be portable yet.

### 5. Pack the build into one HTML file

Run:

```bash
python3 "$SKILL_DIR/scripts/pack_html.py" \
  path/to/intermediate/index.html \
  path/to/output/story-name.html \
  --root path/to/intermediate
```

Set `SKILL_DIR` to this skill's directory. The packer uses only Python's standard library. It inlines local scripts, stylesheets, CSS imports, CSS URLs, images, media, icons, fonts, and source sets; removes `<base>` and incompatible CSP metadata; and safely escapes inline scripts.

Treat a missing referenced asset as a build error. Fix the build or path mapping rather than using `--allow-missing`, except when the missing resource is proven irrelevant.

### 6. Audit without browser tooling

Run both audits:

```bash
python3 "$SKILL_DIR/scripts/audit_html.py" path/to/output/story-name.html
python3 "$SKILL_DIR/scripts/audit_html.py" path/to/output/story-name.html --strict-network --fail-on-secrets
```

The first command must pass. For an offline artifact, the strict-network command must also pass. The audit checks active external resources, remaining file dependencies, CSS imports/URLs, module/chunk imports, workers, frames, forms, network APIs, and high-confidence embedded-secret patterns.

Also verify:

- the output is exactly one HTML file;
- the file contains the expected story title/text and requested mock fixtures;
- no source or lockfile changed unintentionally;
- the original story remains unmodified unless the user separately requested source changes.
- stylesheet order matches Storybook; do not validate only by checking that selectors exist;
- create a temporary computed-style contract for important target elements and states, containing exact expected values derived from repository styles or an existing user-provided Storybook screenshot. Check the contract in the artifact at runtime and expose failures in visible text/console. Typical properties include `font-weight`, `font-family`, border widths/styles/colors, box shadow, dimensions, spacing, colors, and disabled/selected/modal states.

Browser automation is optional only when the user separately asks for interactive browser QA. It is never required by this skill.

### 7. Deliver

Give the clickable HTML path, file size, the exact story export and args/mocks used, and short test instructions. State whether strict offline audit passed. Mention that some email/security systems block JavaScript-bearing HTML and that zipping the single file is a transport workaround.

## Failure boundaries

- If the story depends on a proprietary remote widget that cannot legally or technically be embedded, explain that exact dependency and ask whether a faithful local stub is acceptable.
- If the repository lacks a buildable component entry or required packages, report the missing local dependency; do not silently substitute a visual imitation.
- If an interaction fundamentally requires a backend, preserve the UI flow with an artifact-only fixture or clearly mark the artifact as network-dependent.
- Never claim full portability when either audit reports an unresolved active dependency.
