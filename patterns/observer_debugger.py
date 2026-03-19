import functools
import inspect
import os
import sys
import threading
import time
import uuid
from datetime import datetime

DEBUGGER_PATH = os.path.dirname(__file__)


def debug_runtime(func):

    state = threading.local()

    def init_state():
        if not hasattr(state, "depth"):
            state.depth = 0
            state.locals_map = {}
            state.logs = []
            state.start_time = time.time()
            state.status = "success"
            state.process_id = f"req_{uuid.uuid4().hex[:8]}"

    def safe_repr(value):
        try:
            r = repr(value)
            if len(r) > 80:
                return r[:80] + "..."
            return r
        except:
            return "<unrepr>"

    def log(line):
        state.logs.append(line)

    def tracer(frame, event, arg):

        init_state()

        filename = frame.f_code.co_filename
        if not filename.startswith(DEBUGGER_PATH):
            return tracer

        func_name = frame.f_code.co_name
        indent = "│   " * (state.depth - 1)

        if event == "call":
            args = frame.f_locals
            arg_names = frame.f_code.co_varnames[: frame.f_code.co_argcount]

            args_string = ", ".join(
                f"{name}={safe_repr(args.get(name))}" for name in arg_names
            )

            state.depth += 1
            state.locals_map[id(frame)] = {}

            log(f"{indent}├── CALL {func_name}({args_string})")

        elif event == "line":
            current = frame.f_locals
            previous = state.locals_map.get(id(frame), {})

            for k, v in current.items():
                prev_v = previous.get(k, object())

                if k not in previous:
                    log(f"{indent}│   CREATE {k} ← {safe_repr(v)}")

                elif id(prev_v) != id(v) or prev_v != v:
                    log(f"{indent}│   UPDATE {k}: {safe_repr(prev_v)} → {safe_repr(v)}")

            state.locals_map[id(frame)] = current.copy()

        elif event == "return":
            state.depth -= 1
            indent = "│   " * state.depth

            log(f"{indent}└── RETURN {func_name} → {safe_repr(arg)}")

        elif event == "exception":
            exc_type, exc_value, _ = arg

            state.status = "error"

            log(f"{indent}│   ERROR {exc_type.__name__}({safe_repr(exc_value)})")

        return tracer

    def finalize_log(entry_name):

        duration = round(time.time() - state.start_time, 6)

        record = {
            "process_id": state.process_id,
            "timestamp": datetime.now().isoformat(),
            "duration": duration,
            "entry": entry_name,
            "status": state.status,
            "log": "\n".join(state.logs),
        }

        return record

    async def async_wrapper(*args, **kwargs):

        sys.settrace(tracer)

        try:
            result = await func(*args, **kwargs)
        except Exception:
            raise
        finally:
            sys.settrace(None)

        record = finalize_log(func.__name__)
        print(record)

        return result

    def sync_wrapper(*args, **kwargs):

        sys.settrace(tracer)
        result = None

        try:
            result = func(*args, **kwargs)

        except Exception as e:
            state.status = "error"
            raise

        finally:
            sys.settrace(None)
            record = finalize_log(func.__name__)
            print(record)

        return result

    if inspect.iscoroutinefunction(func):
        return functools.wraps(func)(async_wrapper)

    return functools.wraps(func)(sync_wrapper)


def helper(a, b=None):
    total = a + (b or 0)
    total = total / 0
    return total


def compute(x, y=None):
    try:
        value = helper(x, y)
    except Exception as e:
        pass
    return value


@debug_runtime
def main_api(user_id, data=None):

    result = compute(user_id, data)

    final = result * 2
    return final


main_api(10)
