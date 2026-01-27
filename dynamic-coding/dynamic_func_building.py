"""
Dynamic Function Runtime (Python)

Expected input (via stdin as JSON):
{
  "metadata": {
    "function_name": "example_fn",
    "timeout": 5
  },
  "code": "def handler(event, context): return {'ok': True}",
  "payload": {
    "foo": "bar"
  }
}
"""

import json
import signal
import sys
import traceback
from types import MappingProxyType

import requests

# =============================
# Configuration
# =============================

ALLOWED_DOMAINS = ("https://api.github.com", "https://jsonplaceholder.typicode.com")

ORCHESTRATOR_URL = "http://localhost:8000/execute"

DEFAULT_TIMEOUT = 5


# =============================
# Safety: Timeout
# =============================


class TimeoutException(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutException("Function execution timed out")


# =============================
# Platform APIs (Context)
# =============================


def http_request(method, url, headers=None, body=None, timeout=5):
    if not url.startswith(ALLOWED_DOMAINS):
        raise Exception(f"Domain not allowed: {url}")

    response = requests.request(
        method=method, url=url, headers=headers, json=body, timeout=timeout
    )
    return {
        "status": response.status_code,
        "headers": dict(response.headers),
        "body": response.json() if response.content else None,
    }


def call_function(function_name, payload):
    response = requests.post(
        f"{ORCHESTRATOR_URL}/{function_name}", json=payload, timeout=3
    )
    response.raise_for_status()
    return response.json()


def get_context():
    """
    Context object exposed to user function.
    Immutable to prevent tampering.
    """
    return MappingProxyType({"http": http_request, "call_function": call_function})


# =============================
# Execution Engine
# =============================


def execute_user_function(metadata, code, payload):
    # Setup timeout
    timeout = metadata.get("timeout", DEFAULT_TIMEOUT)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)

    try:
        # Restricted builtins
        safe_builtins = {
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "dict": dict,
            "list": list,
            "bool": bool,
            "print": print,
            "range": range,
            "Exception": Exception,
        }

        # Execution namespace
        user_globals = {"__builtins__": safe_builtins}
        user_locals = {}

        # Compile & execute user code
        exec(code, user_globals, user_locals)

        if "handler" not in user_locals:
            raise Exception(
                "User code must define a `handler(event, context)` function"
            )

        handler = user_locals["handler"]

        # Call handler
        result = handler(payload, get_context())

        return {"success": True, "result": result}

    except TimeoutException as e:
        return {"success": False, "error": str(e)}

    except Exception as e:
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}

    finally:
        signal.alarm(0)


# =============================
# Main Entrypoint
# =============================


def main():
    try:
        raw_input = sys.stdin.read()
        event = json.loads(raw_input)

        metadata = event.get("metadata", {})
        code = event["code"]
        payload = event.get("payload", {})

        response = execute_user_function(metadata, code, payload)

        print(json.dumps(response))

    except Exception as e:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": f"Runtime failure: {str(e)}",
                    "traceback": traceback.format_exc(),
                }
            )
        )


if __name__ == "__main__":
    main()
