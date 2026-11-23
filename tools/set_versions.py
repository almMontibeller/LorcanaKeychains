"""Find saved revisions by their whole number, including status suffixes."""

import re

VERSION_DIRECTORY = re.compile(r'v([0-9]{2,})(?:_(?:approved|printed))?')


def saved_versions(set_directory):
    revisions = []
    for directory in set_directory.iterdir():
        match = VERSION_DIRECTORY.fullmatch(directory.name)
        if match and directory.is_dir():
            revisions.append((int(match[1]), directory))
    return [directory for _, directory in sorted(revisions)]


def version_directory(set_directory, version):
    for directory in saved_versions(set_directory):
        if directory.name.partition('_')[0] == version:
            return directory
    return set_directory / version


def saved_project(set_directory, version):
    directory = version_directory(set_directory, version)
    stem = f'{set_directory.name}_{version}'
    canonical = directory / f'{stem}.3mf'
    printed = directory / f'{stem}_printed.3mf'
    return printed if not canonical.is_file() and printed.is_file() else canonical
