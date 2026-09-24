# Presentation — IoT and Smart Home Security

Slidev source of the T39 classroom talk.

From the repository root, after `pnpm install` once:

```bash
pnpm slides:dev      # live deck at http://localhost:3030
pnpm slides:build    # static site in presentation/dist/
pnpm slides:export   # PDF export (uses the Chromium that pnpm install downloads)
```

- `slides.md` — cover slide and section imports
- `slides/` — one file per section
- `public/` — figures; those reproduced from the two source papers remain their authors' copyright
- `style.css` — deck styles
