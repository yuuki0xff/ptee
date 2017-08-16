#!/usr/bin/env python3

from setuptools import setup

setup(
    name='ptee',
    version='1.0',
    description='Parallel writable tee command',
    author='yuuki0xff',
    author_email='yuuki0xff@gmail.com',
    url='https://github.com/yuuki0xff/ptee',
    license='MIT',
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: Implementation :: CPython',
        'License :: OSI Approved :: MIT License',
        'Environment :: Console',
        'Topic :: Utilities',
        'Topic :: Text Processing :: Filters',
    ],
    packages=['ptee'],
    entry_points={
        'console_scripts': [
            'ptee = ptee.ptee_cmd:main',
            'pteeexec = ptee.pteeexec_cmd:main',
        ],
    },
)
