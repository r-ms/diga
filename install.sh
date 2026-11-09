#!/bin/sh
# Install diga with one command:
#   curl -LsSf https://raw.githubusercontent.com/r-ms/diga/main/install.sh | sh
#
# Installs uv if needed, then diga with Russian, English, Portuguese and the rest of Europe,
# downloads the models (~3.5 GB, once) and starts diga at login.
# Next to this script there may be a diga-*.whl (installed instead of the latest code) and a
# glossary.yaml (copied to ~/.config/diga if you have none). DIGA_SOURCE overrides where diga
# comes from: a wheel, a directory or a git URL.
set -eu

say() { printf '\033[1m%s\033[0m\n' "$*"; }

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "diga needs a Mac with Apple Silicon (M1 or newer)." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (Python package manager)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  PATH="$HOME/.local/bin:$PATH"
fi

# Look next to the script only when it is run as a file (sh install.sh), never when piped from
# curl: then "here" would be whatever directory you happen to be in.
here="" bundled=""
case "$0" in
  *install.sh) here=$(cd "$(dirname "$0")" && pwd) ;;
esac
if [ -n "$here" ]; then
  bundled=$(ls "$here"/diga-*.whl 2>/dev/null | tail -n 1 || true)
  if [ -z "$bundled" ] && [ -f "$here/pyproject.toml" ] && grep -q '^name = "diga"' "$here/pyproject.toml"; then
    bundled="$here"  # run from a clone of the repository: install that code
  fi
fi
# a package or clone next to this script wins over the repository
source="${DIGA_SOURCE:-${bundled:-git+https://github.com/r-ms/diga}}"
if [ -e "$source" ]; then  # a local wheel or source directory
  spec="diga[ru,parakeet] @ file://$(cd "$(dirname "$source")" && pwd)/$(basename "$source")"
elif [ "${source#git+}" != "$source" ]; then
  spec="diga[ru,parakeet] @ $source"
else
  spec="$source[ru,parakeet]"
fi
say "Installing diga…"
uv tool install --force --python 3.12 "$spec"
uv tool update-shell >/dev/null 2>&1 || true
PATH="$HOME/.local/bin:$PATH"

glossary="$HOME/.config/diga/glossary.yaml"
if [ -n "$here" ] && [ -f "$here/glossary.yaml" ] && [ ! -f "$glossary" ]; then  # your terms
  mkdir -p "$(dirname "$glossary")"
  cp "$here/glossary.yaml" "$glossary"
  say "Glossary copied to $glossary"
fi

say "Downloading the models (once, about 3.5 GB)…"
diga models --download default

if [ "${DIGA_AUTOSTART:-1}" = "1" ]; then
  say "Starting diga at login…"
  diga autostart install
fi

say "Done. Hold the right ⌘ key and speak."
echo "Open a new terminal window to use the diga command (diga doctor, diga -v)."
echo "macOS will ask for Microphone, Accessibility and Input Monitoring the first time —"
echo "allow them, then check with: diga doctor"
