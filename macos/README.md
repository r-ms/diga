# diga.app

`launcher.c` and `Info.plist` make a minimal app bundle around diga, so macOS asks for the
microphone, Input Monitoring and Accessibility in diga's name instead of "Python".

The launcher starts the real diga (`Contents/Resources/run`) as a child process and stays its
parent: macOS holds the app that started a process responsible for what it does, so the
permissions belong to `io.github.diga`. It asks for Input Monitoring and Accessibility
itself — macOS lists an app in those panes only when the app's own executable asks. Running Python directly — or `exec`-ing it — would make
the process Python itself.

The Homebrew formula builds it (`brew install r-ms/tools/diga`) and runs it as the service:

```sh
cc -O2 -framework ApplicationServices -o diga.app/Contents/MacOS/diga launcher.c
cp Info.plist diga.app/Contents/Info.plist
printf '#!/bin/sh\nexec /path/to/diga "$@"\n' > diga.app/Contents/Resources/run
codesign --force --sign - --identifier io.github.diga diga.app
```

`Info.plist` carries no diga version on purpose: an unchanged bundle keeps the same signature,
so the permissions survive upgrades.
