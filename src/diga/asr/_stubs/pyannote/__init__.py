"""Empty stand-in for ``pyannote`` — NOT the real package.

GigaAM's ``modeling_gigaam.py`` imports pyannote only inside ``get_pipeline()`` (file-based
VAD), which diga never calls. ``transformers`` still checks, by scanning the file's text, that
a top-level ``pyannote`` package is importable when the model is loaded. This empty package
satisfies that check without pulling in the heavy ``pyannote.audio``. It is put on
``sys.path`` only when the real pyannote is not installed.
"""
