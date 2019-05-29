# -*- coding: utf-8 -*-

from pyworxcloud import __version__
import setuptools

setuptools.setup(
    name = 'pyworxcloud',
    version = __version__,
    description = 'Worx Landroid API library',
    author = 'Morten Trab',
    author_email = 'morten@trab.dk',
    license= 'MIT',
    url = 'https://github.com/mtrab/pyworxcloud',
    packages=setuptools.find_packages(),
)