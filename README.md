# Discord Role Whitelist Generator

I built this to maintain multiple VRChat world whitelists from Discord roles. Manually sorting members into tier and verification lists was tedious, especially when the same export needed to feed several worlds. This desktop app lets me keep those rules in a profile and regenerate the text files from the next member export.

Issues and ideas are welcome, particularly examples of exports or workflows that do not work well yet. Please remove member data and connection details before sharing examples.

![Discord Role Whitelist Generator](app%20screenshot.png)

## Run on Windows

Install Python 3.10 or newer with **Add Python to PATH** enabled, download or clone this repository, then double-click `Run_Discord_Whitelist_Generator.bat`. The launcher installs the dependencies and opens the app.

For a separate environment, run these commands in the repository folder:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python discord_role_whitelist_generator.py
```

To build a Windows EXE, run `build_exe.bat`; the result goes in `dist/`. Linux/macOS can run the Python entry point with the dependencies installed and Tkinter available, but Windows is the primary platform.

## Export and generate

Add [MemberList](https://discord.com/discovery/applications/674885857458651161) to your Discord server with permission to view members and roles. Run `/server filetype csv` and download the export.

1. Load the CSV and choose the output name column, usually `Nickname`.
2. Add output rules or load a JSON profile.
3. Preview the lists and check for names shared across output files.
4. Generate local `.txt` files, or enable SFTP and upload them.
5. Save your profile to reuse the rules next time.

Each rule supports **must have**, **any one of**, and **must not have** roles. Names can be sorted and deduplicated. Output names are cleaned for Windows and forced to `.txt`; local generation asks before overwriting existing files. Upload regenerates from the currently loaded CSV and current rules, independently of the preview.

## CSV and rule examples

The export needs a header row, a name column and one column per role. A nonblank role cell means the member has that role, including values such as `0` or `False`. Role headings are matched exactly. Blank names are skipped.

| User | ID | Nickname | 18+ verified | Copper tier | Silver tier |
| --- | --- | --- | --- | --- | --- |
| example_user | 123 | ExampleUser | 18+ verified | Copper tier | |
| another_user | 456 | AnotherUser | 18+ verified | | Silver tier |

For `Copper_Tier.txt`, require both `Copper tier` and `18+ verified`, and exclude `==NOT AGE VERIFIED==`. Only members satisfying all those conditions are included. A role missing from the CSV counts as absent, so check your role headings when changing exports.

Try `examples/example_members.csv` with `examples/example_profile.json`. My `examples/mellish_profile_no_secrets.json` contains rules for `Lead_Tier.txt`, `Copper_Tier.txt`, `Silver_Tier.txt` and `Verified_18_Plus.txt`, without private server details.

## Security and SFTP

Passwords are requested for each upload and are never saved in profiles. Profiles can contain the host, port, username and remote path, so review them before sharing. Do not put passwords, private connection details or real member exports in source control. A private local `user_secrets.json` is ignored by Git, but the app does not read it automatically.

Uploads write the current lists to the output folder and replace the corresponding remote files. The remote directory must already exist. Connection errors identify the upload stage and give checks for authentication, DNS, timeouts and permissions.

**Current security limitation:** the SFTP connection encrypts traffic but does not verify the server host key. Use it only with a server and network you trust until known-host verification is implemented.

## Current limitations

- CSV exports are loaded manually; this does not sync Discord roles automatically. Reload the CSV after changing it on disk.
- Role detection treats columns other than `User`, `ID` and the selected name column as possible roles. Review the detected list for other export metadata.
- Names are plain text, not verified VRChat account IDs. Duplicate names are compared exactly, including case.
- Uploads run in the background, but CSV loading and generation can pause the interface for large exports.
- An interrupted multi-file upload can leave a partially updated remote set. There is no rollback or upload cancellation.
- Automated tests cover rules, CSV parsing, profiles and mocked uploads; live SFTP servers and packaged EXEs still need manual checks.

## Development

```bat
python -m unittest discover -s tests -v
```

The GUI entry point is `discord_role_whitelist_generator.py`. Matching and filename rules live in `whitelist_rules.py`, CSV parsing in `csv_loader.py`, profile persistence in `profile_manager.py`, and blocking network work in `sftp_uploader.py`. The GUI receives worker events through a queue polled by Tkinter.

Use specific commit messages describing the behavior changed, and add real changes to [CHANGELOG.md](CHANGELOG.md). Preserve existing history.

If you would like to support my VRChat tools and community projects, you can find me on [Patreon](https://www.patreon.com/Mellish_Penthouse).
