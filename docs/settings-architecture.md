# Settings split (`config/settings/`)

**Context:** One `settings.py` mixes dev DB, secrets, and test DB. That makes it easy to run tests against real data or ship unsafe defaults.

**Action:** Replaced the single file with `base.py` + `local.py` + `test.py`. `local` and `test` do `from .base import *` then override only what differs (DB, `DEBUG`, etc.).

**Split boundaries:** Shared stuff (apps, middleware, templates, paths) stays in `base.py`. Per-environment stuff stays out of `base` when possible.

**REMINDER TO MYSELF** Set which module Django loads:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.local   # for dev
export DJANGO_SETTINGS_MODULE=config.settings.test    # for tests
```

If you forget, Django won’t load the right config. Alternatively, change the default in `manage.py` to `config.settings.local` so daily commands work without exporting (still use `test` in CI or when running the test runner).
