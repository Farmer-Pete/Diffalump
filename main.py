import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Iterable, cast

import click
from git import Repo
from unidiff import Hunk, PatchedFile, PatchSet

MAX_CHUNK_LINES = 100
CONTEXT_LINE_COUNT = 5


@dataclass
class FileChunk:
    file: PatchedFile
    hunks: list[str]


class DiffChunker:
    def __init__(self, patches: PatchSet):
        self.file_sizes: DefaultDict[tuple[str, str], int] = defaultdict(int)
        self.hunks_by_file: DefaultDict[tuple[str, str], list[list[str]]] = defaultdict(
            list
        )
        self.file_hashes: dict[tuple[str, str], PatchedFile] = dict()

        # Group file chunks by file
        for file_patch in patches:
            file_hash = (file_patch.source_file, file_patch.target_file)
            self.file_hashes[file_hash] = file_patch
            for chunk_size, chunk in self._chunk(file_patch):
                self.file_sizes[file_hash] += chunk_size
                self.hunks_by_file[file_hash].append([str(hunk) for hunk in chunk])

    def _chunk(self, file_patch: PatchedFile) -> Iterable[tuple[int, list[Hunk]]]:
        current_chunk_size = 0
        chunk: list[Hunk] = list()

        if file_patch.is_rename and not file_patch:
            # A plain rename with no other changes
            yield 0, []
            return

        for hunk in file_patch:
            hunk_size = max(
                sum(1 for line in hunk if line.is_added),
                sum(1 for line in hunk if line.is_removed),
            )

            if current_chunk_size and (
                current_chunk_size + hunk_size > MAX_CHUNK_LINES
            ):
                yield current_chunk_size, chunk
                current_chunk_size = 0
                chunk = list()

            current_chunk_size += hunk_size
            chunk.append(hunk)

        if chunk:
            yield current_chunk_size, chunk

    @property
    def chunks(self) -> Iterable[Iterable[FileChunk]]:
        small_diff_files: list[FileChunk] = list()
        small_diff_len = 0

        for patched_file, file_diff_size in sorted(
            self.file_sizes.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            if file_diff_size >= MAX_CHUNK_LINES // 4:
                for chunk in self.hunks_by_file[patched_file]:
                    yield (FileChunk(self.file_hashes[patched_file], chunk),)
            else:
                # Combine all small chunks together
                small_diff_files.extend(
                    FileChunk(self.file_hashes[patched_file], chunk)
                    for chunk in self.hunks_by_file[patched_file]
                )
                small_diff_len += file_diff_size
                if small_diff_len > MAX_CHUNK_LINES + (MAX_CHUNK_LINES // 4):
                    yield small_diff_files
                    small_diff_files = list()
                    small_diff_len = 0

        yield small_diff_files


class Diffalump:
    def __init__(self, output_dir: Path, prefix: str):
        self.output_dir = output_dir
        self.prefix = prefix

    def get_git_diff(
        self,
        directory: str,
        base: str,
        target: str,
        exclude: tuple[str, ...],
    ) -> PatchSet:
        repo = Repo(directory)
        diff_args = [f"{base}..{target}"]
        for path in exclude:
            diff_args.append(f":(exclude){path}")
        diff_text = repo.git.diff(
            *diff_args,
            unified=CONTEXT_LINE_COUNT,
            histogram=True,
        )
        return PatchSet(diff_text)

    def chunk_patchset(self, patch_set: PatchSet) -> int:
        index = 0
        for index, file_chunks in enumerate(DiffChunker(patch_set).chunks):
            output = self.output_dir / f"{self.prefix}__{index+1:03}.diff"
            with open(output, "w") as f:
                for file in file_chunks:
                    f.write(str(file.file.patch_info) + "\n")
                    for hunk in file.hunks:
                        f.write(hunk)
        return index + 1


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
    "--output-dir",
    type=click.Path(
        exists=False,
        file_okay=False,
        dir_okay=True,
        writable=True,
        path_type=Path,
    ),
    default=None,
    help="Output directory for chunk files (defaults to creating a temporary directory).",
)
@click.option(
    "-p",
    "--prefix",
    default=None,
    help="Prefix for output files (defaults to base_branch-target_branch).",
)
@click.option(
    "-e",
    "--exclude",
    multiple=True,
    help="Paths to exclude from the diff (can be specified multiple times)",
)
@click.argument("target_branch")
def main(
    directory: str,
    base_branch: str,
    output_dir: Path | None,
    prefix: str | None,
    exclude: tuple[str, ...],
    target_branch: str,
):
    """
    Diffalump - Intelligently chunk Git diffs for easier AI code review.

    Compares changes between two branches, demarcating  manageable chunks
    for the AI to review. Large files are split appropriately while small changes
    are combined together.
    """
    # Create output directory if not provided
    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp())

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create prefix if not provided
    if prefix is None:
        prefix = re.sub(
            r"__*",
            "_",
            f"{base_branch}-{target_branch}".translate(
                str.maketrans(
                    {
                        "/": "-",
                        " ": "_",
                    }
                )
            ),
        )

    app = Diffalump(output_dir, prefix)
    count = app.chunk_patchset(
        app.get_git_diff(
            directory,
            base_branch,
            target_branch,
            exclude,
        )
    )

    print(f"Wrote {count} chunk files to:", output_dir)


if __name__ == "__main__":
    cast(click.Command, main)()
