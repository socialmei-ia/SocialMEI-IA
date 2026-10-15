# Frontend instructions

- `socialmei-app.html` is the principal application entry.
- Keep Vanilla HTML/CSS/JavaScript unless a separate migration is approved.
- Do not batch-add modules/async/defer; script order and globals still matter.
- Keep transport/config in stores/helpers; never hardcode AWS URLs in renderers.
- Distinguish UI state, local preferences, demo/local data and remote business data.
- Do not silently persist failed remote business writes locally.
- Search all references before renaming IDs, classes, storage keys, data attributes or globals.
- Reuse the existing design system; avoid large final override blocks.
- Large visual additions use prototype-first.
- Test Light/Dark, desktop/mobile, keyboard/focus/dialogs and reduced motion.
- UI copy PT-BR; technical identifiers English.
