import functools
import inspect
import os
import sys
import threading
import time

DEBUGGER_PATH = os.path.dirname(__file__)
print(f"{DEBUGGER_PATH= }")


def debug_runtime(func):

    state = threading.local()

    def init_state():
        if not hasattr(state, "depth"):
            state.depth = 0
            state.stack = []
            state.locals_map = {}
            state.tree = {"name": func.__name__, "children": []}
            state.node_stack = [state.tree]

    def tracer(frame, event, arg):

        init_state()

        func_name = frame.f_code.co_name
        args = frame.f_locals
        indent = "│   " * (state.depth - 1)

        filename = frame.f_code.co_filename
        if not filename.startswith(DEBUGGER_PATH):
            return tracer

        if event == "call":
            node = {"name": func_name, "start": time.time(), "children": [], "vars": {}}
            args_string = ", ".join([f"{k}={v}" for k, v in args.items()])
            # print(f"{args_string= }")
            parent = state.node_stack[-1]
            parent["children"].append(node)

            state.node_stack.append(node)
            state.locals_map[frame] = {}
            state.depth += 1

            print(f"{indent}├── CALL {func_name}({args_string})")

        elif event == "line":
            current = frame.f_locals
            previous = state.locals_map.get(frame, {})
            for k, v in current.items():
                if k not in previous:
                    print(f"{indent}│   CREATE {k} ← {v}")

                elif previous[k] != v:
                    print(f"{indent}│   UPDATE {k}: {previous[k]} → {v}")

            state.locals_map[frame] = current.copy()

        elif event == "return":
            state.depth -= 1
            indent = "│   " * state.depth

            node = state.node_stack.pop()
            node["return"] = arg
            node["duration"] = round(time.time() - node["start"], 6)

            print(f"{indent}└── RETURN {func_name} → {arg} ({node['duration']}s)")

        return tracer

    async def async_wrapper(*args, **kwargs):

        sys.settrace(tracer)

        try:
            result = await func(*args, **kwargs)
        finally:
            sys.settrace(None)

        print("\nExecution Tree:")
        print_tree(state.tree)

        return result

    def sync_wrapper(*args, **kwargs):

        sys.settrace(tracer)

        try:
            result = func(*args, **kwargs)
        finally:
            sys.settrace(None)

        # print("\nExecution Tree:")
        # print_tree(state.tree)

        return result

    if inspect.iscoroutinefunction(func):
        return functools.wraps(func)(async_wrapper)

    return functools.wraps(func)(sync_wrapper)


def print_tree(node, indent=0):

    space = "  " * indent

    if "duration" in node:
        print(f"{space}- {node['name']} (time={node['duration']}s)")
    else:
        print(f"{space}- {node['name']}")

    for child in node.get("children", []):
        print_tree(child, indent + 1)


def helper(a, b=None):
    total = a + (b or 0)
    return total


def compute(x, y=None):
    value = helper(x, y)
    return value


@debug_runtime
def main_api(user_id, data=None):

    result = compute(user_id, data)

    final = result * 2
    return final


main_api(10)
