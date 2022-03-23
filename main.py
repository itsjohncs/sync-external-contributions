#!/usr/bin/env python3

import collections
import datetime
import os
import re
import subprocess
import sys

import yaml

Commit = collections.namedtuple("Commit", ["project_id", "sha", "timestamp"])

SOURCE_LOG_RE = re.compile(
    r"^(?P<sha>[a-f0-9]+),(?P<email>[^,]+),(?P<timestamp>[^ ]+)$"
)


def get_commits_from_source(project_id, include_emails, git_root):
    # %H %ae %aI is hash, email, author date (in "strict" ISO 8601 format)
    process = subprocess.run(
        ["git", "log", "--format=%H,%ae,%aI"],
        capture_output=True,
        check=True,
        cwd=git_root,
        encoding="utf8"
    )

    for line in process.stdout.splitlines():
        match = SOURCE_LOG_RE.match(line)
        if not match:
            raise RuntimeError(f"Could not parse line...\n\n{line}")

        if match.group("email") in include_emails:
            yield Commit(
                project_id=project_id,
                sha=match.group("sha"),
                timestamp=datetime.datetime.fromisoformat(match.group("timestamp")),
            )


SYNCED_LOG_RE = re.compile(
    r"^(?P<timestamp>[^,]+),Synced from (?P<project_id>\w+):(?P<sha>[a-f0-9]+)$"
)


def get_synced_commits(git_root):
    process = subprocess.run(
        ["git", "log", "--format=%aI,%s"], capture_output=True, check=True, cwd=git_root,
        encoding="utf8"
    )

    for line in process.stdout.splitlines():
        match = SYNCED_LOG_RE.match(line)
        if match:
            yield Commit(
                project_id=match.group("project_id"),
                sha=match.group("sha"),
                timestamp=datetime.datetime.fromisoformat(match.group("timestamp")),
            )


def add_commit(git_root, commit):
    subprocess.run(
        [
            "git",
            "commit",
            "--allow-empty",
            f"--message=Synced from {commit.project_id}:{commit.sha}",
        ],
        check=True,
        cwd=git_root,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": commit.timestamp.isoformat(),
            "GIT_COMMIRTER_DATE": commit.timestamp.isoformat(),
        },
    )


def read_config(config_path):
    with open(config_path, "r", encoding="utf8") as config_file:
        return yaml.load(config_file, Loader=yaml.Loader)


def main(config_path):
    config = read_config(config_path)

    include_emails = config["include-emails"]

    source_commits = set()
    for project in config["projects"]:
        source_commits.update(
            get_commits_from_source(project["id"], include_emails, project["git-root"])
        )

    synced_commits = set(get_synced_commits(config["sync-repo"]))

    shas_to_remove = synced_commits - source_commits
    if shas_to_remove:
        raise NotImplementedError("Some commits have been removed.")

    assert {i.sha for i in source_commits - synced_commits} == {
        i.sha for i in source_commits
    } - {i.sha for i in synced_commits}
    for commit in source_commits - synced_commits:
        add_commit(config["sync-repo"], commit)


if __name__ == "__main__":
    main(sys.argv[1])
