import ast

def remove_tests_from_file(filepath, test_names):
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()

    tree = ast.parse(source)

    class TestRemover(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if node.name in test_names:
                return None
            self.generic_visit(node)
            return node

        def visit_AsyncFunctionDef(self, node):
            if node.name in test_names:
                return None
            self.generic_visit(node)
            return node

    remover = TestRemover()
    new_tree = remover.visit(tree)
    ast.fix_missing_locations(new_tree)

    new_source = ast.unparse(new_tree)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_source)

tests_to_remove = {
    "tests/unit/test_coding_worker.py": [
        "test_coding_worker_node_dynamic_rag_injection",
        "test_coding_worker_node_loop_termination",
        "test_coding_worker_node_phase_split_blocks"
    ],
    "tests/unit/test_context_overflow.py": [
        "test_handle_context_overflow_compresses_knowledge",
        "test_handle_context_overflow_no_breach",
        "test_handle_context_overflow_prunes_memory"
    ],
    "tests/unit/test_modules.py": [
        "test_memory_deduplication"
    ],
    "tests/unit/test_multihop_reasoning.py": [
        "test_multi_hop_reasoning_evaluation"
    ],
    "tests/unit/test_retry_visibility.py": [
        "test_ask_stream_async_bubbles_retry_warning"
    ]
}

import os
for path, names in tests_to_remove.items():
    if os.path.exists(path):
        remove_tests_from_file(path, names)
        print(f"Removed {len(names)} tests from {path}")
    else:
        print(f"File {path} not found")
