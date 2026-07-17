import logging
from typing import Tuple

from src.tools.coding_tools import execute_command

logger = logging.getLogger("RAG.CodeValidation")

def find_first_error(node):
    if node.type == 'ERROR' or node.is_missing:
        return node
    if getattr(node, 'has_error', False):
        for child in node.children:
            if getattr(child, 'has_error', False):
                err = find_first_error(child)
                if err:
                    return err
    return None

def validate_syntax(code_content: str, filename: str) -> Tuple[bool, str]:
    """
    Validates Python and JS/JSX/TS/TSX syntax using Tree-sitter AST parsing.
    """
    logger.info(f"Validating syntax for: {filename}")
    
    language_name = None
    lower_name = filename.lower()
    if lower_name.endswith(".py"):
        language_name = "python"
    elif lower_name.endswith(".js") or lower_name.endswith(".jsx"):
        language_name = "javascript"
    elif lower_name.endswith(".ts") or lower_name.endswith(".tsx"):
        language_name = "typescript"

    if not language_name:
        logger.info(f"Skipping compilation syntax check for non-compilable file: {filename}")
        return True, "Skipping compilation check for non-compilable file."

    try:
        import tree_sitter
        lang_obj = None
        
        if language_name == "python":
            import tree_sitter_python
            lang_obj = tree_sitter.Language(tree_sitter_python.language())
        elif language_name == "javascript":
            import tree_sitter_javascript
            lang_obj = tree_sitter.Language(tree_sitter_javascript.language())
        elif language_name == "typescript":
            import tree_sitter_typescript
            if lower_name.endswith(".tsx"):
                lang_obj = tree_sitter.Language(tree_sitter_typescript.language_tsx())
            else:
                lang_obj = tree_sitter.Language(tree_sitter_typescript.language_typescript())
                
        parser = tree_sitter.Parser(lang_obj)
        tree = parser.parse(code_content.encode("utf-8"))
        
        if tree.root_node.has_error:
            err_node = find_first_error(tree.root_node)
            if err_node:
                line = err_node.start_point[0] + 1
                col = err_node.start_point[1]
                err_msg = f"Tree-sitter Syntax Error: Broken or missing syntax '{err_node.type}' at line {line}, column {col} in {filename}"
                logger.warning(err_msg)
                return False, err_msg
            else:
                err_msg = f"Tree-sitter Syntax Error: Unknown syntax issue in {filename}"
                logger.warning(err_msg)
                return False, err_msg
                
        return True, "Syntax compilation successful."
    except Exception as e:
        err_msg = f"Unexpected tree-sitter compilation error: {e}"
        logger.error(err_msg)
        return False, err_msg


def validate_tests(test_command: str) -> Tuple[bool, str]:
    """
    Runs unit tests through execute_command and checks for success.
    """
    logger.info(f"Executing test validation: {test_command}")
    res = execute_command(test_command)
    
    # Analyze output for failures/errors
    res_lower = res.lower()
    
    # Check if command failed or raised NameError/SyntaxError
    if "error" in res_lower or "failed" in res_lower or "failures" in res_lower:
        # Check if it still exited with code 0 (which is unlikely if there's failure)
        if "[command exited with status 0]" in res_lower:
            # Succeeded despite warning keyword
            return True, res
        return False, res
        
    return True, res
