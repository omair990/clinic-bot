# Browser end-to-end tests

Playwright tests that drive the admin panel in a real browser — the parts pure-Python
tests can't reach (client-side JS: the guided clinic-data editor, row add/remove, weekday
checkboxes, the hidden-field sync, the actual form submit).

## clinic_editor.spec.js

Verifies the **hybrid clinic-data editor** (`app/templates/tenant_edit.html`) saves
correctly: fills the guided forms, adds a service/doctor/FAQ, ticks weekday boxes, submits,
then reloads and asserts the data persisted through the server's validate+normalize path
(including that a typed price comes back as a JSON **number**).

## Run

```bash
bash e2e/run.sh
```

`run.sh` is self-contained: it creates a throwaway local Postgres DB, seeds a tenant, starts
the app on `:8099`, drives the editor in the **system Google Chrome** (no Playwright browser
download — `channel: "chrome"`), then tears it all down. **Production is never touched.**

Capture a screenshot: `SCREENSHOT=/tmp/edit.png bash e2e/run.sh`

### Requirements
- Local Postgres with `createdb`/`dropdb` on `PATH`
- The project virtualenv (`.venv`) with Python deps installed
- Node.js and Google Chrome installed
- Pages use SSE, so the spec waits on `load` (never `networkidle`).

`node_modules/` is git-ignored; `run.sh` installs the `playwright` npm package on first run.
