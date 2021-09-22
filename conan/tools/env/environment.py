import fnmatch
import os
import textwrap
import platform
from collections import OrderedDict
from contextlib import contextmanager

from conans.errors import ConanException
from conans.util.files import save


class _EnvVarPlaceHolder:
    pass


def environment_wrap_command(conanfile, env_filenames, cmd, cwd=None):
    from conan.tools.microsoft.subsystems import unix_path
    assert env_filenames
    filenames = [env_filenames] if not isinstance(env_filenames, list) else env_filenames
    bats, shs = [], []

    cwd = cwd or os.getcwd()

    for f in filenames:
        f = f if os.path.isabs(f) else os.path.join(cwd, f)
        if f.lower().endswith(".sh"):
            if os.path.isfile(f):
                f = unix_path(conanfile, f)
                shs.append(f)
        elif f.lower().endswith(".bat"):
            if os.path.isfile(f):
                bats.append(f)
        else:  # Simple name like "conanrunenv"
            path_bat = "{}.bat".format(f)
            path_sh = "{}.sh".format(f)
            if os.path.isfile(path_bat):
                bats.append(path_bat)
            elif os.path.isfile(path_sh):
                path_sh = unix_path(conanfile, path_sh)
                shs.append(path_sh)

    if bats and shs:
        raise ConanException("Cannot wrap command with different envs, {} - {}".format(bats, shs))

    if bats:
        launchers = " && ".join('"{}"'.format(b) for b in bats)
        return '{} && {}'.format(launchers, cmd)
    elif shs:
        launchers = " && ".join('. "{}"'.format(f) for f in shs)
        return '{} && {}'.format(launchers, cmd)
    else:
        return cmd


class _EnvValue:
    def __init__(self, name, value=_EnvVarPlaceHolder, separator=" ", path=False):
        self._name = name
        self._values = [] if value is None else value if isinstance(value, list) else [value]
        self._path = path
        self._sep = separator

    def dumps(self):
        result = []
        path = "(path)" if self._path else ""
        if not self._values:  # Empty means unset
            result.append("{}=!".format(self._name))
        elif _EnvVarPlaceHolder in self._values:
            index = self._values.index(_EnvVarPlaceHolder)
            for v in self._values[:index]:
                result.append("{}=+{}{}".format(self._name, path, v))
            for v in self._values[index+1:]:
                result.append("{}+={}{}".format(self._name, path, v))
        else:
            append = ""
            for v in self._values:
                result.append("{}{}={}{}".format(self._name, append, path, v))
                append = "+"
        return "\n".join(result)

    def copy(self):
        return _EnvValue(self._name, self._values, self._sep, self._path)

    @property
    def is_path(self):
        return self._path

    def remove(self, value):
        self._values.remove(value)

    def append(self, value, separator=None):
        if separator is not None:
            self._sep = separator
        if isinstance(value, list):
            self._values.extend(value)
        else:
            self._values.append(value)

    def prepend(self, value, separator=None):
        if separator is not None:
            self._sep = separator
        if isinstance(value, list):
            self._values = value + self._values
        else:
            self._values.insert(0, value)

    def compose_env_value(self, other):
        """
        :type other: _EnvValue
        """
        try:
            index = self._values.index(_EnvVarPlaceHolder)
        except ValueError:  # It doesn't have placeholder
            pass
        else:
            new_value = self._values[:]  # do a copy
            new_value[index:index + 1] = other._values  # replace the placeholder
            self._values = new_value

    def get_str(self, conanfile, placeholder, pathsep=os.pathsep):
        """
        :param conanfile: The conanfile is necessary to get win_bash, path separator, etc.
        :param placeholder: a OS dependant string pattern of the previous env-var value like
        $PATH, %PATH%, et
        :param pathsep: The path separator, typically ; or :
        :return: a string representation of the env-var value, including the $NAME-like placeholder
        """
        values = []
        for v in self._values:
            if v is _EnvVarPlaceHolder:
                if placeholder:
                    values.append(placeholder.format(name=self._name))
            else:
                if self._path:
                    from conan.tools.microsoft.subsystems import unix_path
                    v = unix_path(conanfile, v)
                values.append(v)
        if self._path:
            pathsep = ":" if conanfile.win_bash else pathsep
            return pathsep.join(values)

        return self._sep.join(values)

    def get_value(self, conanfile, pathsep=os.pathsep):
        previous_value = os.getenv(self._name)
        return self.get_str(conanfile, previous_value, pathsep)


class Environment:
    def __init__(self, conanfile):
        # It being ordered allows for Windows case-insensitive composition
        self._values = OrderedDict()  # {var_name: [] of values, including separators}
        self._conanfile = conanfile

    def __bool__(self):
        return bool(self._values)

    __nonzero__ = __bool__

    def copy(self):
        e = Environment(self._conanfile)
        e._values = self._values.copy()
        return e

    def __repr__(self):
        return repr(self._values)

    def dumps(self):
        return "\n".join([v.dumps() for v in reversed(self._values.values())])

    def define(self, name, value, separator=" "):
        self._values[name] = _EnvValue(name, value, separator, path=False)

    def define_path(self, name, value):
        self._values[name] = _EnvValue(name, value, path=True)

    def unset(self, name):
        """
        clears the variable, equivalent to a unset or set XXX=
        """
        self._values[name] = _EnvValue(name, None)

    def append(self, name, value, separator=None):
        self._values.setdefault(name, _EnvValue(name)).append(value, separator)

    def append_path(self, name, value):
        self._values.setdefault(name, _EnvValue(name, path=True)).append(value)

    def prepend(self, name, value, separator=None):
        self._values.setdefault(name, _EnvValue(name)).prepend(value, separator)

    def prepend_path(self, name, value):
        self._values.setdefault(name, _EnvValue(name, path=True)).prepend(value)

    def remove(self, name, value):
        self._values[name].remove(value)

    def save_bat(self, filename, generate_deactivate=True, pathsep=os.pathsep):
        deactivate = textwrap.dedent("""\
            echo Capturing current environment in deactivate_{filename}
            setlocal
            echo @echo off > "deactivate_{filename}"
            echo echo Restoring environment >> "deactivate_{filename}"
            for %%v in ({vars}) do (
                set foundenvvar=
                for /f "delims== tokens=1,2" %%a in ('set') do (
                    if "%%a" == "%%v" (
                        echo set %%a=%%b>> "deactivate_{filename}"
                        set foundenvvar=1
                    )
                )
                if not defined foundenvvar (
                    echo set %%v=>> "deactivate_{filename}"
                )
            )
            endlocal

            """).format(filename=os.path.basename(filename), vars=" ".join(self._values.keys()))
        capture = textwrap.dedent("""\
            @echo off
            {deactivate}
            echo Configuring environment variables
            """).format(deactivate=deactivate if generate_deactivate else "")
        result = [capture]
        for varname, varvalues in self._values.items():
            value = varvalues.get_str(self._conanfile, "%{name}%", pathsep)
            result.append('set {}={}'.format(varname, value))

        content = "\n".join(result)
        save(filename, content)

    def save_ps1(self, filename, generate_deactivate=True, pathsep=os.pathsep):
        # FIXME: This is broken and doesnt work
        deactivate = ""
        capture = textwrap.dedent("""\
            {deactivate}
            """).format(deactivate=deactivate if generate_deactivate else "")
        result = [capture]
        for varname, varvalues in self._values.items():
            value = varvalues.get_str(self._conanfile, "$env:{name}", pathsep)
            result.append('$env:{}={}'.format(varname, value))

        content = "\n".join(result)
        save(filename, content)

    def save_sh(self, filename, generate_deactivate=True, pathsep=os.pathsep):
        deactivate = textwrap.dedent("""\
            echo Capturing current environment in deactivate_{filename}
            echo echo Restoring variables >> deactivate_{filename}
            for v in {vars}
            do
                value=$(printenv $v)
                if [ -n "$value" ]
                then
                    echo export "$v=$value" >> deactivate_{filename}
                else
                    echo unset $v >> deactivate_{filename}
                fi
            done
            echo Configuring environment variables
            """.format(filename=os.path.basename(filename), vars=" ".join(self._values.keys())))
        capture = textwrap.dedent("""\
           {deactivate}
           echo Configuring environment variables
           """).format(deactivate=deactivate if generate_deactivate else "")
        result = [capture]
        for varname, varvalues in self._values.items():
            value = varvalues.get_str(self._conanfile, "${name}", pathsep)
            if value:
                result.append('export {}="{}"'.format(varname, value))
            else:
                result.append('unset {}'.format(varname))

        content = "\n".join(result)
        save(filename, content)

    def save_script(self, name, group="build"):
        if platform.system() == "Windows" and not self._conanfile.win_bash:
            path = os.path.join(self._conanfile.generators_folder, "{}.bat".format(name))
            self.save_bat(path)
        else:
            path = os.path.join(self._conanfile.generators_folder, "{}.sh".format(name))
            self.save_sh(path)

        if group:
            register_env_script(self._conanfile, path, group)

    def compose_env(self, other):
        """
        self has precedence, the "other" will add/append if possible and not conflicting, but
        self mandates what to do. If self has define(), without placeholder, that will remain
        :type other: Environment
        """
        for k, v in other._values.items():
            existing = self._values.get(k)
            if existing is None:
                self._values[k] = v.copy()
            else:
                existing.compose_env_value(v)

        self._conanfile = self._conanfile or other._conanfile
        return self

    # Methods to user access to the environment object as a dict
    def keys(self):
        return self._values.keys()

    def __getitem__(self, name):
        return self._values[name].get_value(self._conanfile)

    def get(self, name, default=None):
        v = self._values.get(name)
        if v is None:
            return default
        return v.get_value(self._conanfile)

    def items(self):
        """returns {str: str} (varname: value)"""
        return {k: v.get_value(self._conanfile) for k, v in self._values.items()}.items()

    def __eq__(self, other):
        """
        :type other: Environment
        """
        return other._values == self._values

    def __ne__(self, other):
        return not self.__eq__(other)

    @contextmanager
    def apply(self):
        apply_vars = self.items()
        old_env = dict(os.environ)
        os.environ.update(apply_vars)
        try:
            yield
        finally:
            os.environ.clear()
            os.environ.update(old_env)


class ProfileEnvironment:
    def __init__(self):
        self._environments = OrderedDict()

    def __repr__(self):
        return repr(self._environments)

    def __bool__(self):
        return bool(self._environments)

    __nonzero__ = __bool__

    def get_env(self, conanfile, ref):
        """ computes package-specific Environment
        it is only called when conanfile.buildenv is called
        the last one found in the profile file has top priority
        """
        result = Environment(conanfile)
        for pattern, env in self._environments.items():
            if pattern is None or fnmatch.fnmatch(str(ref), pattern):
                # Latest declared has priority, copy() necessary to not destroy data
                result = env.copy().compose_env(result)
        return result

    def update_profile_env(self, other):
        """
        :type other: ProfileEnvironment
        :param other: The argument profile has priority/precedence over the current one.
        """
        for pattern, environment in other._environments.items():
            existing = self._environments.get(pattern)
            if existing is not None:
                self._environments[pattern] = environment.compose_env(existing)
            else:
                self._environments[pattern] = environment

    def dumps(self):
        result = []
        for pattern, env in self._environments.items():
            if pattern is None:
                result.append(env.dumps())
            else:
                result.append("\n".join("{}:{}".format(pattern, line) if line else ""
                                        for line in env.dumps().splitlines()))
        if result:
            result.append("")
        return "\n".join(result)

    @staticmethod
    def loads(text):
        result = ProfileEnvironment()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for op, method in (("+=", "append"), ("=+", "prepend"),
                               ("=!", "unset"), ("=", "define")):
                tokens = line.split(op, 1)
                if len(tokens) != 2:
                    continue
                pattern_name, value = tokens
                pattern_name = pattern_name.split(":", 1)
                if len(pattern_name) == 2:
                    pattern, name = pattern_name
                else:
                    pattern, name = None, pattern_name[0]

                # When loading from profile file, latest line has priority
                env = Environment(conanfile=None)
                if method == "unset":
                    env.unset(name)
                else:
                    if value.startswith("(path)"):
                        value = value[6:]
                        method = method + "_path"
                    getattr(env, method)(name, value)

                existing = result._environments.get(pattern)
                if existing is None:
                    result._environments[pattern] = env
                else:
                    result._environments[pattern] = env.compose_env(existing)
                break
            else:
                raise ConanException("Bad env definition: {}".format(line))
        return result


def create_env_script(conanfile, content, filename, group):
    """
    Create a simple script executing a command and register it.
    """
    path = os.path.join(conanfile.generators_folder, filename)
    save(path, content)

    if group:
        register_env_script(conanfile, path, group)


def register_env_script(conanfile, env_script_path, group):
    """
    Add the "env_script_path" to the current list of registered scripts for defined "group"
    These will be mapped to files:
    - conan{group}.bat|sh = calls env_script_path1,... env_script_pathN
    """
    existing = conanfile.env_scripts.setdefault(group, [])
    if env_script_path not in existing:
        existing.append(env_script_path)
