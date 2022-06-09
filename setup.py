# -*- coding: utf-8 -*-

import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pyworxcloud",
    description="Landroid cloud API library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Morten Trab",
    author_email="morten@trab.dk",
    license="MIT",
    url="https://github.com/mtrab/pyworxcloud",
    packages=setuptools.find_packages(),
    project_urls={
        "Bug Tracker": "https://github.com/mtrab/pyworxcloud/issues",
    },
    install_requires=["paho-mqtt>=1.6.1", "pyOpenSSL>=22.0.0"],
)
