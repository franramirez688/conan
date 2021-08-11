import functools
import os
import time

from tqdm import tqdm

import conans
from conans import __version__ as client_version
from conans.cli.output import ConanOutput
from conans.client.api.helpers.search import Search
from conans.client.cache.cache import ClientCache
from conans.client.conf.required_version import check_required_conan_version
from conans.client.generators import GeneratorManager
from conans.client.graph.graph_binaries import GraphBinariesAnalyzer
from conans.client.graph.graph_manager import GraphManager
from conans.client.graph.proxy import ConanProxy
from conans.client.graph.python_requires import PyRequireLoader
from conans.client.graph.range_resolver import RangeResolver
from conans.client.hook_manager import HookManager
from conans.client.loader import ConanFileLoader
from conans.client.migrations import ClientMigrator
from conans.client.remote_manager import RemoteManager
from conans.client.rest.auth_manager import ConanApiAuthManager
from conans.client.rest.conan_requester import ConanRequester
from conans.client.rest.rest_client import RestApiClientFactory
from conans.client.runner import ConanRunner
from conans.client.tools.env import environment_append
from conans.client.userio import UserIO
from conans.errors import ConanException, NotFoundException, PackageNotFoundException, \
    ConanConnectionError
from conans.model.ref import ConanFileReference, PackageReference
from conans.model.version import Version
from conans.paths import get_conan_user_home
from conans.search.search import search_packages
from conans.tools import set_global_instances
from conans.util.dates import from_timestamp_to_iso8601
from conans.util.log import configure_logger


class ConanApp(object):
    def __init__(self, cache_folder, user_io, http_requester=None, runner=None):
        # User IO, interaction and logging
        self.user_io = user_io
        self.out = self.user_io.out

        self.cache_folder = cache_folder
        self.cache = ClientCache(self.cache_folder, self.out)
        self.config = self.cache.config
        if self.config.non_interactive:
            self.user_io.disable_input()

        # Adjust CONAN_LOGGING_LEVEL with the env readed
        conans.util.log.logger = configure_logger(self.config.logging_level,
                                                  self.config.logging_file)
        conans.util.log.logger.debug("INIT: Using config '%s'" % self.cache.conan_conf_path)

        self.hook_manager = HookManager(self.cache.hooks_path, self.config.hooks, self.out)
        # Wraps an http_requester to inject proxies, certs, etc
        self.requester = ConanRequester(self.config, http_requester)
        # To handle remote connections
        artifacts_properties = self.cache.read_artifacts_properties()
        rest_client_factory = RestApiClientFactory(self.out, self.requester, self.config,
                                                   artifacts_properties=artifacts_properties)
        # Wraps RestApiClient to add authentication support (same interface)
        auth_manager = ConanApiAuthManager(rest_client_factory, self.user_io, self.cache.localdb)
        # Handle remote connections
        self.remote_manager = RemoteManager(self.cache, auth_manager, self.out, self.hook_manager)

        # Adjust global tool variables
        set_global_instances(self.out, self.requester, self.config)

        self.runner = runner or ConanRunner(self.config.print_commands_to_output,
                                            self.config.generate_run_log_file,
                                            self.config.log_run_to_output,
                                            self.out)

        self.proxy = ConanProxy(self.cache, self.out, self.remote_manager)
        self.range_resolver = RangeResolver(self.cache, self.remote_manager)
        self.generator_manager = GeneratorManager()
        self.pyreq_loader = PyRequireLoader(self.proxy, self.range_resolver)
        self.loader = ConanFileLoader(self.runner, self.out,
                                      self.generator_manager, self.pyreq_loader, self.requester)
        self.binaries_analyzer = GraphBinariesAnalyzer(self.cache, self.out, self.remote_manager)
        self.graph_manager = GraphManager(self.out, self.cache, self.remote_manager, self.loader,
                                          self.proxy, self.range_resolver, self.binaries_analyzer)

    def load_remotes(self, remote_name=None, update=False, check_updates=False):
        remotes = self.cache.registry.load_remotes()
        if remote_name:
            remotes.select(remote_name)
        self.pyreq_loader.enable_remotes(update=update, check_updates=check_updates, remotes=remotes)
        return remotes


def api_method(f):
    """Useful decorator to manage Conan API methods"""
    @functools.wraps(f)
    def wrapper(api, *args, **kwargs):
        error = None
        results = None
        try:  # getcwd can fail if Conan runs on an non-existing folder
            old_curdir = os.getcwd()
        except EnvironmentError:
            old_curdir = None
        try:
            api.create_app()
            with environment_append(api.app.cache.config.env_vars):
                results = f(api, *args, **kwargs)
        except (NotFoundException, PackageNotFoundException):
            # This exception must be caught manually due to a server inconsistency:
            # Artifactory API returns an empty result if the recipe doesn't exist, but
            # Conan Server returns a 404. This probably should be fixed server side,
            # but in the meantime we must handle it here
            pass
        except ConanConnectionError as e:
            error = f"There was a connection problem: {str(e)}"
        except BaseException as e:
            error = str(e)
        finally:
            if old_curdir:
                os.chdir(old_curdir)
            # Let's return the results and any possible error
            return results, error
    return wrapper


class ConanAPIV2(object):
    def __init__(self, cache_folder=None, quiet=True, user_io=None, http_requester=None,
                 runner=None):
        self.out = ConanOutput(quiet=quiet)
        self.user_io = user_io or UserIO(out=self.out)
        self.cache_folder = cache_folder or os.path.join(get_conan_user_home(), ".conan")
        self.http_requester = http_requester
        self.runner = runner
        self.app = None  # Api calls will create a new one every call

        # Migration system
        migrator = ClientMigrator(self.cache_folder, Version(client_version), self.out)
        migrator.migrate()
        check_required_conan_version(self.cache_folder, self.out)

    def create_app(self):
        self.app = ConanApp(self.cache_folder, self.user_io, self.http_requester, self.runner)

    @api_method
    def user_list(self, remote_name=None):
        self.out.scope = "MyScope"
        self.out.debug("debug message")
        self.out.info("info message")
        self.out.warning("warning message")
        self.out.scope = ""
        self.out.error("error message")
        self.out.critical("critical message")
        for _ in tqdm(range(10)):
            time.sleep(.08)
            self.out.info("doing something")

        if not remote_name or "*" in remote_name:
            info = {"remote1": {"user": "someuser1"},
                    "remote2": {"user": "someuser2"},
                    "remote3": {"user": "someuser3"},
                    "remote4": {"user": "someuser4"}}
        else:
            info = {"{}".format(remote_name): {"user": "someuser1"}}
        return info

    @api_method
    def user_add(self, remote_name, user_name, user_password, force_add=False):
        return {}

    @api_method
    def user_remove(self, remote_name):
        return {}

    @api_method
    def user_update(self, user_name, user_pasword):
        return {}

    @api_method
    def get_active_remotes(self, remote_names):
        remotes = self.app.cache.registry.load_remotes()
        all_remotes = remotes.all_values()

        if not all_remotes:
            raise ConanException("The remotes registry is empty. "
                                 "Please add at least one valid remote.")
        # If no remote is specified, search in all of them
        if not remote_names:
            # Exclude disabled remotes
            all_remotes = [remote for remote in all_remotes if not remote.disabled]
            return all_remotes

        active_remotes = []
        for remote_name in remote_names:
            remote = remotes[remote_name]
            active_remotes.append(remote)

        return active_remotes

    @api_method
    def search_local_recipes(self, query):
        remotes = self.app.cache.registry.load_remotes()
        search = Search(self.app.cache, self.app.remote_manager, remotes)
        references = search.search_local_recipes(query)
        results = []
        for reference in references:
            result = {
                "name": reference.name,
                "id": repr(reference)
            }
            results.append(result)
        return results

    @api_method
    def search_remote_recipes(self, query, remote):
        remotes = self.app.cache.registry.load_remotes()
        search = Search(self.app.cache, self.app.remote_manager, remotes)
        results = []
        remote_references = search.search_remote_recipes(query, remote.name)
        for remote_name, references in remote_references.items():
            for reference in references:
                result = {
                    "name": reference.name,
                    "id": repr(reference)
                }
                results.append(result)
        return results

    def _get_revisions(self, ref, remote=None):
        if isinstance(ref, PackageReference):
            method_name = 'get_package_revisions'
        elif isinstance(ref, ConanFileReference):
            method_name = 'get_recipe_revisions'
        else:
            raise ConanException(f"Unknown reference type: {ref}")

        # Let's get all the revisions from a remote server
        if remote:
            results = getattr(self.app.remote_manager, method_name)(ref, remote=remote)
        else:
            # Let's get the revisions from the local cache
            revs = getattr(self.app.cache, method_name)(ref)
            results = []
            for revision in revs:
                timestamp = self.app.cache.get_timestamp(revision)
                result = {
                    "revision": revision.revision,
                    "time": timestamp
                }
                results.append(result)
        return results

    @api_method
    def get_package_revisions(self, reference, remote=None):
        """
        Get all the recipe revisions given a reference from cache or remote.

        :param reference: `PackageReference` without the revision
        :param remote: `Remote` object
        :return: `list` of `dict` with all the results, e.g.,
                    [
                      {
                        "revision": "80b7cbe095ac7f38844b6511e69e453a",
                        "time": "2021-07-20 00:56:25 UTC"
                      }
                    ]
        """
        return self._get_revisions(reference, remote=remote)

    @api_method
    def get_recipe_revisions(self, reference, remote=None):
        """
        Get all the recipe revisions given a reference from cache or remote.

        :param reference: `ConanFileReference` without the revision
        :param remote: `Remote` object
        :return: `list` of `dict` with all the results, e.g.,
                  [
                      {
                        "revision": "80b7cbe095ac7f38844b6511e69e453a",
                        "time": "2021-07-20 00:56:25 UTC"
                      }
                  ]
        """
        return self._get_revisions(reference, remote=remote)

    @api_method
    def get_package_ids(self, reference, remote=None):
        """
        Get all the Package IDs given a recipe revision from cache or remote.

        Note: if reference does not have the revision, we'll return the Package IDs for
        the latest recipe revision by default

        :param reference: `ConanFileReference` with/without revision
        :param remote: `Remote` object
        :return: `dict` with the reference revision and the results with the package_id as keys, e.g.
                  {
                    "reference": "libcurl/7.77.0#2a9c4fcc8d76d891e4db529efbe24242",
                    "results": {
                        "d5f16437dd4989cc688211b95c24525589acaafd": {
                            "settings": {"compiler": "apple-clang",...},
                            "options": {'options': {'shared': 'False',...}},
                            "requires": ['mylib/1.0.8:3df6ebb8a308d309e882b21988fd9ea103560e16',...]
                        }
                    }
                  }
        """
        if remote:
            rrev = reference if reference.revision else \
                self.app.remote_manager.get_latest_recipe_revision(reference, remote)
            packages_props = self.app.remote_manager.search_packages(remote, rrev, None)
        else:
            rrev = reference if reference.revision else self.app.cache.get_latest_rrev(reference)
            package_ids = self.app.cache.get_package_ids(rrev)
            package_layouts = []
            for pkg in package_ids:
                latest_prev = self.app.cache.get_latest_prev(pkg)
                package_layouts.append(self.app.cache.pkg_layout(latest_prev))
            packages_props = search_packages(package_layouts, None)

        return {
            "reference": repr(rrev),
            "results": packages_props
        }


Conan = ConanAPIV2
