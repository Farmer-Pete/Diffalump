import io
from itertools import zip_longest
from pathlib import Path
from tempfile import TemporaryDirectory
from unidiff import PatchSet
from main import DiffChunker, Diffalump


def test_diff_chunker_chunks_properly():
    with open("tests/input.txt", "r") as file:
        chunker = DiffChunker(PatchSet(file))
        assert chunker.file_sizes == {
            ("c/.gitignore", "w/.gitignore"): 3,
            ("c/README.md", "w/README.md"): 1,
            ("c/main.py", "w/main.py"): 45,
            ("c/prompt.txt", "w/prompt.md"): 0,
            ("c/pyproject.toml", "w/pyproject.toml"): 1,
            ("c/uv.lock", "w/uv.lock"): 45,
        }
        assert {
            key: sum(len(chunk) for chunk in chunker.hunks_by_file[key])
            for key in chunker.file_sizes
        } == {
            ("c/.gitignore", "w/.gitignore"): 1,
            ("c/README.md", "w/README.md"): 1,
            ("c/main.py", "w/main.py"): 2,
            ("c/prompt.txt", "w/prompt.md"): 0,
            ("c/pyproject.toml", "w/pyproject.toml"): 1,
            ("c/uv.lock", "w/uv.lock"): 3,
        }


def test_diff_chunker_lists_chunks_properly():
    with open("tests/input.txt") as file:
        chunk_lists = list(DiffChunker(PatchSet(file)).chunks)
        assert [len(list(chunks)) for chunks in chunk_lists] == [1, 1, 4]
        assert [
            sum(len(chunk.hunks) for chunk in chunks) for chunks in chunk_lists
        ] == [2, 3, 3]


def test_main_produces_the_expected_output(tmp_path):
    with open("tests/input.txt") as input_file:
        path = Path(tmp_path)
        Diffalump(path, "test").chunk_patchset(PatchSet(input_file))
        for generated, expected in zip_longest(
            sorted(path.iterdir()),
            sorted(Path("tests/").glob("output_*.txt")),
        ):
            assert open(generated).read() == open(expected).read()
