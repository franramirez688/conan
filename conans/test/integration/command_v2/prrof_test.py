import json
import os
import re
import textwrap
from unittest.mock import patch, Mock

import pytest

from conans.errors import ConanException, ConanConnectionError
from conans.model.recipe_ref import RecipeReference
from conans.model.package_ref import PkgReference
from conans.test.assets.genconanfile import GenConanfile
from conans.test.utils.tools import TestClient, TestServer


class TestListBase:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.client = TestClient()

    def _add_remote(self, remote_name):
        self.client.servers[remote_name] = TestServer(users={"username": "passwd"},
                                                      write_permissions=[("*/*@*/*", "*")])
        self.client.update_servers()
        self.client.run("remote login {} username -p passwd".format(remote_name))

    def _upload_recipe(self, remote, ref):
        self.client.save({'conanfile.py': GenConanfile()})
        ref = RecipeReference.loads(ref)
        self.client.run(f"create . --name={ref.name} --version={ref.version} "
                        f"--user={ref.user} --channel={ref.channel}")
        self.client.run("upload --force -r {} {}".format(remote, ref))

    def _upload_full_recipe(self, remote, ref):
        self.client.save({"conanfile.py": GenConanfile("pkg", "0.1").with_package_file("file.h",
                                                                                       "0.1")})
        self.client.run("create . --user=user --channel=channel")
        self.client.run("upload --force -r {} {}".format(remote, "pkg/0.1@user/channel"))

        self.client.save({'conanfile.py': GenConanfile()
                          })
        self.client.run(f"create . --name={ref.name} --version={ref.version} "
                        f"-s os=Macos -s build_type=Release -s arch=x86_64 "
                        f"--user={ref.user} --channel={ref.channel}")
        self.client.run("upload --force -r {} {}".format(remote, ref))

    @staticmethod
    def _get_fake_recipe_refence(recipe_name):
        return f"{recipe_name}#fca0383e6a43348f7989f11ab8f0a92d"

    def _get_lastest_recipe_ref(self, recipe_name):
        return self.client.cache.get_latest_recipe_reference(RecipeReference.loads(recipe_name))

    def _get_lastest_package_ref(self, pref):
        return self.client.cache.get_latest_package_reference(PkgReference.loads(pref))


class Testsbaja(TestListBase):

    def test_search_all_revisions_and_package_ids(self):
        remote1 = "remote1"
        remote2 = "remote2"

        self._add_remote(remote1)
        self._upload_full_recipe(remote1, RecipeReference(name="test_recipe", version="1.0",
                                                          user="user", channel="channel"))
        self._add_remote(remote2)
        self._upload_full_recipe(remote2, RecipeReference(name="test_recipe", version="2.1",
                                                          user="user", channel="channel"))
        self.client.run(f'list *#* -r="*" -c')
        output = str(self.client.out)
        expected_output = textwrap.dedent("""\
        Local Cache:
          test_recipe
            test_recipe/2.1@user/channel#a22316c3831b70763e4405841ee93f27 .*
            test_recipe/1.0@user/channel#a22316c3831b70763e4405841ee93f27 .*
          pkg
            pkg/0.1@user/channel#44a36b797bc85fb66af6acf90cf8f539 .*
        remote1:
          pkg
            pkg/0.1@user/channel#44a36b797bc85fb66af6acf90cf8f539 .*
          test_recipe
            test_recipe/1.0@user/channel#a22316c3831b70763e4405841ee93f27 .*
        remote2:
          pkg
            pkg/0.1@user/channel#44a36b797bc85fb66af6acf90cf8f539 .*
          test_recipe
            test_recipe/2.1@user/channel#a22316c3831b70763e4405841ee93f27 .*
        """)
        assert bool(re.match(expected_output, output, re.MULTILINE))
        self.client.run(f'list test_recipe/*:*#* -r="*" -c')
        output = str(self.client.out)
        expected_output = textwrap.dedent("""\
        Local Cache:
          test_recipe
            test_recipe/2.1@user/channel#4d670581ccb765839f2239cc8dff8fbd (2022-12-28 14:54:38 UTC)
              PID: da39a3ee5e6b4b0d3255bfef95601890afd80709
                PREV: 0ba8627bd47edc3a501e8f0eb9a79e5e (2022-12-28 14:54:38 UTC)
            test_recipe/1.0@user/channel#4d670581ccb765839f2239cc8dff8fbd (2022-12-28 14:54:38 UTC)
              PID: da39a3ee5e6b4b0d3255bfef95601890afd80709
                PREV: 0ba8627bd47edc3a501e8f0eb9a79e5e (2022-12-28 14:54:38 UTC)
        remote1:
          test_recipe
            test_recipe/1.0@user/channel#4d670581ccb765839f2239cc8dff8fbd (2022-12-28 14:54:38 UTC)
              PID: da39a3ee5e6b4b0d3255bfef95601890afd80709
                PREV: 0ba8627bd47edc3a501e8f0eb9a79e5e (2022-12-28 14:54:38 UTC)
        remote2:
          test_recipe
            test_recipe/2.1@user/channel#4d670581ccb765839f2239cc8dff8fbd (2022-12-28 14:54:38 UTC)
              PID: da39a3ee5e6b4b0d3255bfef95601890afd80709
                PREV: 0ba8627bd47edc3a501e8f0eb9a79e5e (2022-12-28 14:54:38 UTC)
        """)
        assert bool(re.match(expected_output, output, re.MULTILINE))
