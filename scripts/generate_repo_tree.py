import os

OUTPUT = "repo_tree.txt"

IGNORE = {
    ".git",
    "__pycache__",
    "node_modules",
    ".next",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "venv",
}


def scan_dir(root, prefix=""):
    tree_lines = []

    try:
        entries = [e for e in os.listdir(root) if e not in IGNORE]
    except Exception:
        return []

    entries.sort()

    for i, name in enumerate(entries):
        path = os.path.join(root, name)
        connector = "└── " if i == len(entries) - 1 else "├── "

        tree_lines.append(prefix + connector + name)

        if os.path.isdir(path):
            extension = "    " if i == len(entries) - 1 else "│   "
            tree_lines.extend(scan_dir(path, prefix + extension))

    return tree_lines


def generate_tree():
    root = "."
    print("Scanning repository...")

    tree = ["PROJECT FILE TREE", ""]
    tree.extend(scan_dir(root))

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(tree))

    print(f"Repo tree saved → {OUTPUT}")


if __name__ == "__main__":
    generate_tree()
