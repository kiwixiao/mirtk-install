"""Tab-completion for interactive ``input()`` prompts.

Shell-level completion (argcomplete) only works while typing the
``mirtk-*`` command line. Once the pipeline is running and asks questions
via ``input()``, Tab does nothing unless ``readline`` is configured with a
completer. ``enable_path_completion()`` wires up filesystem-path completion
so users can Tab-complete files and directories at those prompts.

It degrades gracefully: if ``readline`` is unavailable (e.g. some minimal
environments) or stdin is not a TTY (non-interactive / scripted runs), it
does nothing.
"""

import glob
import os
import sys

_ENABLED = False


def _complete_path(text, state):
    """readline completer that completes filesystem paths."""
    expanded = os.path.expanduser(text)
    matches = [
        m + (os.sep if os.path.isdir(m) else "")
        for m in glob.glob(expanded + "*")
    ]
    return matches[state] if state < len(matches) else None


def enable_path_completion():
    """Enable Tab completion of file/dir paths at ``input()`` prompts.

    Safe to call more than once and safe to call in non-interactive runs.
    """
    global _ENABLED
    if _ENABLED:
        return
    # Nothing to complete against an interactive prompt that isn't a TTY.
    if not sys.stdin.isatty():
        return
    try:
        import readline
    except ImportError:
        return

    # Treat only whitespace as word breaks so the whole path token (including
    # '/' and '~') is handed to the completer, not just the last segment.
    readline.set_completer_delims(" \t\n")
    readline.set_completer(_complete_path)

    # libedit (macOS default) uses a different bind syntax than GNU readline.
    if "libedit" in (getattr(readline, "__doc__", "") or ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")

    _ENABLED = True
