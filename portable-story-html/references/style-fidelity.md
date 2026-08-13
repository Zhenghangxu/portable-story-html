# Style fidelity without browser automation

Portability checks do not prove visual fidelity. Validate the cascade and key computed values separately.

## Preserve the cascade

Follow the original style entry's import order. A common safe order is:

1. framework variables/overrides;
2. framework reset/components;
3. component-library global/base styles;
4. component-library atoms/molecules used by the story;
5. application theme variables and global utilities;
6. application typography/base/theme component overrides;
7. artifact-only canvas/layout rules.

Do not import only the target theme partial if it uses `@extend` classes defined in global styles. Do not place a library base partial after a theme override: later `border: none`, `font-weight`, or reset rules can silently win even though every expected selector is present.

## Computed-style contract

Add a small artifact-only runtime assertion after mount. It must not change styling. Example:

```js
const contract = [
  {
    selector: ".btn--primary",
    expected: {
      fontWeight: "700",
      borderTopWidth: "2px",
      borderTopStyle: "solid",
      boxShadow: "rgb(0, 0, 0) 4px 4px 0px 0px",
    },
  },
];
```

For each selector, use `getComputedStyle`, compare the declared properties, and set a visible `data-portable-style-audit="passed|failed"` attribute on the root. On failure, render or append a concise `<pre>` report and throw/log an error.

Derive expected values from the repository's compiled Storybook styles, source variables/mixins, existing snapshots, or a screenshot supplied by the user. Do not invent expectations.

For interactive states, create deterministic checks only when they can be triggered locally: disabled args, selected controls, open modal classes, hover/focus via artifact-only test buttons, or explicit fixture states. Remove test-only state after checking when it would interfere with QA.

## Static fallback

When runtime execution cannot be exercised, at minimum inspect compiled rule order and specificity for each contract selector. Confirm the final winning declarations occur after conflicting library/reset declarations. Report that validation as static rather than claiming pixel fidelity.
