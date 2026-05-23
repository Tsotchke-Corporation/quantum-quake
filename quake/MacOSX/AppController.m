/*
Copyright (C) 2007-2008 Kristian Duske

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

*/
#import "AppController.h"
#import "ScreenInfo.h"
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
#import <stdio.h>

NSString *FQPrefCommandLineKey = @"CommandLine";
NSString *FQPrefFullscreenKey = @"Fullscreen";
NSString *FQPrefScreenModeKey = @"ScreenMode";

static void QGE_LauncherProbe(const char *target,
                              const char *phase,
                              const char *path,
                              const char *result)
{
    fprintf(stderr,
            "QGE launcher probe target=%s symbol=QGE_LauncherProbe phase=%s path=%s result=%s\n",
            target ? target : "unknown",
            phase ? phase : "runtime",
            path ? path : "macos_app_launcher",
            result ? result : "unknown");
    fflush(stderr);
}

@interface AppController ()
- (void)launchQuakeUsingLauncherControls:(BOOL)useLauncherControls;
@end

@implementation AppController

+(void) initialize {
    NSMutableDictionary *defaults = [NSMutableDictionary dictionary];
    QGE_LauncherProbe("AppController", "initialize",
                      "macos_app_launcher", "defaults_registered");
    
    [defaults setObject:@"" forKey:FQPrefCommandLineKey];
    [defaults setObject:[NSNumber numberWithBool:YES] forKey:FQPrefFullscreenKey];
    [defaults setObject:[NSNumber numberWithInt:0] forKey:FQPrefScreenModeKey];
    
    [[NSUserDefaults standardUserDefaults] registerDefaults:defaults];
}

- (BOOL)application:(NSApplication *)application shouldSaveApplicationState:(NSCoder *)coder {
    (void)application;
    (void)coder;
    return NO;
}

- (BOOL)application:(NSApplication *)application shouldRestoreApplicationState:(NSCoder *)coder {
    (void)application;
    (void)coder;
    return NO;
}

- (BOOL)applicationSupportsSecureRestorableState:(NSApplication *)application {
    (void)application;
    return NO;
}

- (id)init {
    int i;
#ifndef USE_SDL2
    int j;
    int flags;
    int bpps[3] = {32, 24, 16};
    SDL_PixelFormat format;
    SDL_Rect **modes;
#endif
    ScreenInfo *info;

    self = [super init];
    if (!self)
        return nil;

    QGE_LauncherProbe("AppController", "init",
                      "macos_app_launcher", "created");

    arguments = [[QuakeArguments alloc] initWithArguments:gArgv + 1 count:gArgc - 1];
    screenModes = [[NSMutableArray alloc] init];
    [screenModes addObject:@"Default or command line arguments"];

    if ([arguments argument:@"-nolauncher"] != nil) {
        QGE_LauncherProbe("ScreenInfo", "display_modes",
                          "nolauncher", "intentional_skip");
        QGE_LauncherProbe("sender", "launcher_controls",
                          "nolauncher", "intentional_skip");
        return self;
    }

    if (SDL_InitSubSystem(SDL_INIT_VIDEO) == -1)
        return self;
    
#if defined(USE_SDL2)
    {
        const int sdlmodes = SDL_GetNumDisplayModes(0);
        for (i = 0; i < sdlmodes; i++)
        {
            SDL_DisplayMode mode;
            if (SDL_GetDisplayMode(0, i, &mode) == 0)
            {
                info = [[ScreenInfo alloc] initWithWidth:mode.w height:mode.h bpp:SDL_BITSPERPIXEL(mode.format)];
                [screenModes addObject:info];
                [info release];
            }
        }
    }
#else
    flags = SDL_OPENGL | SDL_FULLSCREEN;
    format.palette = NULL;
    
    for (i = 0; i < 3; i++) {
        format.BitsPerPixel = bpps[i];
        modes = SDL_ListModes(&format, flags);

        if (modes == (SDL_Rect **)0 || modes == (SDL_Rect **)-1)
            continue;

        for (j = 0; modes[j]; j++) {
            info = [[ScreenInfo alloc] initWithWidth:modes[j]->w height:modes[j]->h bpp:bpps[i]];
            [screenModes addObject:info];
            [info release];
        }
    }
#endif

    SDL_QuitSubSystem(SDL_INIT_VIDEO);
    return self;
}

- (NSArray *)screenModes {
    return screenModes;
}

#ifndef MAC_OS_X_VERSION_10_13
#define NSControlStateValueOff NSOffState
#define NSControlStateValueOn NSOnState
#endif
- (void)awakeFromNib {
    [launcherWindow setRestorable:NO];

    if ([arguments count] > 0) {
        [paramTextField setStringValue:[arguments description]];
        if ([arguments argument:@"-window"] != nil)
            [fullscreenCheckBox setState:NSControlStateValueOff];
    } else {
		NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
        [paramTextField setStringValue:[defaults stringForKey:FQPrefCommandLineKey]];
        
        BOOL fullscreen = [defaults boolForKey:FQPrefFullscreenKey];
        [fullscreenCheckBox setState:fullscreen ? NSControlStateValueOn : NSControlStateValueOff];
        
        int screenModeIndex = [defaults integerForKey:FQPrefScreenModeKey];
        [screenModePopUp selectItemAtIndex:screenModeIndex];
    }
}

- (void)applicationDidFinishLaunching:(NSNotification *)aNotification {
    QGE_LauncherProbe("AppController", "applicationDidFinishLaunching",
                      "macos_app_launcher", "ready");
	if ([arguments argument:@"-nolauncher"] != nil) {
		[arguments removeArgument:@"-nolauncher"];
		[self launchQuakeUsingLauncherControls:NO];
	} else {
        [launcherWindow center];
		[launcherWindow makeKeyAndOrderFront:self];
	}
}

- (IBAction)changeScreenMode:(id)sender {
    int index = [screenModePopUp indexOfSelectedItem];
    [fullscreenCheckBox setEnabled:index != 0];
}

- (IBAction)launchQuake:(id)sender {
    (void)sender;
    QGE_LauncherProbe("sender", "launchQuake",
                      "launcher_controls", "received");
    [self launchQuakeUsingLauncherControls:YES];
}

- (void)launchQuakeUsingLauncherControls:(BOOL)useLauncherControls {
    int index = 0;
    QGE_LauncherProbe("AppController", "launchQuakeUsingLauncherControls",
                      useLauncherControls ? "launcher_controls" : "nolauncher",
                      "handoff");

    if (useLauncherControls) {
        [arguments parseArguments:[paramTextField stringValue]];

        index = [screenModePopUp indexOfSelectedItem];
        if (index > 0) {
            ScreenInfo *info = [screenModes objectAtIndex:index];

            int width = [info width];
            int height = [info height];
            int bpp = [info bpp];

            [arguments addArgument:@"-width" withValue:[NSString stringWithFormat:@"%d", width]];
            [arguments addArgument:@"-height" withValue:[NSString stringWithFormat:@"%d", height]];
            [arguments addArgument:@"-bpp" withValue:[NSString stringWithFormat:@"%d", bpp]];
        }

        [arguments removeArgument:@"-fullscreen"];
        [arguments removeArgument:@"-window"];
        BOOL fullscreen = [fullscreenCheckBox state] == NSControlStateValueOn;
        if (fullscreen)
            [arguments addArgument:@"-fullscreen"];
        else
            [arguments addArgument:@"-window"];
    }

    NSString *path = [NSString stringWithCString:gArgv[0] encoding:NSASCIIStringEncoding];
    
    int i;
    for (i = 0; i < 4; i++)
        path = [path stringByDeletingLastPathComponent];

    NSFileManager *fileManager = [NSFileManager defaultManager];
    [fileManager changeCurrentDirectoryPath:path];
    
    int argc = [arguments count] + 1;
    char *argv[argc];
    
    argv[0] = gArgv[0];
    [arguments setArguments:argv + 1];

    [launcherWindow close];

    if (useLauncherControls) {
        // update the defaults
        NSUserDefaults *defaults = [NSUserDefaults standardUserDefaults];
        [defaults setObject:[paramTextField stringValue] forKey:FQPrefCommandLineKey];
        [defaults setObject:[NSNumber numberWithBool:[fullscreenCheckBox state] == NSControlStateValueOn] forKey:FQPrefFullscreenKey];
        [defaults setObject:[NSNumber numberWithInt:index] forKey:FQPrefScreenModeKey];
        [defaults synchronize];
    }

    int status = SDL_main (argc, argv);
    exit(status);
}

- (IBAction)cancel:(id)sender {
    exit(0);
}

- (void) dealloc {
    [screenModes release];
    [super dealloc];
}


@end
