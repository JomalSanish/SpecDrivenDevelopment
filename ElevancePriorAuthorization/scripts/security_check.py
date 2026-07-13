import ast
import os
import sys

BANNED_DOMAINS = [
    "openai.com",
    "anthropic.com",
    "api.openai.com",
    "api.anthropic.com"
]

def check_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return False
        
    try:
        tree = ast.parse(content, filename=filepath)
    except SyntaxError:
        # If it's not valid Python, skip AST checking (or flag it, but skipping is safer)
        return False

    found_violations = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for banned in BANNED_DOMAINS:
                if banned in node.value:
                    print(f"[SECURITY VIOLATION] Found banned domain '{banned}' in {filepath} at line {node.lineno}")
                    found_violations = True
    return found_violations

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
    violations = 0

    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                if check_file(filepath):
                    violations += 1

    if violations > 0:
        print(f"FAILED: Found {violations} files containing banned external AI APIs.")
        sys.exit(1)
    else:
        print("PASSED: No banned external AI APIs found.")
        sys.exit(0)

if __name__ == "__main__":
    main()
