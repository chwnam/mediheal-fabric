from fabric.api import env
from mediheal import origin2local as _origin2local
from mediheal import local2target as _local2target


def origin2local():
    _origin2local(env)


def local2target():
    _local2target(env)


def transplant():
    _origin2local(env)
    _local2target(env)
