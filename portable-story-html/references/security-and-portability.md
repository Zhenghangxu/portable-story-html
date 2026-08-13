# Security and portability

## Offline boundary

An offline artifact must not initiate HTTP(S), WebSocket, EventSource, beacon, frame, authentication, analytics, telemetry, or form-submit traffic. Block these APIs in the temporary entry before application initialization when practical.

Do not block a browser primitive by simple assignment when the property may be read-only. Prefer `Object.defineProperty` with a local throwing function and a guarded assignment fallback.

After all network primitives are guarded before application initialization, add `<meta name="portable-story-network" content="blocked">` to the intermediate HTML. The auditor treats network API names inside bundled dependencies as dormant only when this explicit marker exists. Never add the marker to a network-dependent artifact.

## Secrets

Never embed real values from story args, environment variables, `.env` files, storage, browser sessions, or build-time defines. Replace them with empty values or obvious inert fixtures. A public-looking key in an existing story is still excluded unless the user explicitly authorizes embedding it.

Avoid copying source maps because they expose source text, comments, paths, and build-time constants.

## Redirects and forms

External `window.location`, anchor, and form destinations break offline testing and can leak QA input. Point completion to the artifact's own pathname with query/hash state, or intercept it and render an in-file completion panel.

## Fonts and licenses

Inline only fonts/assets already licensed for the repository's distribution context. If a remote font cannot be redistributed, use a repository-local licensed font or a documented system-font fallback. Do not fetch it at runtime.

## False positives in static auditing

Minified framework bundles may contain documentation/license URLs or dormant endpoint defaults. These string literals are not active dependencies. The audit distinguishes active HTML/CSS resources from network-capable JavaScript patterns, but review warnings in context. Do not suppress an actual fetch, XHR, worker, frame, form, or dynamic-import path.

## File transport

The final artifact may be blocked by email gateways because it contains JavaScript. Zip the one HTML file for transport; this does not change its one-file runtime requirement after extraction.
