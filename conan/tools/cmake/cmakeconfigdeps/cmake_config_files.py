import jinja2
from jinja2 import Template

from conan.internal.model.dependencies import get_transitive_requires
from conan.tools.cmake.cmakeconfigdeps.config import ConfigTemplate2
from conan.tools.cmake.cmakeconfigdeps.config_version import ConfigVersionTemplate2
from conan.tools.cmake.cmakeconfigdeps.target_configuration import TargetConfigurationTemplate2
from conan.tools.cmake.cmakeconfigdeps.targets import TargetsTemplate2


class CMakeConfigFiles:

    def __init__(self, cmakeconfigdeps, dep, require):
        self._cmakeconfigdeps = cmakeconfigdeps
        self._require = require
        self._filename = self.get_cmake_filename(dep)
        self.conanfile = dep
        self.consumer_conanfile = self._cmakeconfigdeps._conanfile  # noqa
        self.is_build_context = require.build
        self.full_cpp_info = dep.cpp_info.deduce_full_cpp_info(dep)
        # Prepared to filter transitive tool-requires with visible=True
        self.transitive_requires = get_transitive_requires(self.consumer_conanfile, dep)  # noqa

    @property
    def pkg_name(self):
        return self.conanfile.ref.name

    @property
    def pkg_version(self):
        return self.conanfile.ref.version

    @property
    def config(self):
        config = self.conanfile.settings.get_safe("build_type", self._cmakeconfigdeps.configuration)
        return config.upper() if config else None

    @property
    def has_headers(self):
        # FIXME: Filter by lib traits!!!!!
        return self._require.headers

    @property
    def package_folder(self):
        return self.conanfile.package_folder.replace("\\", "/")

    @property
    def package_folder_var(self):
        # fallback to consumer configuration if it doesn't have build_type
        config = self.config
        config_folder = f"_{config}" if config else ""
        build = "_BUILD" if self.is_build_context else ""
        return f"{self.pkg_name}_PACKAGE_FOLDER{config_folder}{build}"

    def get_cmake_filename(self, dep=None):
        # Get the name of the file for the find_package(XXX)
        # This is used by CMakeDeps to determine:
        # - The filename to generate (XXX-config.cmake or FindXXX.cmake)
        # - The name of the defined XXX_DIR variables
        # - The name of transitive dependencies for calls to find_dependency
        dep = dep or self.conanfile
        ret = self._cmakeconfigdeps.get_property("cmake_file_name", dep)
        return ret or dep.ref.name

    def get_cmake_target_name(self, dep=None, comp_name=None):
        dep = dep or self.conanfile
        target_name = self.properties("cmake_target_name", dep=dep, comp_name=comp_name)
        return target_name or f"{dep.ref.name}::{dep.ref.name if comp_name else dep.ref.name}"

    @property
    def config_filename(self):
        f = self._filename
        return f"{f}-config.cmake" if f == f.lower() else f"{f}Config.cmake"

    @property
    def config_version_filename(self):
        f = self._filename
        return f"{f}-config-version.cmake" if f == f.lower() else f"{f}ConfigVersion.cmake"

    @property
    def target_configuration_filename(self):
        f = self._filename
        # Fallback to consumer configuration if it doesn't have build_type
        config = (self.config or "none").lower()
        build = "Build" if self.is_build_context else ""
        return f"{f}-Targets{build}-{config}.cmake"

    @property
    def targets_filename(self):
        return f"{self._filename}Targets.cmake"

    def properties(self, prop, dep=None, **kwargs):
        dep = dep or self.conanfile
        return self._cmakeconfigdeps.get_property(prop, dep, **kwargs)

    @staticmethod
    def _render_content(cmake_class_type):
        t = Template(cmake_class_type.template, trim_blocks=True, lstrip_blocks=True,
                     undefined=jinja2.StrictUndefined)
        return t.render(cmake_class_type.context)

    def items(self):
        return {
            self.config_filename: self._render_content(ConfigTemplate2(self)),
            self.config_version_filename: self._render_content(ConfigVersionTemplate2(self)),
            self.target_configuration_filename: self._render_content(TargetConfigurationTemplate2(self)),
            self.targets_filename: self._render_content(TargetsTemplate2(self)),
        }
