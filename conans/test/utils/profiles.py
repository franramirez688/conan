import os

from conan.tools.env.environment import ProfileEnvironment
from conans.model.options import OptionsValues
from conans.model.profile import Profile
from conans.util.files import save


def create_profile(folder, name, settings=None, package_settings=None, options=None,
                   conf=None, buildenv=None):
    profile = Profile()
    profile.settings = settings or {}

    if package_settings:
        profile.package_settings = package_settings

    if options:
        profile.options = OptionsValues(options)

    if conf:
        _conf = "\n".join(conf) if isinstance(conf, list) else conf
        profile.conf.loads(_conf)

    if buildenv:
        buildenv_ = "\n".join(buildenv) if isinstance(buildenv, list) else buildenv
        profile.buildenv = ProfileEnvironment.loads(buildenv_)

    save(os.path.join(folder, name), profile.dumps())
