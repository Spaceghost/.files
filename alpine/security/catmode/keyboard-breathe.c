/* Early Apple SMC keyboard breathing, independent of Python and the desktop. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <math.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t running = 1;

static void stop(int signo) { (void)signo; running = 0; }

static double clock_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1000000000.0;
}

static int read_number(const char *path) {
    FILE *file = fopen(path, "r");
    int value = -1;
    if (file) {
        if (fscanf(file, "%d", &value) != 1) value = -1;
        fclose(file);
    }
    return value;
}

static bool write_text(const char *path, const char *text) {
    int fd = open(path, O_WRONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return false;
    size_t length = strlen(text);
    ssize_t written = write(fd, text, length);
    close(fd);
    return written == (ssize_t)length;
}

static bool write_number(const char *path, int value) {
    char text[32];
    snprintf(text, sizeof(text), "%d\n", value);
    return write_text(path, text);
}

static bool worker_holds_light(const char *path) {
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return false;
    bool held = flock(fd, LOCK_EX | LOCK_NB) != 0 && errno == EWOULDBLOCK;
    close(fd);
    return held;
}

static bool session_alive(const char *pattern) {
    glob_t matches = {0};
    bool alive = false;
    if (glob(pattern, 0, NULL, &matches) == 0) {
        for (size_t i = 0; i < matches.gl_pathc && !alive; ++i) {
            struct stat st;
            struct sockaddr_un address = {.sun_family = AF_UNIX};
            const char *path = matches.gl_pathv[i];
            if (strlen(path) >= sizeof(address.sun_path) || lstat(path, &st) != 0
                    || !S_ISSOCK(st.st_mode)) continue;
            memcpy(address.sun_path, path, strlen(path) + 1);
            int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
            if (fd < 0) continue;
            alive = connect(fd, (struct sockaddr *)&address, sizeof(address)) == 0;
            close(fd);
        }
    }
    globfree(&matches);
    return alive;
}

int main(int argc, char **argv) {
    const char *led = "/sys/class/leds/smc::kbd_backlight";
    const char *runtime = "/run/user/1000";
    const char *lock_path = "/run/oldbook-keyboard-breathe.lock";
    for (int i = 1; i < argc; ++i) {
        if (i + 1 < argc && strcmp(argv[i], "--led-dir") == 0) led = argv[++i];
        else if (i + 1 < argc && strcmp(argv[i], "--runtime-dir") == 0) runtime = argv[++i];
        else if (i + 1 < argc && strcmp(argv[i], "--lock") == 0) lock_path = argv[++i];
        else {
            fprintf(stderr, "usage: %s [--led-dir PATH] [--runtime-dir PATH] [--lock PATH]\n", argv[0]);
            return 2;
        }
    }
    char brightness[4096], maximum_path[4096], trigger[4096], worker[4096], sway[4096];
    if (strlen(led) > 4000 || strlen(runtime) > 3900) return 2;
    snprintf(brightness, sizeof(brightness), "%s/brightness", led);
    snprintf(maximum_path, sizeof(maximum_path), "%s/max_brightness", led);
    snprintf(trigger, sizeof(trigger), "%s/trigger", led);
    snprintf(worker, sizeof(worker), "%s/oldbook/keyboard-backlight.run.lock", runtime);
    snprintf(sway, sizeof(sway), "%s/sway-ipc.*.sock", runtime);
    int lock = open(lock_path, O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB) != 0) {
        fprintf(stderr, "keyboard-breathe: another worker owns the light, or lock unavailable\n");
        if (lock >= 0) close(lock);
        return 1;
    }
    struct sigaction action = {.sa_handler = stop};
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGHUP, &action, NULL);
    bool handed_off = false, yielding = false, owned = false;
    int original = 0, previous = -1;
    double started = clock_seconds(), next_probe = 0;
    const struct timespec tick = {.tv_sec = 0, .tv_nsec = 33333333};
    while (running) {
        double now = clock_seconds();
        if (now >= next_probe) {
            bool session = session_alive(sway);
            bool desktop = worker_holds_light(worker);
            if (!session) handed_off = false;
            if (desktop && session) handed_off = true;
            yielding = desktop || handed_off;
            next_probe = now + 0.25;
        }
        if (yielding) {
            owned = false;
            previous = -1;
        } else {
            int maximum = read_number(maximum_path);
            if (maximum > 0 && maximum <= 65535) {
                if (!owned) {
                    original = read_number(brightness);
                    if (original < 0 || !write_text(trigger, "none\n")) {
                        nanosleep(&tick, NULL);
                        continue;
                    }
                    owned = true;
                    started = now;
                }
                double wave = (1.0 - cos((now - started) * 6.283185307179586 / 6.0)) / 2.0;
                int value = (int)lround(maximum * 0.45 * (0.12 + 0.88 * wave));
                if (value < 1) value = 1;
                if (value != previous) {
                    if (!write_number(brightness, value)) {
                        fprintf(stderr, "keyboard-breathe: brightness write failed\n");
                        close(lock);
                        return 1;
                    }
                    previous = value;
                }
            } else {
                owned = false;
            }
        }
        nanosleep(&tick, NULL);
    }
    if (owned && !worker_holds_light(worker)) (void)write_number(brightness, original);
    close(lock);
    return 0;
}
