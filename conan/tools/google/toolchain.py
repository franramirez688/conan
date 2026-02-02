import os
import textwrap

from jinja2 import Template, StrictUndefined

from conan.errors import ConanException
from conan.internal import check_duplicated_generator
from conan.internal.internal_tools import raise_on_universal_arch
from conan.tools.build.cross_building import cross_building
from conan.tools.apple.apple import (
    is_apple_os,
    resolve_apple_flags,
    apple_min_version_flag,
    apple_extra_flags,
)
from conan.tools.build.flags import (
    architecture_flag,
    architecture_link_flag,
    threads_flags,
    libcxx_flags,
)
from conan.tools.env import VirtualBuildEnv
from conan.tools.microsoft import msvc_runtime_flag
from conan.internal.util.files import save


class BazelToolchain:
    """
    Conan Bazel C++ Toolchain generator

    Design goals:
    - Single-file generator
    - MesonToolchain-like architecture
    - Fully Bazel-compliant (platforms + cc_toolchain)
    - Cross-build aware
    """

    folder_name = "conan_bazel"

    # -------------------------------------------------------------------------
    # Templates
    # -------------------------------------------------------------------------

    _platform_bzl_template = textwrap.dedent("""
    def define_platform():
        native.platform(
            name = "conan_platform",
            constraint_values = [
                "@platforms//os:{{ os }}",
                "@platforms//cpu:{{ cpu }}",
            ],
        )
    """)

    _cc_toolchain_bzl_template = textwrap.dedent("""
    load("@bazel_tools//tools/cpp:cc_toolchain_config_lib.bzl",
         "cc_toolchain_config")

    def _impl(ctx):
        return cc_common.create_cc_toolchain_config_info(
            ctx = ctx,

            toolchain_identifier = "{{ toolchain_id }}",
            compiler = "{{ compiler }}",
            target_cpu = "{{ target_cpu }}",
            target_system_name = "{{ target_os }}",

            tool_paths = [
            {% for name, path in tool_paths.items() %}
                tool_path(name = "{{ name }}", path = "{{ path }}"),
            {% endfor %}
            ],

            features = [
            {% for f in features %}
                feature(
                    name = "{{ f.name }}",
                    enabled = {{ "True" if f.enabled else "False" }},
                    flag_sets = [
                        flag_set(
                            actions = {{ f.actions }},
                            flag_groups = [
                                flag_group(
                                    flags = {{ f.flags }}
                                ),
                            ],
                        ),
                    ],
                ),
            {% endfor %}
            ],
        )

    cc_toolchain_config = rule(
        implementation = _impl,
        attrs = {},
        provides = [CcToolchainConfigInfo],
    )
    """)

    _build_bazel_template = textwrap.dedent("""
    load(":platform.bzl", "define_platform")
    load(":cc_toolchain.bzl", "cc_toolchain_config")

    define_platform()

    cc_toolchain(
        name = "cc_toolchain",
        toolchain_identifier = "{{ toolchain_id }}",
        toolchain_config = ":cc_toolchain_config",
        all_files = ":empty",
        compiler_files = ":empty",
        dwp_files = ":empty",
        linker_files = ":empty",
        objcopy_files = ":empty",
        strip_files = ":empty",
    )

    toolchain(
        name = "conan_cc_toolchain",
        toolchain_type = "@bazel_tools//tools/cpp:toolchain_type",
        toolchain = ":cc_toolchain",
        target_compatible_with = [
            "@platforms//os:{{ os }}",
            "@platforms//cpu:{{ cpu }}",
        ],
    )

    filegroup(name = "empty", srcs = [])
    """)

    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------

    def __init__(self, conanfile):
        raise_on_universal_arch(conanfile)

        self._conanfile = conanfile
        self.settings = conanfile.settings
        self.conf = conanfile.conf

        self._is_cross = cross_building(conanfile)
        self._is_apple = is_apple_os(conanfile)

        self._output_dir = os.path.join(
            conanfile.generators_folder, self.folder_name
        )

        # Public, user-modifiable API (Meson-style)
        self.extra_cflags = []
        self.extra_cxxflags = []
        self.extra_linkflags = []
        self.extra_defines = []

        self.enable_lto = False
        self.enable_pic = None

        # Internal state
        self._features = []
        self._tool_paths = {}

        # Validate required settings
        self._validate_settings()

        # Resolve environment & tools
        self._resolve_build_environment()
        self._resolve_compilers()
        self._resolve_flags()

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def _validate_settings(self):
        if not self.settings.get_safe("compiler"):
            raise ConanException("BazelToolchain requires 'settings.compiler'")
        if not self.settings.get_safe("compiler.version"):
            raise ConanException("BazelToolchain requires 'settings.compiler.version'")
        if not self.settings.get_safe("os"):
            raise ConanException("BazelToolchain requires 'settings.os'")
        if not self.settings.get_safe("arch"):
            raise ConanException("BazelToolchain requires 'settings.arch'")

    # -------------------------------------------------------------------------
    # Resolution phase (Meson-style)
    # -------------------------------------------------------------------------

    def _resolve_build_environment(self):
        self._buildenv = VirtualBuildEnv(
            self._conanfile, auto_generate=True
        ).vars()

    def _resolve_compilers(self):
        conf_execs = self.conf.get(
            "tools.build:compiler_executables",
            default={}, check_type=dict
        )

        compiler = str(self.settings.compiler)

        if compiler in ("gcc", "clang", "apple-clang"):
            self._tool_paths["gcc"] = (
                conf_execs.get("c")
                or self._buildenv.get("CC")
                or "clang"
            )
            self._tool_paths["g++"] = (
                conf_execs.get("cpp")
                or self._buildenv.get("CXX")
                or "clang++"
            )
            self._tool_paths["ar"] = conf_execs.get("ar") or self._buildenv.get("AR") or "ar"
            self._tool_paths["ld"] = conf_execs.get("ld") or self._buildenv.get("LD") or "ld"

        elif compiler == "msvc":
            self._tool_paths["cl"] = "cl"
            self._tool_paths["link"] = "link"
            self._tool_paths["lib"] = "lib"

        else:
            raise ConanException(
                f"BazelToolchain: compiler '{compiler}' not supported yet"
            )

    def _resolve_flags(self):
        # Architecture flags
        self._arch_flag = architecture_flag(self._conanfile)
        self._arch_link_flag = architecture_link_flag(self._conanfile)

        # Threads flags
        self._threads_flags = threads_flags(self._conanfile)

        # libc++
        self._libcxx, self._gcc_abi = libcxx_flags(self._conanfile)

        # Apple flags
        self._apple_flags = []
        if self._is_apple:
            minf, archf, sysrootf = resolve_apple_flags(self._conanfile, self._is_cross)
            self._apple_flags += archf.split() if archf else []
            self._apple_flags += sysrootf.split() if sysrootf else []
            self._apple_flags.append(apple_min_version_flag(self._conanfile))
            self._apple_flags += apple_extra_flags(self._conanfile)

        # Build-type flags
        self._build_type_flags = []
        bt = self.settings.get_safe("build_type")
        if bt == "Debug":
            self._build_type_flags += ["-g", "-O0"]
        elif bt == "Release":
            self._build_type_flags += ["-O3", "-DNDEBUG"]

        # C++ standard
        cppstd = self.settings.compiler.get_safe("cppstd")
        if cppstd:
            self._build_type_flags.append(f"-std=c++{cppstd}")

    # -------------------------------------------------------------------------
    # Feature construction (Bazel-native)
    # -------------------------------------------------------------------------

    def _build_features(self):
        compile_flags = (
            [self._arch_flag] +
            self._build_type_flags +
            self._threads_flags +
            self._apple_flags +
            self.extra_cxxflags +
            [f"-D{d}" for d in self.extra_defines]
        )

        link_flags = (
            [self._arch_flag, self._arch_link_flag] +
            self._threads_flags +
            self._apple_flags +
            self.extra_linkflags
        )

        self._features.append({
            "name": "conan_compile_flags",
            "enabled": True,
            "actions": [
                "c-compile",
                "c++-compile",
                "assemble",
                "preprocess-assemble",
            ],
            "flags": compile_flags,
        })

        self._features.append({
            "name": "conan_link_flags",
            "enabled": True,
            "actions": [
                "c++-link-executable",
                "c++-link-dynamic-library",
                "c++-link-static-library",
            ],
            "flags": link_flags,
        })

        if self._libcxx:
            self._features.append({
                "name": "libcxx",
                "enabled": True,
                "actions": ["c++-compile", "c++-link-executable"],
                "flags": [self._libcxx],
            })

        if self._gcc_abi:
            self._features.append({
                "name": "gcc_abi",
                "enabled": True,
                "actions": ["c++-compile"],
                "flags": [f"-D{self._gcc_abi}"],
            })

        if self.settings.compiler == "msvc":
            rt = msvc_runtime_flag(self._conanfile)
            if rt:
                self._features.append({
                    "name": "msvc_runtime",
                    "enabled": True,
                    "actions": ["c++-compile", "c++-link-executable"],
                    "flags": [str(rt)],
                })

    # -------------------------------------------------------------------------
    # Context (MesonToolchain-style)
    # -------------------------------------------------------------------------

    @property
    def _context(self):
        self._build_features()

        return {
            "toolchain_id": self._toolchain_id,
            "compiler": str(self.settings.compiler),
            "target_cpu": str(self.settings.arch),
            "target_os": str(self.settings.os).lower(),
            "os": str(self.settings.os).lower(),
            "cpu": str(self.settings.arch),
            "tool_paths": self._tool_paths,
            "features": self._features,
        }

    @property
    def _toolchain_id(self):
        return "-".join([
            "conan",
            str(self.settings.os),
            str(self.settings.arch),
            str(self.settings.compiler),
            str(self.settings.compiler.version),
        ]).lower()

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def _render(self, template, context):
        return Template(
            template,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        ).render(context)

    # -------------------------------------------------------------------------
    # Generate
    # -------------------------------------------------------------------------

    def generate(self):
        check_duplicated_generator(self, self._conanfile)

        os.makedirs(self._output_dir, exist_ok=True)

        ctx = self._context

        save(
            os.path.join(self._output_dir, "platform.bzl"),
            self._render(self._platform_bzl_template, ctx),
        )

        save(
            os.path.join(self._output_dir, "cc_toolchain.bzl"),
            self._render(self._cc_toolchain_bzl_template, ctx),
        )

        save(
            os.path.join(self._output_dir, "BUILD.bazel"),
            self._render(self._build_bazel_template, ctx),
        )

        self._conanfile.output.info(
            f"BazelToolchain generated in {self._output_dir}"
        )
