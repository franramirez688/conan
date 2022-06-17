import fnmatch

from conan.api.conan_api import ConanAPIV2
from conans.cli.command import conan_command, COMMAND_GROUPS, OnceArgument
from conans.cli.conan_app import ConanApp
from conans.client.userio import UserInput
from conans.errors import ConanException


@conan_command(group=COMMAND_GROUPS['consumer'])
def cleaner(conan_api: ConanAPIV2, parser, *args):
    """
    Removes recipes or packages from local cache or a remote.
    - If no remote is specified (-r), the removal will be done in the local conan cache.
    - If a recipe reference is specified, it will remove the recipe and all the packages, unless -p
      is specified, in that case, only the packages matching the specified query (and not the recipe)
      will be removed.
    - If a package reference is specified, it will remove only the package.
    """
    parser.add_argument('-r', '--remote', action=OnceArgument,
                        help='Will remove from the specified remote')
    args = parser.parse_args(*args)

    remote = conan_api.remotes.get(args.remote) if args.remote else None
    all_rrevs = conan_api.search.recipe_revisions("*/*#*")
    latest_rrevs = conan_api.search.recipe_revisions("*/*#latest")
    for rrev in all_rrevs:
        if rrev in latest_rrevs:
            all_prevs = conan_api.search.package_revisions(f"{rrev.repr_notime()}:*#*")
            latest_prevs = conan_api.search.package_revisions(f"{rrev.repr_notime()}:*#latest")
            print(f"Let's go for the latest prev {rrev.repr_notime()}")
            for prev in all_prevs:
                if prev in latest_prevs:
                    print(f"Skipping latest prev {prev.repr_notime()}")
                else:
                    print(f"Removiing latest prev {prev.repr_notime()}")
                    # conan_api.remove.package(prev, remote=remote)
        else:
            print(f"Removiiinggg latest prev {rrev.repr_notime()}")
            # conan_api.remove.recipe(rrev, remote=remote)
