"""Compile implementation modules for the CPython 3.11 stable ABI."""

from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup
from setuptools.command.build_py import build_py

BOOTSTRAP = {"__init__", "__main__"}


class BootstrapOnly(build_py):
    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        return [item for item in modules if item[1] in BOOTSTRAP]


extensions = [
    Extension(
        f"httpcrabber.{path.stem}", [path.as_posix()],
        define_macros=[("Py_LIMITED_API", "0x030B0000")], py_limited_api=True,
    )
    for path in sorted(Path("src/httpcrabber").glob("*.py"))
    if path.stem not in BOOTSTRAP
]

setup(
    ext_modules=cythonize(extensions, build_dir="build/cython",
                          compiler_directives={"language_level": 3, "annotation_typing": False}),
    cmdclass={"build_py": BootstrapOnly},
    options={"bdist_wheel": {"py_limited_api": "cp311"}},
)
