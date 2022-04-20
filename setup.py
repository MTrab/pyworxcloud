# -*- coding: utf-8 -*-

import setuptools

from pyworxcloud import __version__

# requirements = ['paho-mqtt==1.6.1',
# 'pyOpenSSL==22.0.0',
# 'ratelimit==2.2.1']

with open("requirements.txt") as reqs_file:
    requirements = reqs_file.readlines()

setuptools.setup(
    name="pyworxcloud",
    version=__version__,
    description="Worx Landroid API library",
    author="Morten Trab",
    author_email="morten@trab.dk",
    license="MIT",
    url="https://github.com/mtrab/pyworxcloud",
    packages=setuptools.find_packages(),
    install_requires=requirements,
)
