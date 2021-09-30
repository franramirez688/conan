import pytest
import platform
import textwrap

from conans.test.assets.pkg_cmake import pkg_cmake
from conans.test.utils.tools import TestClient


@pytest.mark.tool_cmake
@pytest.mark.tool_intel_oneapi
@pytest.mark.xfail(reason="Intel oneAPI Toolkit is not installed on CI yet")
@pytest.mark.skipif(platform.system() != "Linux", reason="Only for Linux")
class TestInteloneAPI:

    @pytest.fixture(autouse=True)
    def _setUp(self):
        self.client = TestClient()
        # Let's create a default hello/0.1 example
        files = pkg_cmake("hello", "0.1")
        self.client.save(files)

    def test_intel_oneapi_and_dpcpp(self):
        intel_profile = textwrap.dedent("""
            [settings]
            os=Linux
            arch=x86_64
            arch_build=x86_64
            compiler=intel-cc
            compiler.mode=dpcpp
            compiler.version=2021.3
            compiler.libcxx=libstdc++
            build_type=Release
            [env]
            CC=dpcpp
            CXX=dpcpp
        """)
        self.client.save({"intel_profile": intel_profile})
        # Build in the cache
        self.client.run('create . --profile:build=intel_profile --profile:host=intel_profile')
        assert ":: initializing oneAPI environment ..." in self.client.out
        assert ":: oneAPI environment initialized ::" in self.client.out
        assert "Check for working CXX compiler: /opt/intel/oneapi/compiler/2021.3.0/linux/bin/dpcpp -- works" in self.client.out
        assert "hello/0.1: Package '5d42bcd2e9be3378ed0c2f2928fe6dc9ea1b0922' created" in self.client.out
