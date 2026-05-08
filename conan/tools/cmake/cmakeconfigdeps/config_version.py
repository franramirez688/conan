import textwrap

from conan.errors import ConanException


class ConfigVersionTemplate2:
    """
    foo-config-version.cmake
    """
    def __init__(self, cmake_info):
        self._cmake_info = cmake_info

    @property
    def context(self):
        policy = self._cmake_info.properties.get("cmake_config_version_compat")
        if policy is None:
            policy = "SameMajorVersion"
        if policy not in ("AnyNewerVersion", "SameMajorVersion", "SameMinorVersion", "ExactVersion"):
            raise ConanException(f"Unknown cmake_config_version_compat={policy} in {self._cmake_info.config_version_filename}")
        version = self._cmake_info.properties.get("system_package_version")
        version = version or self._cmake_info.pkg_version
        return {"version": version,
                "policy": policy}

    @property
    def template(self):
        # https://gitlab.kitware.com/cmake/cmake/blob/master/Modules/BasicConfigVersion-SameMajorVersion.cmake.in
        # This will be at XXX-config-version.cmake
        # AnyNewerVersion|SameMajorVersion|SameMinorVersion|ExactVersion
        ret = textwrap.dedent("""\
            set(PACKAGE_VERSION "{{ version }}")

            if(PACKAGE_VERSION VERSION_LESS PACKAGE_FIND_VERSION)
                set(PACKAGE_VERSION_COMPATIBLE FALSE)
            else()
                {% if policy == "AnyNewerVersion" %}
                set(PACKAGE_VERSION_COMPATIBLE TRUE)
                {% elif policy == "SameMajorVersion" %}
                if("{{ version }}" MATCHES "^([0-9]+)\\\\.")
                    set(CVF_VERSION_MAJOR {{ '${CMAKE_MATCH_1}' }})
                else()
                    set(CVF_VERSION_MAJOR "{{ version }}")
                endif()

                if(PACKAGE_FIND_VERSION_MAJOR STREQUAL CVF_VERSION_MAJOR)
                    set(PACKAGE_VERSION_COMPATIBLE TRUE)
                else()
                    set(PACKAGE_VERSION_COMPATIBLE FALSE)
                endif()
                {% elif policy == "SameMinorVersion" %}
                if("{{ version }}" MATCHES "^([0-9]+)\\.([0-9]+)")
                    set(CVF_VERSION_MAJOR "${CMAKE_MATCH_1}")
                    set(CVF_VERSION_MINOR "${CMAKE_MATCH_2}")
                else()
                    set(CVF_VERSION_MAJOR "{{ version }}")
                    set(CVF_VERSION_MINOR "")
                endif()
                if((PACKAGE_FIND_VERSION_MAJOR STREQUAL CVF_VERSION_MAJOR) AND
                    (PACKAGE_FIND_VERSION_MINOR STREQUAL CVF_VERSION_MINOR))
                  set(PACKAGE_VERSION_COMPATIBLE TRUE)
                else()
                  set(PACKAGE_VERSION_COMPATIBLE FALSE)
                endif()
                {% elif policy == "ExactVersion" %}
                if("{{ version }}" MATCHES "^([0-9]+)\\.([0-9]+)\\.([0-9]+)")
                    set(CVF_VERSION_MAJOR "${CMAKE_MATCH_1}")
                    set(CVF_VERSION_MINOR "${CMAKE_MATCH_2}")
                    set(CVF_VERSION_MINOR "${CMAKE_MATCH_3}")
                else()
                    set(CVF_VERSION_MAJOR "{{ version }}")
                    set(CVF_VERSION_MINOR "")
                    set(CVF_VERSION_PATCH "")
                endif()
                if((PACKAGE_FIND_VERSION_MAJOR STREQUAL CVF_VERSION_MAJOR) AND
                    (PACKAGE_FIND_VERSION_MINOR STREQUAL CVF_VERSION_MINOR) AND
                    (PACKAGE_FIND_VERSION_PATCH STREQUAL CVF_VERSION_PATCH))
                  set(PACKAGE_VERSION_COMPATIBLE TRUE)
                else()
                  set(PACKAGE_VERSION_COMPATIBLE FALSE)
                endif()
                {% endif %}

                if(PACKAGE_FIND_VERSION STREQUAL PACKAGE_VERSION)
                    set(PACKAGE_VERSION_EXACT TRUE)
                endif()
            endif()
            """)
        return ret
