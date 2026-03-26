from __future__ import annotations

import copy
import posixpath
import re
from pathlib import PurePosixPath

import nbformat
from nbformat import NotebookNode


# =============================================================================
# HARD-CODED CONFIG
# =============================================================================

REPO = "snow0369/qiskit_handson_260330"
BRANCH = "main"  # better: pin to a tag or commit SHA

# Notebook files in the order you want them merged.
NOTEBOOKS = [
    "0_setup-and-intro.ipynb",
    "2_vqe_tutorial_revised.ipynb",
    "advanced-1_PrecalculatedHamiltonians.ipynb",
    "advanced-2_CustomTargetBackend.ipynb",
]

# Output merged notebook.
OUTPUT_NOTEBOOK = "combined_colab.ipynb"

# Files that must exist in the Colab runtime.
FILES_TO_DOWNLOAD = [
    "utils.py",
    "linear_h_chains_bk_2q_reduced.json",
    "requirements.txt"
]

# Optional requirements file in the repo.
REQUIREMENTS_FILE = None # Already included in 0_setup-and-intro.ipynb

# Where downloaded files should go inside Colab.
# Use "." if your code expects files in the current working directory.
# Use something like "project_support" if you want them isolated.
DOWNLOAD_DIR = "."

# If True, add DOWNLOAD_DIR to sys.path in the setup cell.
ADD_DOWNLOAD_DIR_TO_SYS_PATH = True

# If True, preserve subdirectories under DOWNLOAD_DIR when downloading files.
# Example:
#   data/molecule.json -> ./data/molecule.json
# instead of flattening to ./molecule.json
PRESERVE_DOWNLOAD_TREE = True

# If True, remove outputs from all code cells.
CLEAR_OUTPUTS = False

# If True, insert a top-level TOC markdown cell.
INSERT_TOC = True


# =============================================================================
# HELPERS
# =============================================================================

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif"}


def github_raw_url(repo: str, branch: str, path: str) -> str:
    path = str(PurePosixPath(path))
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def slugify_heading(text: str) -> str:
    """
    Approximate markdown heading anchor generation.
    Good enough for notebook internal links.
    """
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def resolve_repo_relative_path(notebook_repo_path: str, target_path: str) -> str:
    notebook_dir = posixpath.dirname(str(PurePosixPath(notebook_repo_path)))
    if target_path.startswith("/"):
        return target_path.lstrip("/")
    return posixpath.normpath(posixpath.join(notebook_dir, target_path))


def is_external_url(path: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", path))


def is_data_uri(path: str) -> bool:
    return path.startswith("data:")


def strip_optional_title_from_markdown_target(target: str) -> str:
    """
    Handles common markdown link/image patterns like:
        path/to/file.png "title"
        <path/to/file.png>
    """
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        return target[1:-1].strip()
    if " " in target:
        return target.split(" ", 1)[0].strip()
    return target


def should_rewrite_image_asset(path: str) -> bool:
    if is_external_url(path) or is_data_uri(path):
        return False

    clean_path = path.split("#", 1)[0].split("?", 1)[0].strip()
    suffix = PurePosixPath(clean_path).suffix.lower()
    return suffix in IMAGE_EXTENSIONS


def is_notebook_link(path: str) -> bool:
    if is_external_url(path) or is_data_uri(path):
        return False
    suffix = PurePosixPath(path.split("#", 1)[0].split("?", 1)[0]).suffix.lower()
    return suffix == ".ipynb"


def make_download_destination(repo_path: str, download_dir: str) -> str:
    repo_path = str(PurePosixPath(repo_path))
    if PRESERVE_DOWNLOAD_TREE:
        return str(PurePosixPath(download_dir) / PurePosixPath(repo_path))
    return str(PurePosixPath(download_dir) / PurePosixPath(repo_path).name)


def first_heading_from_notebook(nb: NotebookNode, fallback: str) -> str:
    heading_pattern = re.compile(r"^\s*#\s+(.+?)\s*$", flags=re.MULTILINE)
    for cell in nb.cells:
        if cell.cell_type == "markdown":
            m = heading_pattern.search(cell.source)
            if m:
                return m.group(1).strip()
    return fallback


def prefix_headings(markdown: str, prefix: str) -> str:
    """
    Prefix markdown headings to reduce collisions across merged notebooks.
    """
    lines = markdown.splitlines()
    out = []
    for line in lines:
        m = re.match(r"^(#{1,6}\s+)(.+)$", line)
        if m:
            out.append(f"{m.group(1)}{prefix}{m.group(2)}")
        else:
            out.append(line)
    return "\n".join(out)


def rewrite_markdown(
    markdown: str,
    *,
    repo: str,
    branch: str,
    notebook_repo_path: str,
    ipynb_anchor_map: dict[str, str],
) -> str:
    """
    Rewrites:
      1) markdown image links -> GitHub raw URLs
      2) HTML img src -> GitHub raw URLs
      3) links to sibling ipynb files -> internal anchors
    """
    # -------------------------------------------------------------------------
    # Markdown images: ![alt](path)
    # -------------------------------------------------------------------------
    md_img_pattern = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)")

    def md_img_repl(match: re.Match) -> str:
        alt = match.group("alt")
        raw_target = strip_optional_title_from_markdown_target(match.group("path"))

        if not should_rewrite_image_asset(raw_target):
            return match.group(0)

        resolved = resolve_repo_relative_path(notebook_repo_path, raw_target)
        url = github_raw_url(repo, branch, resolved)
        return f"![{alt}]({url})"

    markdown = md_img_pattern.sub(md_img_repl, markdown)

    # -------------------------------------------------------------------------
    # HTML images: <img src="path" ...>
    # -------------------------------------------------------------------------
    html_img_pattern = re.compile(
        r"""<img\b(?P<before>[^>]*?)\bsrc\s*=\s*(?P<quote>["']?)(?P<path>[^\s"'<>]+)(?P=quote)(?P<after>[^>]*)>""",
        flags=re.IGNORECASE | re.VERBOSE,
    )

    def html_img_repl(match: re.Match) -> str:
        raw_target = match.group("path").strip()

        if not should_rewrite_image_asset(raw_target):
            return match.group(0)

        resolved = resolve_repo_relative_path(notebook_repo_path, raw_target)
        url = github_raw_url(repo, branch, resolved)

        before = match.group("before")
        after = match.group("after")

        return f'<img{before}src="{url}"{after}>'

    markdown = html_img_pattern.sub(html_img_repl, markdown)

    # -------------------------------------------------------------------------
    # Standard markdown links: [text](path)
    # Must come after image rewrite, because images also use markdown syntax.
    # -------------------------------------------------------------------------
    md_link_pattern = re.compile(r"(?<!!)\[(?P<text>[^\]]+)\]\((?P<path>[^)]+)\)")

    def md_link_repl(match: re.Match) -> str:
        text = match.group("text")
        raw_target = strip_optional_title_from_markdown_target(match.group("path"))

        if not is_notebook_link(raw_target):
            return match.group(0)

        resolved = resolve_repo_relative_path(notebook_repo_path, raw_target)
        anchor = ipynb_anchor_map.get(resolved)
        if anchor is None:
            return match.group(0)

        return f"[{text}](#{anchor})"

    markdown = md_link_pattern.sub(md_link_repl, markdown)
    return markdown


def build_setup_cell_source(
    *,
    repo: str,
    branch: str,
    files_to_download: list[str],
    pip_requirements: str | None,
    download_dir: str,
    add_download_dir_to_sys_path: bool,
) -> str:
    lines = [
        "# Colab setup",
        "from pathlib import Path",
        "from urllib.request import urlretrieve",
        "import sys",
        "",
        f'DOWNLOAD_DIR = Path("{download_dir}")',
        "DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)",
        "",
        "def _download(url: str, dst: Path) -> None:",
        "    dst.parent.mkdir(parents=True, exist_ok=True)",
        "    print(f'Downloading {url} -> {dst}')",
        "    urlretrieve(url, dst)",
        "",
    ]

    if add_download_dir_to_sys_path:
        lines += [
            "resolved_download_dir = str(DOWNLOAD_DIR.resolve())",
            "if resolved_download_dir not in sys.path:",
            "    sys.path.insert(0, resolved_download_dir)",
            "",
        ]

    for repo_path in files_to_download:
        raw_url = github_raw_url(repo, branch, repo_path)
        dst = make_download_destination(repo_path, download_dir)
        lines.append(f'_download("{raw_url}", Path("{dst}"))')

    if pip_requirements:
        req_url = github_raw_url(repo, branch, pip_requirements)
        req_dst = make_download_destination(pip_requirements, download_dir)
        lines += [
            "",
            f'_download("{req_url}", Path("{req_dst}"))',
            f'%pip install -r "{req_dst}"',
        ]

    return "\n".join(lines) + "\n"


def clear_cell_outputs(cell: NotebookNode) -> None:
    if cell.cell_type == "code":
        cell["outputs"] = []
        cell["execution_count"] = None


# =============================================================================
# MAIN CONVERSION
# =============================================================================

def main() -> None:
    # -------------------------------------------------------------------------
    # Read all notebooks first so we can build ipynb -> anchor mapping
    # -------------------------------------------------------------------------
    loaded_notebooks: list[tuple[str, NotebookNode]] = []
    ipynb_anchor_map: dict[str, str] = {}

    for nb_path in NOTEBOOKS:
        with open(nb_path, "r", encoding="utf-8") as f:
            nb = nbformat.read(f, as_version=4)

        title = first_heading_from_notebook(
            nb,
            fallback=PurePosixPath(nb_path).stem.replace("_", " ").replace("-", " ").title(),
        )
        anchor = slugify_heading(title)
        ipynb_anchor_map[str(PurePosixPath(nb_path))] = anchor
        loaded_notebooks.append((nb_path, nb))

    # -------------------------------------------------------------------------
    # Create merged notebook
    # -------------------------------------------------------------------------
    merged = nbformat.v4.new_notebook()
    merged.metadata = {
        "colab": {
            "name": PurePosixPath(OUTPUT_NOTEBOOK).name,
            "provenance": [],
            "include_colab_link": True,
        },
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
        },
    }

    merged.cells = []

    # -------------------------------------------------------------------------
    # Title / TOC
    # -------------------------------------------------------------------------
    if INSERT_TOC:
        toc_lines = ["# Combined notebook", "", "## Contents", ""]
        for nb_path, nb in loaded_notebooks:
            title = first_heading_from_notebook(
                nb,
                fallback=PurePosixPath(nb_path).stem.replace("_", " ").replace("-", " ").title(),
            )
            anchor = ipynb_anchor_map[str(PurePosixPath(nb_path))]
            toc_lines.append(f"- [{title}](#{anchor})")
        merged.cells.append(nbformat.v4.new_markdown_cell("\n".join(toc_lines)))

    # -------------------------------------------------------------------------
    # Insert one setup cell near the top
    # -------------------------------------------------------------------------
    setup_source = build_setup_cell_source(
        repo=REPO,
        branch=BRANCH,
        files_to_download=FILES_TO_DOWNLOAD,
        pip_requirements=REQUIREMENTS_FILE,
        download_dir=DOWNLOAD_DIR,
        add_download_dir_to_sys_path=ADD_DOWNLOAD_DIR_TO_SYS_PATH,
    )
    setup_cell = nbformat.v4.new_code_cell(setup_source)
    setup_cell.metadata["tags"] = ["colab-setup"]
    merged.cells.append(setup_cell)

    # -------------------------------------------------------------------------
    # Merge notebooks
    # -------------------------------------------------------------------------
    for nb_index, (nb_path, nb) in enumerate(loaded_notebooks, start=1):
        section_title = first_heading_from_notebook(
            nb,
            fallback=PurePosixPath(nb_path).stem.replace("_", " ").replace("-", " ").title(),
        )
        section_anchor = ipynb_anchor_map[str(PurePosixPath(nb_path))]

        # Section separator
        merged.cells.append(
            nbformat.v4.new_markdown_cell(
                f"# {section_title}\n"
                f"<a id=\"{section_anchor}\"></a>\n\n"
                f"_Source: `{nb_path}`_"
            )
        )

        for cell in nb.cells:
            new_cell = copy.deepcopy(cell)

            # Optionally clear outputs
            if CLEAR_OUTPUTS:
                clear_cell_outputs(new_cell)

            # Rewrite markdown content
            if new_cell.cell_type == "markdown":
                # Prefix headings inside each notebook section to reduce collisions.
                # We skip level-1 headings, because we already inserted a section heading above.
                lines = new_cell.source.splitlines()
                if lines and re.match(r"^\s*#\s+", lines[0]):
                    lines = lines[1:]
                    new_cell.source = "\n".join(lines).lstrip()

                new_cell.source = rewrite_markdown(
                    new_cell.source,
                    repo=REPO,
                    branch=BRANCH,
                    notebook_repo_path=nb_path,
                    ipynb_anchor_map=ipynb_anchor_map,
                )

            merged.cells.append(new_cell)

    # -------------------------------------------------------------------------
    # Write output
    # -------------------------------------------------------------------------
    with open(OUTPUT_NOTEBOOK, "w", encoding="utf-8") as f:
        nbformat.write(merged, f)

    print(f"Wrote merged Colab notebook: {OUTPUT_NOTEBOOK}")


if __name__ == "__main__":
    main()