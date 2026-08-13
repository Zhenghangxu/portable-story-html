# Framework adapters

Use the repository's installed versions and APIs. Keep all adapter files temporary.

## React

Prefer the installed Storybook `composeStory`/`composeStories` API so loaders, decorators, args, and render functions match Storybook. Import preview annotations when the installed API accepts them.

If composition is unavailable, render a small adapter:

```tsx
const args = { ...(meta.args ?? {}), ...(story.args ?? {}), ...overrides };
const Render = story.render ?? meta.render;
const node = Render ? Render(args, context) : React.createElement(meta.component, args);
```

Apply decorators in Storybook order and mount with the repository's installed React DOM API. Alias `react`, `react-dom`, and JSX runtimes to one root copy to prevent invalid-hook-call failures caused by nested component-library dependencies.

## Vue 3

Prefer `composeStory` from the installed Vue Storybook renderer. Otherwise create an app whose render component calls the story/meta render function or mounts `meta.component` with merged args. Reapply preview plugins, global components, provide/inject values, and theme classes.

Alias `vue` to one root copy and configure the bundler to inline assets and emit one chunk.

## Svelte

Use the installed Storybook composition utility when present. Otherwise instantiate the story/meta component with merged props in a temporary root. Import preview/global CSS explicitly. Disable dynamic imports and asset emission.

## Web Components / HTML

Call the story/meta render function with merged args, append the returned node/string to the root, and run relevant preview initializers. Bundle registration modules into the same script.

## Other renderers

Use the renderer package already configured by Storybook. Preserve CSF arg merging, decorators, render selection, preview globals, and style imports. If the repository uses Angular or another compiler-heavy renderer, prefer a minimal repository-native application entry over manually reconstructing generated component code.

## Decorator order

Use the installed Storybook composition API whenever decorator order is uncertain. For a manual adapter, wrap the story so the first decorator in the effective list is the outermost only if that matches the installed Storybook version; verify against its local implementation rather than relying on memory.

## Preview scope

Apply preview behavior required by the target, not unrelated site-wide initializers. A theme wrapper or provider is usually required; initialization of every carousel, form validator, navigation script, or analytics hook is not. If a global decorator mixes required presentation with unrelated side effects, reproduce the required wrapper/provider in the artifact entry and document the omitted side effects.

## Story modules with loaders or play functions

- Execute loaders only when their results can be made deterministic and local.
- Do not automatically execute `play`; it is test automation, not rendering. Reproduce only setup that is required for the initial visible state.
- Replace network loaders with artifact-only fixtures.
