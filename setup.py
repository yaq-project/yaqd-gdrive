#! /usr/bin/env python3
import os
from setuptools import setup, find_packages


here = os.path.abspath(os.path.dirname(__file__))


def read(fname):
    return open(os.path.join(here, fname)).read()


with open(os.path.join(here, "yaqd_gdrive", "VERSION")) as version_file:
    version = version_file.read().strip()

extra_files = {"yaqd_gdrive": ["VERSION"]}

setup(
    name="yaqd-gdrive",
    packages=find_packages(exclude=("tests", "tests.*")),
    package_data=extra_files,
    python_requires=">=3.7",
    setup_requires=["pytest-runner"],
    tests_require=["pytest", "pytest-cov"],
    install_requires=["yaqd-core", "aiohttp"],
    extras_require={
        "docs": ["sphinx", "sphinx-gallery>=0.3.0", "sphinx-rtd-theme"],
        "dev": ["black", "pre-commit", "pydocstyle"],
    },
    version=version,
    description="Google Drive yaq daemon",
    # long_description=read("README.rst"),
    author="yaq Developers",
    license="LGPL v3",
    url="http://gitlab.com/yaq/yaqd-gdrive",
    project_urls={
        "Source": "https://gitlab.com/yaq/yaqd-gdrive",
        "Documentation": "https://yaq.fyi",
        "Issue Tracker": "https://gitlab.com/yaq/yaqd-gdrive/issues",
    },
    entry_points={"console_scripts": ["yaqd-gdrive=yaqd_gdrive._gdrive:GDrive.main"]},
    keywords="spectroscopy science multidimensional hardware",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Scientific/Engineering",
    ],
)
