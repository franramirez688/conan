"""
(conan) franchuti@franchuti-VirtualBox:~/develop/tests/t3$ patchelf
syntax: patchelf
  [--set-interpreter FILENAME]
  [--page-size SIZE]
  [--print-interpreter]
  [--print-soname]		Prints 'DT_SONAME' entry of .dynamic section. Raises an error if DT_SONAME doesn't exist
  [--set-soname SONAME]		Sets 'DT_SONAME' entry to SONAME.
  [--set-rpath RPATH]
  [--remove-rpath]
  [--shrink-rpath]
  [--allowed-rpath-prefixes PREFIXES]		With '--shrink-rpath', reject rpath entries not starting with the allowed prefix
  [--print-rpath]
  [--force-rpath]
  [--add-needed LIBRARY]
  [--remove-needed LIBRARY]
  [--replace-needed LIBRARY NEW_LIBRARY]
  [--print-needed]
  [--no-default-lib]
  [--debug]
  [--version]
  FILENAME
(conan) franchuti@franchuti-VirtualBox:~/develop/tests/t3$ patchelf --print-soname /home/franchuti/.conan/data/hell/1.0/_/_/package/7f2f2e0dc409417fb8c1337f4abdc3c40fe90b3e/lib/libhell.so
libhell.so

"""
import os

from conans.errors import ConanException


class PatchELF(object):
    def __init__(self, conanfile):
        self._conanfile = conanfile
        # Get the patchelf script path, otherwise an exception will be raised
        self._patchelf_path = conanfile.conf.get("tools.build:patchelf_path")
        if not self._patchelf_path:
            raise ConanException("You have to provide a valid patchelf path through "
                                 "'tools.build:patchelf_path' configuration field")

    def _get_shared_lib_file_paths(self, dependency):

        def _get_real_path(libdirs, lib_):
            for libdir in libdirs:
                if not os.path.exists(libdir):
                    self._conanfile.output.warning(
                        "The library folder doesn't exist: {}".format(libdir))
                    continue
                files = os.listdir(libdir)
                for f in files:
                    name, ext = os.path.splitext(f)
                    # if ext in (".so", ".dylib"):
                    if ext == ".so" and name.startswith("lib"):
                        name = name[3:]
                    if lib_ == name:
                        return os.path.join(libdir, f)
            self._conanfile.output.warning("The library {} cannot be found in the "
                                           "dependency".format(lib_))

        cpp_info = dependency.cpp_info.aggregated_components()
        if not cpp_info.libs:
            return None

        libs = {}
        for lib in cpp_info.libs:
            real_path = _get_real_path(cpp_info.libdirs, lib)
            if real_path:
                libs[lib] = real_path

        # shared_library = dependency.options.get_safe("shared") if dependency.options else False
        return libs

    def set_soname(self):
        for dependency in self._conanfile.dependencies.direct_build.values():
            shared_lib_paths = self._get_shared_lib_file_paths(dependency)
            for shared_lib_path in shared_lib_paths.values():
                command = "{} --print-soname {}".format(self._patchelf_path, shared_lib_path)
                out = self._conanfile.run(command)
                if not out:  # this library does not have SONAME
                    lib_name = os.path.basename(shared_lib_path)
                    command = "{} --set-soname {} {}".format(self._patchelf_path, lib_name, shared_lib_path)
                    self._conanfile.run(command)
