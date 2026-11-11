// diga.app's executable. It starts the real diga (Contents/Resources/run, a script) as a CHILD
// and stays its parent: macOS attributes a child's microphone, keyboard and accessibility use
// to the app that launched it, so permission prompts and System Settings say "diga" instead of
// "Python". (exec would not do: the process would become Python itself.)
//
// It also asks for Input Monitoring and Accessibility itself, before starting diga: macOS
// lists an app in those panes only when the app's own executable asks. Asked from the Python
// child, the request was silently dropped and the panes stayed empty (the microphone, asked
// from the child, did work).
#include <ApplicationServices/ApplicationServices.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;
static pid_t child = 0;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

int main(int argc, char **argv) {
    char exe[PATH_MAX], real[PATH_MAX], run[PATH_MAX];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real)) {
        fprintf(stderr, "diga: cannot find my own path\n");
        return 1;
    }
    char *slash = strrchr(real, '/');  // .../diga.app/Contents/MacOS/diga
    if (!slash) return 1;
    *slash = '\0';
    snprintf(run, sizeof(run), "%s/../Resources/run", real);

    char **args = calloc((size_t)argc + 1, sizeof(char *));
    if (!args) return 1;
    args[0] = run;
    for (int i = 1; i < argc; i++) args[i] = argv[i];

    if (!CGPreflightListenEventAccess()) CGRequestListenEventAccess();  // see the hotkey
    if (!CGPreflightPostEventAccess()) CGRequestPostEventAccess();      // type into other apps

    setenv("DIGA_APP", "1", 1);  // so diga names itself, not Python, in its permission hints
    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);
    int err = posix_spawn(&child, run, NULL, NULL, args, environ);
    if (err != 0) {
        fprintf(stderr, "diga: cannot start %s: %s\n", run, strerror(err));
        return 1;
    }
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return 128 + WTERMSIG(status);
}
