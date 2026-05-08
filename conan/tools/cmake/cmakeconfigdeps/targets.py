import textwrap


class TargetsTemplate2:
    """
    FooTargets.cmake
    """
    def __init__(self, cmake_info):
        self._cmake_info = cmake_info

    @property
    def context(self):
        return {"filename": self._cmake_info.targets_filename}

    @property
    def template(self):
        return textwrap.dedent("""\
            include_guard()
            message(STATUS "Conan: Configuring Targets for {{ filename }}")

            # Load information for each installed configuration.
            file(GLOB _target_files "${CMAKE_CURRENT_LIST_DIR}/{{filename}}-Targets-*.cmake")
            foreach(_target_file IN LISTS _target_files)
              include("${_target_file}")
            endforeach()

            file(GLOB _build_files "${CMAKE_CURRENT_LIST_DIR}/{{filename}}-TargetsBuild-*.cmake")
            foreach(_build_file IN LISTS _build_files)
              include("${_build_file}")
            endforeach()
            """)
