import os
import platform

from conan.tools.google import BazelToolchain


class Bazel:

    def __init__(self, conanfile):
        """
        :param conanfile: ``< ConanFile object >`` The current recipe object. Always use ``self``.
        """
        self._conanfile = conanfile
        # Use BazelToolchain generated file if exists
        self._use_conan_config = True
        self._startup_opts = ""

    def _safe_run_command(self, command):
        """
        Windows is having problems stopping bazel processes, so it ends up locking
        some files if something goes wrong. Better to shut down the Bazel server after running
        each command.
        """
        try:
            self._conanfile.run(command)
        finally:
            if platform.system() == "Windows":
                self._conanfile.run("bazel" + self._startup_opts + " shutdown")

    def _get_startup_command_options(self):
        bazelrc_paths = []
        if self._use_conan_config:
            bazelrc_paths.append(self._conan_bazelrc)
        # User bazelrc paths have more prio than Conan one
        # See more info in https://bazel.build/run/bazelrc
        bazelrc_paths.extend(self._conanfile.conf.get("tools.google.bazel:bazelrc_path", default=[],
                                                      check_type=list))
        opts = " ".join(["--bazelrc=" + rc.replace("\\", "/") for rc in bazelrc_paths])
        return f" {opts}" if opts else ""

    def build(self, args=None, target="//...", clean=True):
        """
        Runs:

          bazel <startup_opts> build
            --bazelrc=...
            --platforms=//conan_bazel:conan_platform
            --extra_toolchains=//conan_bazel:conan_cc_toolchain
            --config=...
            <args>
            <targets>
        """

        args = args or []

        # ---------------------------------------------------------------------
        # Startup command
        # ---------------------------------------------------------------------
        bazel_cmd = "bazel" + self._startup_opts

        # ---------------------------------------------------------------------
        # Clean (important for toolchain changes)
        # ---------------------------------------------------------------------
        if clean:
            self._safe_run_command(f"{bazel_cmd} clean")

        # ---------------------------------------------------------------------
        # Build command
        # ---------------------------------------------------------------------
        command = f"{bazel_cmd} build"

        # ---------------------------------------------------------------------
        # Activate Conan toolchain + platform
        # ---------------------------------------------------------------------
        if self._use_conan_config:
            command += " --platforms=//conan_bazel:conan_platform"
            command += " --extra_toolchains=//conan_bazel:conan_cc_toolchain"

        # ---------------------------------------------------------------------
        # Optional user configs
        # ---------------------------------------------------------------------
        for config in self._conanfile.conf.get(
            "tools.google.bazel:configs", default=[], check_type=list
        ):
            command += f" --config={config}"

        # ---------------------------------------------------------------------
        # Extra user arguments
        # ---------------------------------------------------------------------
        for arg in args:
            command += f" {arg}"

        # ---------------------------------------------------------------------
        # Targets
        # ---------------------------------------------------------------------
        command += f" {target}"

        # ---------------------------------------------------------------------
        # Run
        # ---------------------------------------------------------------------
        self._safe_run_command(command)

    def test(self, target=None):
        """
        Runs "bazel test <targets>" command.
        """
        if self._conanfile.conf.get("tools.build:skip_test", check_type=bool) or target is None:
            return
        self._safe_run_command("bazel" + self._startup_opts + f" test {target}")
