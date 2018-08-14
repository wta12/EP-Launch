import glob
import os
import sys

from cx_Freeze import setup as cx_setup, Executable

from eplaunch import NAME, VERSION
# from eplaunch.utilities.crossplatform import Platform

include_files = []
default_workflows = glob.glob("eplaunch/workflows/default/site_location.py")
workflow_tuples = [(x, os.path.join('lib', x)) for x in default_workflows]
include_files.extend(workflow_tuples)

include_dependencies = []
#
# if Platform.get_current_platform() == Platform.LINUX:
#     include_dependencies.append(("/usr/lib/libpng12.so.0.37.0", "libpng.so.0"))

# Dependencies are automatically detected, but it might need fine tuning.
build_exe_options = {
    "packages": ["eplaunch", "os", "wx", "pubsub.pub"],
    "excludes": ["tkinter"],
    "include_files": include_files + include_dependencies
}

# GUI applications require a different base on Windows (the default is for a
# console application).
base = None
if sys.platform == "win32":
    base = "Win32GUI"

cx_setup(
    name=NAME,
    version=VERSION,
    description='Graphical Interface and Workflow Manager for EnergyPlus',
    executables=[Executable("eplaunch/runner.py", targetName="EPLaunch", base=base)],
    url='https://github.com/NREL/EP-Launch',
    license='ModifiedBSD',
    options={"build_exe": build_exe_options},
)
