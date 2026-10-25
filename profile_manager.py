"""JSON profile persistence. Passwords are never part of a profile."""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from whitelist_rules import OutputRule

CONFIG_VERSION = 1

@dataclass
class SftpSettings:
    enabled: bool = False
    host: str = ""
    port: int = 22
    username: str = ""
    remote_path: str = ""


@dataclass
class Profile:
    profile_name: str = "New Profile"
    name_column: str = "Nickname"
    output_folder: str = "output"
    dedupe_names: bool = True
    sort_names: bool = True
    outputs: list[OutputRule] = field(default_factory=list)
    sftp: SftpSettings = field(default_factory=SftpSettings)


def load_profile(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    outputs = [OutputRule(**item) for item in raw.get("outputs", [])]
    sftp = SftpSettings(**raw.get("sftp", {}))
    profile = Profile(
        profile_name=raw.get("profile_name", "Loaded Profile"),
        name_column=raw.get("name_column", "Nickname"),
        output_folder=raw.get("output_folder", "output"),
        dedupe_names=raw.get("dedupe_names", True),
        sort_names=raw.get("sort_names", True),
        outputs=outputs,
        sftp=sftp,
    )
    return profile


def save_profile(path, profile):
    data = asdict(profile)
    data["config_version"] = CONFIG_VERSION
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
