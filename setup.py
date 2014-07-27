#!/usr/bin/env python

from __future__ import absolute_import, division, print_function

import os
import setuptools

base_dir = os.path.dirname(__file__)

about = {}
with open(os.path.join(base_dir, "pugbot_ng", "__about__.py")) as f:
    exec(f.read(), about)

with open(os.path.join(base_dir, "README.rst")) as f:
    long_description = f.read()

setuptools.setup(
    name=about["__title__"],
    version=about["__version__"],

    description=about["__summary__"],
    long_description=long_description,
    license=about["__license__"],
    url=about["__uri__"],

    author=about["__author__"],
    author_email=about["__email__"],

    classifiers=[
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: BSD License",
        "Natural Language :: English",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Operating System :: POSIX :: BSD",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Communications :: Chat :: Internet Relay Chat"
    ],

    packages=["pugbot_ng"],
    install_requires=[
        "irc == 8.9.1",
        "jaraco.timing == 1.0",
        "jaraco.util == 10.2",
        "more-itertools == 2.2",
        "six == 1.7.3"
    ],
    entry_points={
        "console_scripts": ["pugbot_ng=pugbot_ng.pugbot_ng:main"]
    }
)
