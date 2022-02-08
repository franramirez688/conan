import textwrap

import pytest

from conans.errors import ConanException
from conans.model.conf import ConfDefinition


@pytest.fixture()
def conf_definition():
    text = textwrap.dedent("""\
        tools.microsoft.msbuild:verbosity=minimal
        user.company.toolchain:flags=someflags
    """)
    c = ConfDefinition()
    c.loads(text)
    return c, text


def test_conf_definition(conf_definition):
    c, text = conf_definition
    # Round trip
    assert c.dumps() == text
    # access
    assert c["tools.microsoft.msbuild:verbosity"] == "minimal"
    assert c["user.company.toolchain:flags"] == "someflags"
    assert c["tools.microsoft.msbuild:nonexist"] is None
    assert c["nonexist:nonexist"] is None
    # bool
    assert bool(c)
    assert not bool(ConfDefinition())


def test_conf_update(conf_definition):
    c, _ = conf_definition
    text = textwrap.dedent("""\
        user.company.toolchain:flags=newvalue
        another.something:key=value
    """)
    c2 = ConfDefinition()
    c2.loads(text)
    c.update_conf_definition(c2)
    result = textwrap.dedent("""\
        tools.microsoft.msbuild:verbosity=minimal
        user.company.toolchain:flags=newvalue
        another.something:key=value
    """)
    assert c.dumps() == result


def test_conf_rebase(conf_definition):
    c, _ = conf_definition
    text = textwrap.dedent("""\
       user.company.toolchain:flags=newvalue
       another.something:key=value""")
    c2 = ConfDefinition()
    c2.loads(text)
    c.rebase_conf_definition(c2)
    # The c profile will have precedence, and "
    result = textwrap.dedent("""\
        tools.microsoft.msbuild:verbosity=minimal
        user.company.toolchain:flags=someflags
    """)
    assert c.dumps() == result


def test_conf_error_per_package():
    text = "*:core:verbosity=minimal"
    c = ConfDefinition()
    with pytest.raises(ConanException,
                       match=r"Conf '\*:core:verbosity' cannot have a package pattern"):
        c.loads(text)


def test_conf_error_uppercase():
    text = "tools.something:Verbosity=minimal"
    c = ConfDefinition()
    with pytest.raises(ConanException, match=r"Conf 'tools.something:Verbosity' must be lowercase"):
        c.loads(text)
    text = "tools.Something:verbosity=minimal"
    c = ConfDefinition()
    with pytest.raises(ConanException,
                       match=r"Conf 'tools.Something:verbosity' must be lowercase"):
        c.loads(text)


def test_parse_spaces():
    text = "core:verbosity = minimal"
    c = ConfDefinition()
    c.loads(text)
    assert c["core:verbosity"] == "minimal"


def test_conf_actions(conf_definition):
    c, _ = conf_definition
    text = textwrap.dedent("""\
    tools.microsoft.msbuild:verbosity=+another
    user.company.toolchain:flags+=moreflags
    # tools.cmake:njobs=5
    # tools.flags:cc=-first 1 -second 2
    # tools.flags:cc+=-third 3
    # tools.flags:cxx=-first 1
    # tools.cmake:njobs=!
    # tools.flags:cxx=+-second 2
    # tools.flags:cxx=+-third 3
    """)
    c2 = ConfDefinition()
    c2.loads(text)
    c.update_conf_definition(c2)
    result = textwrap.dedent("""\
    tools.microsoft.msbuild:verbosity=another
    tools.microsoft.msbuild:verbosity+=minimal
    user.company.toolchain:flags=someflags
    user.company.toolchain:flags+=moreflags
    """)
    assert c.dumps() == result
