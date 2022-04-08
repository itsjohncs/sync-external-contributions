#!/usr/bin/env python3

import datetime
import os
import re
import subprocess
import sys

import yaml


class Commit:
    def __init__(self, project_id, sha, timestamp, sync_target_sha=None):
        self.project_id = project_id
        self.sha = sha
        self.timestamp = timestamp
        self.sync_target_sha = sync_target_sha

    def _to_tuple(self):
        return (self.project_id, self.sha, self.timestamp)

    def __hash__(self):
        return hash(self._to_tuple())

    def __eq__(self, other):
        return self._to_tuple() == other._to_tuple()


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
        encoding="utf8",
    )

    for line in process.stdout.splitlines():
        match = SOURCE_LOG_RE.match(line)
        if not match:
            raise RuntimeError(f"Could not parse line...\n\n{line}")

        if match.group("email") in include_emails:
            yield Commit(
                project_id=project_id,
                sha=match.group("sha"),
                timestamp=datetime.datetime.fromisoformat(
                    match.group("timestamp")
                ),
            )


SYNCED_LOG_RE = re.compile(
    r"^(?P<sync_target_sha>[^,]+),"
    r"(?P<timestamp>[^,]+),"
    r"Synced from (?P<project_id>\w+):(?P<sha>[a-f0-9]+)$"
)


def get_synced_commits(git_root):
    process = subprocess.run(
        ["git", "log", "--format=%H,%aI,%s"],
        capture_output=True,
        check=True,
        cwd=git_root,
        encoding="utf8",
    )

    for line in process.stdout.splitlines():
        match = SYNCED_LOG_RE.match(line)
        if match:
            yield Commit(
                project_id=match.group("project_id"),
                sha=match.group("sha"),
                timestamp=datetime.datetime.fromisoformat(
                    match.group("timestamp")
                ),
                sync_target_sha=match.group("sync_target_sha"),
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


def remove_commit(git_root, sha):
    subprocess.check_call(
        [
            "git",
            "rebase",
            "--no-stat",
            "--rebase-merges",
            "--onto",
            f"{sha}^",
            sha,
        ],
        cwd=git_root,
    )


def get_commit_summary(git_root, sha):
    return subprocess.check_output(
        ["git", "log", "--pretty=reference", f"{sha}^!"],
        encoding="utf-8",
        cwd=git_root,
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
            get_commits_from_source(
                project["id"], include_emails, project["git-root"]
            )
        )

    synced_commits = set(get_synced_commits(config["sync-repo"]))

    commits_to_remove = synced_commits - source_commits
    if commits_to_remove:
        project_id_to_git_root = {
            project["id"]: project["git-root"] for project in config["projects"]
        }

        print("Commits exist in the sync target that are not in any repo.")
        for commit in commits_to_remove:
            summary = get_commit_summary(
                project_id_to_git_root[commit.project_id], commit.sha
            ).strip()
            print(f"\t{summary}")
        answer = input("Remove these commits from the sync target (y/N)?: ")
        if answer != "y":
            sys.exit("Quitting.")

        for commit in commits_to_remove:
            remove_commit(config["sync-repo"], commit.sync_target_sha)

    assert {i.sha for i in source_commits - synced_commits} == {
        i.sha for i in source_commits
    } - {i.sha for i in synced_commits}
    for commit in source_commits - synced_commits:
        add_commit(config["sync-repo"], commit)


if __name__ == "__main__":
    main(sys.argv[1])
