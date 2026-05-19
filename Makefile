# Quantum Quake - Makefile
# Builds QGE (Quantum Game Engine) and links with Moonlab

CC = clang
CFLAGS = -Wall -Wextra -O2 -std=c11
LDFLAGS = -lm

# Platform detection
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    CFLAGS += -DPLATFORM_MACOS
    LDFLAGS += -framework Accelerate -framework Metal -framework MetalKit -framework Foundation -framework Security -lc++
    # Apple Silicon optimizations
    ARCH := $(shell uname -m)
    ifeq ($(ARCH),arm64)
        CFLAGS += -mcpu=apple-m1
    endif
else ifeq ($(UNAME_S),Linux)
    CFLAGS += -DPLATFORM_LINUX -mavx2 -mfma
    LDFLAGS += -lpthread
endif

# Directories
MOONLAB_DIR = deps/moonlab
QGE_DIR = qge
QUAKE_DIR = quake/WinQuake
BUILD_DIR = build
BIN_DIR = bin

# Moonlab sources (core quantum simulation)
MOONLAB_SRCS = \
    $(MOONLAB_DIR)/src/quantum/state.c \
    $(MOONLAB_DIR)/src/quantum/gates.c \
    $(MOONLAB_DIR)/src/quantum/measurement.c \
    $(MOONLAB_DIR)/src/quantum/entanglement.c \
    $(MOONLAB_DIR)/src/quantum/noise.c \
    $(MOONLAB_DIR)/src/utils/matrix_math.c \
    $(MOONLAB_DIR)/src/utils/entropy.c \
    $(MOONLAB_DIR)/src/utils/config.c \
    $(MOONLAB_DIR)/src/optimization/memory_align.c \
    $(MOONLAB_DIR)/src/optimization/simd_ops.c \
    $(MOONLAB_DIR)/src/algorithms/grover.c

# Add tensor network sources
MOONLAB_SRCS += \
    $(MOONLAB_DIR)/src/algorithms/tensor_network/tensor.c \
    $(MOONLAB_DIR)/src/algorithms/tensor_network/tn_state.c \
    $(MOONLAB_DIR)/src/algorithms/tensor_network/tn_gates.c \
    $(MOONLAB_DIR)/src/algorithms/tensor_network/tn_measurement.c

# Add QRNG v3 application sources (production quantum RNG)
MOONLAB_SRCS += \
    $(MOONLAB_DIR)/src/applications/qrng.c \
    $(MOONLAB_DIR)/src/applications/entropy_pool.c \
    $(MOONLAB_DIR)/src/applications/hardware_entropy.c \
    $(MOONLAB_DIR)/src/applications/health_tests.c \
    $(MOONLAB_DIR)/src/applications/bell_test.c

# Add Bell test algorithm (required by QRNG v3)
MOONLAB_SRCS += \
    $(MOONLAB_DIR)/src/algorithms/bell_tests.c

# Add performance monitor (required by QRNG v3)
MOONLAB_SRCS += \
    $(MOONLAB_DIR)/src/utils/performance_monitor.c

# Add optimization sources (platform-specific)
ifeq ($(UNAME_S),Darwin)
    MOONLAB_SRCS += $(MOONLAB_DIR)/src/optimization/accelerate_ops.c
    MOONLAB_OBJC_SRCS = $(MOONLAB_DIR)/src/optimization/gpu_metal.mm
endif

MOONLAB_CPP_SRCS = \
    $(MOONLAB_DIR)/src/optimization/gpu/backends/gpu_eshkol.cpp

# QGE sources
QGE_SRCS = \
    $(QGE_DIR)/qge_init.c \
    $(QGE_DIR)/qge_rng.c \
    $(QGE_DIR)/qge_quantum_runtime.c \
    $(QGE_DIR)/qge_trace.c \
    $(QGE_DIR)/qge_world.c \
    $(QGE_DIR)/qge_ai.c \
    $(QGE_DIR)/qge_render.c \
    $(QGE_DIR)/qge_vis.c \
    $(QGE_DIR)/qge_audio.c \
    $(QGE_DIR)/qge_physics.c

# QGE Metal sources (macOS only)
ifeq ($(UNAME_S),Darwin)
    QGE_OBJC_SRCS = $(QGE_DIR)/qge_metal.mm
endif

# Include paths
INCLUDES = -I$(MOONLAB_DIR)/src -I$(MOONLAB_DIR)/tools -I$(QGE_DIR) -I$(QUAKE_DIR)

# Object files
MOONLAB_OBJS = $(patsubst %.c,$(BUILD_DIR)/%.o,$(MOONLAB_SRCS))
MOONLAB_OBJS += $(patsubst %.cpp,$(BUILD_DIR)/%.o,$(MOONLAB_CPP_SRCS))
MOONLAB_OBJS += $(patsubst %.mm,$(BUILD_DIR)/%.o,$(MOONLAB_OBJC_SRCS))
QGE_OBJS = $(patsubst %.c,$(BUILD_DIR)/%.o,$(QGE_SRCS))
QGE_OBJS += $(patsubst %.mm,$(BUILD_DIR)/%.o,$(QGE_OBJC_SRCS))

# Targets
.PHONY: all clean test moonlab qge dirs demo demo-sdl quake run-quake test_noesis_input_contract test_qge_perf_summary test_qge_trace_summary test_qge_vanilla_matrix_perf test_qge_publication_tools test_qge_python_tools test_snd_quantum_source_contract test_qge_audio_authority_smoke

all: dirs moonlab qge test_qge

dirs:
	@mkdir -p $(BUILD_DIR)/$(MOONLAB_DIR)/src/quantum
	@mkdir -p $(BUILD_DIR)/$(MOONLAB_DIR)/src/utils
	@mkdir -p $(BUILD_DIR)/$(MOONLAB_DIR)/src/algorithms
	@mkdir -p $(BUILD_DIR)/$(MOONLAB_DIR)/src/algorithms/tensor_network
	@mkdir -p $(BUILD_DIR)/$(MOONLAB_DIR)/src/optimization
	@mkdir -p $(BUILD_DIR)/$(MOONLAB_DIR)/src/optimization/gpu/backends
	@mkdir -p $(BUILD_DIR)/$(MOONLAB_DIR)/src/applications
	@mkdir -p $(BUILD_DIR)/$(QGE_DIR)
	@mkdir -p $(BIN_DIR)

# Compile Moonlab C sources
$(BUILD_DIR)/%.o: %.c
	@echo "CC $<"
	@$(CC) $(CFLAGS) $(INCLUDES) -c $< -o $@

# Compile Moonlab Objective-C++ sources (Metal)
# Use C++17 for ObjC++ instead of C11
OBJCXX_FLAGS = -Wall -Wextra -O2 -std=c++17
ifeq ($(UNAME_S),Darwin)
    OBJCXX_FLAGS += -DPLATFORM_MACOS
    ifeq ($(ARCH),arm64)
        OBJCXX_FLAGS += -mcpu=apple-m1
    endif
endif

$(BUILD_DIR)/%.o: %.cpp
	@echo "CXX $<"
	@$(CC) $(OBJCXX_FLAGS) $(INCLUDES) -c $< -o $@

$(BUILD_DIR)/%.o: %.mm
	@echo "CC (ObjC++) $<"
	@$(CC) $(OBJCXX_FLAGS) $(INCLUDES) -fobjc-arc -c $< -o $@

# Build Moonlab library
moonlab: dirs $(MOONLAB_OBJS)
	@echo "Building Moonlab..."
	@ar rcs $(BUILD_DIR)/libmoonlab.a $(MOONLAB_OBJS)
	@echo "Moonlab library built: $(BUILD_DIR)/libmoonlab.a"

# Build QGE library
qge: dirs moonlab $(QGE_OBJS)
	@echo "Building QGE..."
	@ar rcs $(BUILD_DIR)/libqge.a $(QGE_OBJS)
	@echo "QGE library built: $(BUILD_DIR)/libqge.a"

# Test program
test_qge: qge
	@echo "Building QGE test..."
	@$(CC) $(CFLAGS) $(INCLUDES) tests/test_qge.c \
		-L$(BUILD_DIR) -lqge -lmoonlab $(LDFLAGS) \
		-o $(BIN_DIR)/test_qge
	@echo "Test built: $(BIN_DIR)/test_qge"

test_console_contract: dirs
	@echo "Building console artifact contract test..."
	@$(CC) $(CFLAGS) tests/test_console_contract.c \
		-o $(BIN_DIR)/test_console_contract
	@echo "Test built: $(BIN_DIR)/test_console_contract"

test_noesis_input_contract:
	@echo "Running Noesis input contract test..."
	@bash tests/test_noesis_input_contract.sh

test_qge_perf_summary:
	@echo "Running QGE performance summary contract test..."
	@bash tests/test_qge_perf_summary.sh

test_qge_trace_summary:
	@echo "Running QGE trace summary contract test..."
	@bash tests/test_qge_trace_summary.sh

test_qge_vanilla_matrix_perf:
	@echo "Running QGE vanilla matrix performance contract test..."
	@bash tests/test_qge_vanilla_matrix_perf.sh

test_qge_publication_tools:
	@echo "Running QGE publication tools contract test..."
	@bash tests/test_qge_publication_tools.sh

test_qge_python_tools:
	@echo "Running QGE Python tools unit tests..."
	@python3 tests/test_qge_python_tools.py

test_snd_quantum_source_contract:
	@echo "Running QGE quantum source audio contract test..."
	@bash tests/test_snd_quantum_source_contract.sh

test_qge_audio_authority_smoke:
	@echo "Running QGE audio authority smoke evidence test..."
	@bash tests/test_qge_audio_authority_smoke.sh

# Run tests
test: test_qge test_console_contract test_noesis_input_contract test_qge_perf_summary test_qge_trace_summary test_qge_vanilla_matrix_perf test_qge_publication_tools test_qge_python_tools test_snd_quantum_source_contract test_qge_audio_authority_smoke
	@echo "Running QGE tests..."
	@./$(BIN_DIR)/test_qge
	@echo "Running console artifact contract test..."
	@./$(BIN_DIR)/test_console_contract

clean:
	rm -rf $(BUILD_DIR) $(BIN_DIR)

# Info target
info:
	@echo "Quantum Quake Build System"
	@echo "=========================="
	@echo "Platform: $(UNAME_S)"
	@echo "Compiler: $(CC)"
	@echo "CFLAGS: $(CFLAGS)"
	@echo "LDFLAGS: $(LDFLAGS)"
	@echo ""
	@echo "Moonlab sources: $(words $(MOONLAB_SRCS)) files"
	@echo "QGE sources: $(words $(QGE_SRCS)) files"

# ==============================================================================
# Quantum Rendering Demo
# ==============================================================================

DEMO_DIR = demo

# Demo (headless - outputs PPM files)
demo: qge
	@echo "Building Quantum Demo (headless)..."
	@mkdir -p $(BUILD_DIR)/$(DEMO_DIR)
	@$(CC) $(CFLAGS) $(INCLUDES) -I$(DEMO_DIR) $(DEMO_DIR)/quantum_demo.c \
		-L$(BUILD_DIR) -lqge -lmoonlab $(LDFLAGS) \
		-o $(BIN_DIR)/quantum_demo
	@echo "Demo built: $(BIN_DIR)/quantum_demo"
	@echo ""
	@echo "Run with: ./$(BIN_DIR)/quantum_demo"
	@echo "This will output quantum_frame_XX.ppm files"

# Demo with SDL2 (interactive window)
demo-sdl: qge
	@echo "Building Quantum Demo (SDL2)..."
	@mkdir -p $(BUILD_DIR)/$(DEMO_DIR)
	@$(CC) $(CFLAGS) $(INCLUDES) -I$(DEMO_DIR) -DUSE_SDL $(DEMO_DIR)/quantum_demo.c \
		-L$(BUILD_DIR) -lqge -lmoonlab $(LDFLAGS) \
		$(shell pkg-config --cflags --libs sdl2 2>/dev/null || echo "-lSDL2") \
		-o $(BIN_DIR)/quantum_demo_sdl
	@echo "Demo built: $(BIN_DIR)/quantum_demo_sdl"
	@echo ""
	@echo "Controls: WASD=move, Q/E=rotate, Space=reset, ESC=quit"

# Run headless demo
run-demo: demo
	@echo "Running Quantum Demo..."
	@cd $(BIN_DIR) && ./quantum_demo

# Run SDL demo
run-demo-sdl: demo-sdl
	@echo "Running Quantum Demo (SDL2)..."
	@./$(BIN_DIR)/quantum_demo_sdl

# ==============================================================================
# Metal GPU Acceleration Demo
# ==============================================================================

# Demo with Metal GPU acceleration
demo-metal: qge
	@echo "Building Quantum Demo (Metal GPU)..."
	@mkdir -p $(BUILD_DIR)/$(DEMO_DIR)
	@$(CC) $(CFLAGS) $(INCLUDES) -I$(DEMO_DIR) -DUSE_METAL $(DEMO_DIR)/quantum_demo.c \
		-L$(BUILD_DIR) -lqge -lmoonlab $(LDFLAGS) \
		-o $(BIN_DIR)/quantum_demo_metal
	@echo "Demo built: $(BIN_DIR)/quantum_demo_metal"
	@echo ""
	@echo "GPU-accelerated quantum rendering enabled"

# Run Metal demo
run-demo-metal: demo-metal
	@echo "Running Quantum Demo (Metal GPU)..."
	@./$(BIN_DIR)/quantum_demo_metal

# ==============================================================================
# Quantum Quake (Full QuakeSpasm + QGE + Moonlab)
# ==============================================================================

QUAKESPASM_DIR = quake/Quake

# Codec and framework paths for runtime
CODEC_LIB_DIR = quake/MacOSX/codecs/lib
SDL2_FRAMEWORK_DIR = quake/MacOSX

# App bundle paths
APP_BUNDLE = QuantumQuake.app
APP_CONTENTS = $(APP_BUNDLE)/Contents
APP_MACOS = $(APP_CONTENTS)/MacOS
APP_FRAMEWORKS = $(APP_CONTENTS)/Frameworks
APP_RESOURCES = $(APP_CONTENTS)/Resources
EXISTING_APP = QuakeSpasm-SDL2-M1.app

# Build Quantum Quake .app bundle
quake:
	@echo ""
	@echo "======================================"
	@echo "  Building Quantum Quake"
	@echo "  QuakeSpasm + QGE + Moonlab"
	@echo "======================================"
	@echo ""
	@$(MAKE) -C $(QUAKESPASM_DIR) -f Makefile.darwin USE_SDL2=1
	@# Create .app bundle structure
	@mkdir -p $(APP_MACOS) $(APP_FRAMEWORKS) $(APP_RESOURCES)/English.lproj $(BIN_DIR)
	@# Copy binary
	@cp $(QUAKESPASM_DIR)/quakespasm $(APP_MACOS)/quantum_quake
	@cp $(QUAKESPASM_DIR)/quakespasm $(BIN_DIR)/quantum_quake
	@# Copy codec dylibs into app bundle
	@cp -f $(CODEC_LIB_DIR)/libFLAC.dylib $(APP_MACOS)/ 2>/dev/null || true
	@cp -f $(CODEC_LIB_DIR)/libogg.dylib $(APP_MACOS)/ 2>/dev/null || true
	@cp -f $(CODEC_LIB_DIR)/libvorbis.dylib $(APP_MACOS)/ 2>/dev/null || true
	@cp -f $(CODEC_LIB_DIR)/libvorbisfile.dylib $(APP_MACOS)/ 2>/dev/null || true
	@cp -f $(CODEC_LIB_DIR)/libopus.dylib $(APP_MACOS)/ 2>/dev/null || true
	@cp -f $(CODEC_LIB_DIR)/libopusfile.dylib $(APP_MACOS)/ 2>/dev/null || true
	@cp -f $(CODEC_LIB_DIR)/libmad.dylib $(APP_MACOS)/ 2>/dev/null || true
	@cp -f $(CODEC_LIB_DIR)/libxmp.dylib $(APP_MACOS)/ 2>/dev/null || true
	@# Copy SDL2 framework
	@cp -Rn $(SDL2_FRAMEWORK_DIR)/SDL2.framework $(APP_FRAMEWORKS)/ 2>/dev/null || true
	@# Copy NIB and resources from existing app bundle
	@cp $(EXISTING_APP)/Contents/Resources/English.lproj/Launcher.nib $(APP_RESOURCES)/English.lproj/ 2>/dev/null || true
	@cp $(EXISTING_APP)/Contents/Resources/QuakeSpasm.icns $(APP_RESOURCES)/ 2>/dev/null || true
	@# Create Info.plist
	@/usr/libexec/PlistBuddy -c "Clear dict" $(APP_CONTENTS)/Info.plist 2>/dev/null || true
	@/usr/libexec/PlistBuddy \
		-c "Add :CFBundleExecutable string quantum_quake" \
		-c "Add :CFBundleName string QuantumQuake" \
		-c "Add :CFBundleIdentifier string com.quantumquake.QuantumQuake" \
		-c "Add :CFBundlePackageType string APPL" \
		-c "Add :CFBundleSignature string ????" \
		-c "Add :CFBundleShortVersionString string 1.0.0" \
		-c "Add :CFBundleIconFile string QuakeSpasm" \
		-c "Add :NSMainNibFile string Launcher" \
		-c "Add :NSPrincipalClass string SDLApplication" \
		-c "Add :NSQuitAlwaysKeepsWindows bool false" \
		-c "Add :LSMinimumSystemVersion string 11.0" \
		-c "Add :CFBundleDevelopmentRegion string English" \
		-c "Add :CFBundleInfoDictionaryVersion string 6.0" \
		$(APP_CONTENTS)/Info.plist
	@# Create PkgInfo
	@echo -n "APPL????" > $(APP_CONTENTS)/PkgInfo
	@# Ad-hoc codesign everything
	@echo "Signing app bundle..."
	@xattr -cr $(APP_BUNDLE) 2>/dev/null || true
	@for lib in $(APP_MACOS)/lib*.dylib; do codesign -s - -f "$$lib" 2>/dev/null || true; done
	@codesign -s - -f --deep $(APP_FRAMEWORKS)/SDL2.framework 2>/dev/null || true
	@codesign -s - -f $(APP_MACOS)/quantum_quake
	@echo ""
	@echo "======================================"
	@echo "  Quantum Quake built successfully!"
	@echo "  App: $(APP_BUNDLE)"
	@echo "======================================"
	@echo ""
	@echo "Run with: make run-quake"
	@echo ""
	@echo "Console commands:"
	@echo "  quantum_render 1  - Enable quantum DWT rendering"
	@echo "  quantum_rng 1     - Enable quantum RNG (default)"
	@echo "  quantum_ai 1      - Enable quantum AI (default)"
	@echo "  quantum_particles 1 - Enable quantum wave particles"
	@echo "  quantum_vis 1     - Enable Grover BSP visibility"
	@echo "  quantum_physics_authoritative 1 - Allow approved QGE projectile writeback"

# Run Quantum Quake (requires Quake game data in assets/id1/)
run-quake: quake
	@echo "Launching Quantum Quake..."
	@$(APP_MACOS)/quantum_quake -basedir assets

# Clean Quantum Quake build
clean-quake:
	@$(MAKE) -C $(QUAKESPASM_DIR) -f Makefile.darwin clean
	@rm -rf $(APP_BUNDLE)
	@rm -f $(BIN_DIR)/quantum_quake
