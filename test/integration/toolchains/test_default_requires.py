import os
import textwrap

import pytest

from conan.test.utils.tools import TestClient


def get_requires_from_content(content):
    for line in content.splitlines():
        if "Requires:" in line:
            return line
    return ""


@pytest.mark.parametrize("default_requires", [True, False])
def test_pkg_skip_component(default_requires):
    conanfile_a = textwrap.dedent("""
        from conan import ConanFile
        class PkgConfigConan(ConanFile):
            name = "pkg_a"
            version = "0.1"
            settings = "build_type", "os", "compiler"
            def package_info(self):
                self.cpp_info.set_property("pkg_config_name", "none")
        """)
    default_requires_line = 'self.cpp_info.components["cmp1"].requires = ["pkg_a::pkg_a"]' if default_requires else ""
    conanfile_b = textwrap.dedent(f"""
        from conan import ConanFile
        class PkgConfigConan(ConanFile):
            name = "pkg_b"
            version = "0.1"
            requires = "pkg_a/0.1"
            settings = "build_type", "os", "compiler"
            def package_info(self):
                self.cpp_info.components["cmp1"].set_property("pkg_config_name", "b-cmp1")
                {default_requires_line}
        """)
    conanfile_c = textwrap.dedent("""
            from conan import ConanFile
            class PkgConfigConan(ConanFile):
                name = "pkg_c"
                version = "0.1"
                settings = "build_type", "os", "compiler"
                requires = "pkg_b/0.1"
                def package_info(self):
                    self.cpp_info.components["cmp2"].set_property("pkg_config_name", "none")
            """)
    tc = TestClient()
    tc.save({"a/conanfile.py": conanfile_a,
             "b/conanfile.py": conanfile_b,
             "c/conanfile.py": conanfile_c})
    tc.run("create a")
    tc.run("create b")
    tc.run("create c")

    tc.run("install --requires=pkg_c/0.1 --generator=PkgConfigDeps -of=out-pkgconfig")
    tc.run("install --requires=pkg_c/0.1 --generator=CMakeDeps -of=out-cmake")
    tc.run("install --requires=pkg_c/0.1 --generator=CMakeConfigDeps -of=out-cmake-config")

    pkg_b_cmake_content = tc.load(os.path.join("out-cmake", "pkg_b-Target-release.cmake"))
    expected = """set_property(TARGET pkg_b_DEPS_TARGET
             APPEND PROPERTY INTERFACE_LINK_LIBRARIES
             $<$<CONFIG:Release>:${pkg_b_FRAMEWORKS_FOUND_RELEASE}>
             $<$<CONFIG:Release>:${pkg_b_SYSTEM_LIBS_RELEASE}>
             $<$<CONFIG:Release>:pkg_a::pkg_a>)"""
    assert expected in pkg_b_cmake_content

    # when default_requires=False, it fails
    pkg_b_cmake_config_content = tc.load(os.path.join("out-cmake-config", "pkg_b-Targets-release.cmake"))
    expected = """set_property(TARGET pkg_b::cmp1 APPEND PROPERTY INTERFACE_LINK_LIBRARIES
             "$<$<CONFIG:RELEASE>:pkg_a::pkg_a>")"""
    assert expected in pkg_b_cmake_config_content

    # when default_requires=False, it fails
    pkg_b_cmp1_content = tc.load(os.path.join("out-pkgconfig", "b-cmp1.pc"))
    pkg_b_cmp1_requires = get_requires_from_content(pkg_b_cmp1_content)
    assert "none" in pkg_b_cmp1_requires
