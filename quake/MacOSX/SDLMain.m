/*   SDLMain.m - main entry point for our Cocoa-ized SDL app
       Initial Version: Darrell Walisser <dwaliss1@purdue.edu>
       Non-NIB-Code & other changes: Max Horn <max@quendi.de>

    Feel free to customize this file to suit your needs
*/

#if defined(SDL_FRAMEWORK) || defined(NO_SDL_CONFIG)
#if defined(USE_SDL2)
#import <SDL2/SDL.h>
#else
#import <SDL/SDL.h>
#endif
#else
#import "SDL.h"
#endif
#import "SDLMain.h"
#import <sys/param.h> /* for MAXPATHLEN */
#import <unistd.h>
#import "SDLApplication.h"
#import <stdio.h>

int    gArgc;
char  **gArgv;
BOOL   gFinderLaunch;
BOOL   gCalledAppMainline = FALSE;

static void QGE_LauncherProbe(const char *target,
                              const char *phase,
                              const char *path,
                              const char *result,
                              int argc)
{
    fprintf(stderr,
            "QGE launcher probe target=%s symbol=QGE_LauncherProbe phase=%s path=%s result=%s finder=%d argc=%d\n",
            target ? target : "unknown",
            phase ? phase : "runtime",
            path ? path : "macos_app_launcher",
            result ? result : "unknown",
            gFinderLaunch ? 1 : 0,
            argc);
    fflush(stderr);
}

/* The main class of the application, the application's delegate */
@implementation SDLMain

/* Set the working directory to the .app's parent directory */
- (void) setupWorkingDirectory:(BOOL)shouldChdir
{
    if (shouldChdir)
    {
        char parentdir[MAXPATHLEN];
		CFURLRef url = CFBundleCopyBundleURL(CFBundleGetMainBundle());
		CFURLRef url2 = CFURLCreateCopyDeletingLastPathComponent(0, url);
		if (CFURLGetFileSystemRepresentation(url2, true, (UInt8 *)parentdir, MAXPATHLEN)) {
	        assert ( chdir (parentdir) == 0 );   /* chdir to the binary app's parent */
		}
		CFRelease(url);
		CFRelease(url2);
	}

}

/* Called when the internal event loop has just started running */
- (void) applicationDidFinishLaunching: (NSNotification *) note
{
    int status;

    QGE_LauncherProbe("SDLMain", "applicationDidFinishLaunching",
                      "macos_app_launcher", "sdl_main", gArgc);

    /* Set the working directory to the .app's parent directory */
    [self setupWorkingDirectory:gFinderLaunch];

    /* Hand off to main application code */
    gCalledAppMainline = TRUE;
    status = SDL_main (gArgc, gArgv);

    /* We're done, thank you for playing */
    exit(status);
}
@end


#ifdef main
#  undef main
#endif


static int IsRootCwd()
{
    char buf[MAXPATHLEN];
    char *cwd = getcwd(buf, sizeof (buf));
    return (cwd && (strcmp(cwd, "/") == 0));
}

static int IsFinderLaunch(const int argc, char **argv)
{
    /* -psn_XXX is passed if we are launched from Finder, SOMETIMES */
    if ( (argc >= 2) && (strncmp(argv[1], "-psn", 4) == 0) ) {
        QGE_LauncherProbe("IsFinderLaunch", "argv",
                          "macos_app_launcher", "finder_psn", argc);
        return 1;
    } else if ((argc == 1) && IsRootCwd()) {
        /* we might still be launched from the Finder; on 10.9+, you might not
        get the -psn command line anymore. If there's no
        command line, and if our current working directory is "/", it
        might as well be a Finder launch. */
        QGE_LauncherProbe("IsFinderLaunch", "cwd",
                          "macos_app_launcher", "finder_root_cwd", argc);
        return 1;
    }
    QGE_LauncherProbe("IsFinderLaunch", "argv",
                      "macos_app_launcher", "direct_args", argc);
    return 0;  /* not a Finder launch. */
}

/* Main entry point to executable - should *not* be SDL_main! */
int main (int argc, char **argv)
{
    QGE_LauncherProbe("SDLMain", "main",
                      "macos_app_launcher", "enter", argc);
    QGE_LauncherProbe("SDLApplication", "principal_class",
                      "macos_app_launcher", "delegated", argc);

    /* Copy the arguments into a global variable */
    if (IsFinderLaunch(argc, argv)) {
        gArgv = (char **) SDL_malloc(sizeof (char *) * 2);
        gArgv[0] = argv[0];
        gArgv[1] = NULL;
        gArgc = 1;
        gFinderLaunch = YES;
    } else {
        int i;
        gArgc = argc;
        gArgv = (char **) SDL_malloc(sizeof (char *) * (argc+1));
        for (i = 0; i <= argc; i++)
            gArgv[i] = argv[i];
        gFinderLaunch = NO;
    }

    NSApplicationMain (argc, (const char**) argv);
    return 0;
}
