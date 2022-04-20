# -*- coding: utf-8 -*-

import setuptools
from pip.req import parse_requirements

from pyworxcloud import __version__

# requirements = ['paho-mqtt==1.6.1',
# 'pyOpenSSL==22.0.0',
# 'ratelimit==2.2.1']

requirements = parse_requirements("requirements.txt", session="hack")

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
