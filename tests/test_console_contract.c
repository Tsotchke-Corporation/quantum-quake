/**
 * @file test_console_contract.c
 * @brief Artifact validator for Quake console dump output.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int validate_condump_file(const char *path, char *error, size_t error_size)
{
    FILE *f;
    int ch;
    int prev = '\n';
    int saw_bytes = 0;

    f = fopen(path, "rb");
    if (!f) {
        snprintf(error, error_size, "could not open %s", path);
        return 0;
    }

    while ((ch = fgetc(f)) != EOF) {
        saw_bytes = 1;
        if (ch & 0x80) {
            snprintf(error, error_size, "non-ASCII byte 0x%02x", ch & 0xff);
            fclose(f);
            return 0;
        }
        if ((ch == '\n' || ch == '\r') && prev == ' ') {
            snprintf(error, error_size, "line has trailing spaces");
            fclose(f);
            return 0;
        }
        prev = ch;
    }
    fclose(f);

    if (saw_bytes && prev != '\n' && prev != '\r') {
        snprintf(error, error_size, "missing final newline");
        return 0;
    }

    return 1;
}

int main(void)
{
    const char *condump_artifact = "build/condump.txt";
    char error[128];
    FILE *f;

    f = fopen(condump_artifact, "wb");
    if (!f) {
        perror(condump_artifact);
        return 1;
    }
    fputs("Quantum Quake console dump\nline without trailing space\n", f);
    fclose(f);

    if (!validate_condump_file(condump_artifact, error, sizeof(error))) {
        fprintf(stderr, "valid condump rejected: %s\n", error);
        remove(condump_artifact);
        return 1;
    }

    f = fopen(condump_artifact, "wb");
    if (!f) {
        perror(condump_artifact);
        return 1;
    }
    fputs("bad trailing space \n", f);
    fclose(f);

    if (validate_condump_file(condump_artifact, error, sizeof(error))) {
        fprintf(stderr, "invalid trailing-space condump accepted\n");
        remove(condump_artifact);
        return 1;
    }

    f = fopen(condump_artifact, "wb");
    if (!f) {
        perror(condump_artifact);
        return 1;
    }
    fputc(0x80, f);
    fputc('\n', f);
    fclose(f);

    if (validate_condump_file(condump_artifact, error, sizeof(error))) {
        fprintf(stderr, "invalid high-bit condump accepted\n");
        remove(condump_artifact);
        return 1;
    }

    remove(condump_artifact);
    puts("Console condump artifact contract: PASSED");
    return 0;
}
