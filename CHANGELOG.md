# Changelog

## Unreleased

- Rewrite the README around the VRChat whitelist workflow, simplify Windows setup and remove leftover release planning.
- Extract whitelist rules, profile persistence, CSV loading and SFTP uploads into independently usable modules.
- Regenerate lists for every upload and duplicate check rather than reusing a stale preview.
- Snapshot upload inputs on the GUI thread and handle worker progress and dialogs through the Tkinter event loop.
- Diagnose empty exports, duplicate/blank headers, malformed rows, invalid UTF-8 and multiline cells.
- Add SFTP timeouts, connection-stage error messages and cleanup after failed authentication or transfers.
- Add automated regression tests and CI.

Known limitations: SFTP host keys are not verified; multi-file uploads have no rollback or cancellation. CSV data must be reloaded manually, and large exports can block the GUI during generation. Live server and EXE checks remain manual.
