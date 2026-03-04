# WOOHWAHAE — Codex Renewal (Core-Only)

## Mission
Align target pages to the visual/content standard of `website/about/index.html` without changing global design tokens.

## Non-Negotiable Rules
1. Do not edit `website/about/index.html`.
2. Do not edit `website/assets/css/style.css`.
3. Do not edit `website/index.html`.
4. Preserve all component markers exactly.
5. Keep existing JS behavior (ids/data-attrs/event hooks) intact.

## Target Scope (Only)
1. `website/_pages/archive/controls.html`
2. `website/_pages/practice/body.html`
3. `website/practice/atelier.html`
4. `website/practice/direction.html`
5. `website/practice/contact.html`
6. `website/404.html`

## Core Design Constraints
- No gradients, shadows, icons, decorative borders.
- Monochrome base (`--text` on `--bg`).
- Typography only through existing tokens/classes.
- Section labels use `001.` numeric rhythm where appropriate.
- Preserve tone policy:
  - Practice pages: 합니다체
  - Archive context: 한다체

## Safe Workflow
1. Read `website/about/index.html` pattern only as reference.
2. Edit only the target scope files above.
3. Rebuild generated sections/components:
   - `python3 core/scripts/build.py --components --bust`
4. Validate:
   - `python3 core/system/visual_validator.py`
5. Stage only explicit files (never `git add website/`):
   - `git add website/_pages/archive/controls.html website/_pages/practice/body.html website/practice/atelier.html website/practice/direction.html website/practice/contact.html website/404.html`
6. Commit:
   - `git commit -m "style: about 기준 핵심 페이지 정렬"`

## Guardrail
Never stage:
- `website/archive/essay-010-work-and-essence/proto_v4.html`
- unrelated pre-existing dirty files
