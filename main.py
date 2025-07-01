import io
import itertools
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, Iterable, cast

import click
from git import Repo
from unidiff import PatchedFile, PatchSet
from unidiff.patch import Line

MAX_CHUNK_LINES = 100
CONTEXT_LINE_COUNT = 5


Chunk = tuple[Line, ...]


@dataclass
class FileChunk:
    file: PatchedFile
    lines: Chunk


def get_git_diff(directory: str, base: str, target: str) -> PatchSet:
    repo = Repo(directory)
    diff_text = repo.git.diff(f"{base}..{target}", unified=CONTEXT_LINE_COUNT)
    return PatchSet(diff_text)


def chunk_diff(
    patches: PatchSet,
) -> Iterable[Iterable[FileChunk]]:
    file_sizes: DefaultDict[tuple[str, str], int] = defaultdict(int)
    chunks_by_file: DefaultDict[tuple[str, str], list[Chunk]] = defaultdict(list)
    file_hashes: dict[tuple[str, str], PatchedFile] = dict()

    # Group file chunks by file and split large files into smaller chunks
    for file_patch in patches:
        file_hash = (file_patch.source_file, file_patch.target_file)
        file_hashes[file_hash] = file_patch
        for hunk in file_patch:
            file_sizes[file_hash] += hunk.source_length + hunk.target_length
            chunks_by_file[file_hash].extend(
                itertools.batched(list(hunk), MAX_CHUNK_LINES)
            )

    small_diff_files: list[FileChunk] = list()
    small_diff_len = 0

    for patched_file, file_diff_size in sorted(
        file_sizes.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        if file_diff_size >= MAX_CHUNK_LINES // 4:
            for chunks in chunks_by_file[patched_file]:
                yield (FileChunk(file_hashes[patched_file], chunks),)
        else:
            # Combine all small chunks together
            small_diff_files.extend(
                FileChunk(file_hashes[patched_file], chunk)
                for chunk in chunks_by_file[patched_file]
            )
            small_diff_len += file_diff_size
            if small_diff_len > MAX_CHUNK_LINES + (MAX_CHUNK_LINES // 4):
                yield small_diff_files
                small_diff_files = list()
                small_diff_len = 0

    yield small_diff_files


@click.command(name="diffalump")
@click.option(
    "-d",
    "--directory",
    default=".",
    help="Directory of the git repository (defaults to current directory)",
)
@click.option(
    "-b",
    "--base-branch",
    default="main",
    help="Base branch for comparison (defaults to main)",
)
@click.option(
    "-o",
    "--output",
    type=click.File("w"),
    default="-",
    help="Output file (defaults to stdout).",
)
@click.argument("target_branch")
def main(directory: str, base_branch: str, output: io.StringIO, target_branch: str):
    """
    Diffalump - Intelligently chunk Git diffs for easier AI code review.

    Compares changes between two branches, demarcating  manageable chunks
    for the AI to review. Large files are split appropriately while small changes
    are combined together.
    """
    diff = get_git_diff(directory, base_branch, target_branch)
    for file_chunks in chunk_diff(diff):
        guid = uuid.uuid4()
        output.write(("<" * 50) + f" START CHUNK: {guid}\n")
        for file in file_chunks:
            output.write(str(file.file) + "\n")
            for line in file.lines:
                output.write(str(line).rstrip() + "\n")
        output.write((">" * 50) + f" END CHUNK: {guid}\n")


if __name__ == "__main__":
    cast(click.Command, main)()
