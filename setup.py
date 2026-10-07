"""
ChronosMatch — build configuration.

Builds the Cython matching-engine extension in-place::

    python setup.py build_ext --inplace

Or install the whole project in editable mode::

    pip install -e .
"""

from setuptools import setup, find_packages
from Cython.Build import cythonize
from distutils.extension import Extension

# ---------------------------------------------------------------------------
# Cython extension definitions
# ---------------------------------------------------------------------------
extensions = [
    Extension(
        # Dotted module name — must match the import path
        name="chronos.matching_engine.order_book",
        sources=["chronos/matching_engine/order_book.pyx"],
        # No external C libraries needed for the scaffold
        libraries=[],
        # Optimisation flags that are safe on all major compilers
        extra_compile_args=[],
        # language_level is also set in the .pyx header, but make it explicit
        define_macros=[("CYTHON_TRACE", "0")],
    ),
]

setup(
    name="chronos-match",
    version="0.2.0",
    description="Zero-Copy High-Frequency Trading Engine — ChronosMatch",
    packages=find_packages(exclude=["tests*", "scripts*"]),
    # Build Cython sources with:
    #   annotate=True  → generate HTML annotation file for profiling
    #   nthreads=0     → serial build (safe on Windows)
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "cdivision": True,
            "nonecheck": False,
            "embedsignature": True,   # keeps __doc__ in compiled module
        },
        annotate=True,  # produces order_book.html for profiling aid
        nthreads=0,
    ),
    python_requires=">=3.10",
    install_requires=[
        "cython>=3.0.0",
    ],
    zip_safe=False,
)
