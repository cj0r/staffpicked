# Contributing

Thanks for helping out. Bug reports, ideas and pull requests are all welcome.

## Reporting a bug or asking for a feature

Open an issue with the matching form. For a bug, include the StaffPicked version, your media server and its version, and the log of the run that went wrong (**Logs** in the web UI). Logs don't print API keys, but check before you paste.

Security problems go through [SECURITY.md](SECURITY.md), not an issue.

## Working on the code

StaffPicked uses only the Python standard library (3.11 or newer) and plain HTML, CSS and JavaScript with no build step, and it should stay that way so the image stays small with nothing to keep patched.

Run the web UI from a checkout:

```bash
python web/server.py          # http://localhost:9343, config in ./config
```

Run the tests from the repo root before opening a pull request:

```bash
python -m unittest discover -s tests -t .
```

They cover season windows, list files, the web UI's entry editor, the config files' KEY blocks, retries, backups, and whole syncs against a small fake Emby server (`tests/fake_emby.py`), from the command line and from the web UI, so they need no real server or API keys.

## Pull requests

- Keep each pull request to one change, with a test for new behavior or a fixed bug.
- Write settings, messages and docs in plain words for someone who isn't a developer.
- When a setting is added or changed, update the KEY block at the top of the matching `config/*.example` file and the user guide in `docs/`.
- Add a line to `CHANGELOG.md` under the next version.

By contributing you agree your work is released under the project's license, GPL-3.0.
