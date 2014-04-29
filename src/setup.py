#!/usr/bin/env python
# encoding: utf-8

import os

from setuptools import setup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

setup(
    name="docker",
    version="0.1.0",
    author="Evgeny Safronov",
    author_email="division494@gmail.com",
    maintainer='Evgeny Safronov',
    maintainer_email='division494@gmail.com',
    url="https://github.com/3Hren/docker-async-client",
    description="Docker asynchronous client.",
    long_description="Docker asynchronous client with using Tornado library with unix socket support.",
    license="LGPLv3+",
    platforms=["Linux", "BSD", "MacOS"],
    include_package_data=True,
    zip_safe=False,
    packages=[
        "docker",
        "docker.internal",
    ],
    install_requires=["tornado >= 3.2"],
    classifiers=[
        # 'Development Status :: 1 - Planning',
        # 'Development Status :: 2 - Pre-Alpha',
        'Development Status :: 3 - Alpha',
        # 'Development Status :: 4 - Beta',
        # 'Development Status :: 5 - Production/Stable',
        # 'Development Status :: 6 - Mature',
        # 'Development Status :: 7 - Inactive',
    ],
)
