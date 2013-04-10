#!/usr/bin/env python
from __future__ import print_function
# -*- coding: utf-8 -*-

# filename   : camp.py
# created at : 2013-04-10 10:39:15
# author     : Jianing Yang <jianingy.yang AT gmail DOT com>

__author__ = 'Jianing Yang <jianingy.yang AT gmail DOT com>'
from os.path import join as path_join
from sys import stderr

_verbose = False


class CampError(Exception):
    pass


class SpecificationError(CampError):
    pass


class FileError(CampError):
    pass


class CommandError(CampError):
    pass


class FatalError(CampError):
    pass


def data_out(s):
    from pprint import PrettyPrinter
    pp = PrettyPrinter(indent=4)
    pp.pprint(s)


def verbose(s):
    if _verbose:
        print(s, file=stderr)


def error(s):
    from sys import stderr
    print('ERROR:', s, file=stderr)


def info(s):
    print('INFO:', s)


def parse_option(args, spec, options={}, header='', footer=''):
    from re import match as re_match
    from getopt import getopt, GetoptError
    help_message = header
    short_opt, long_opt, opt_cond = '', [], {}
    for line in spec.splitlines():
        match = re_match('([a-z])\|(\w+)([:=])(.+)', line)
        if not match:
            continue
        opt_s, opt_l, opt_v, opt_h = match.groups()
        help_message = (help_message +
                        '\n-%s, --%s\t\t%s' % (opt_s, opt_l, opt_h))
        opt_cond['-' + opt_s] = opt_l
        opt_cond['--' + opt_l] = opt_l
        if opt_v == '=':
            opt_s = opt_s + ':'
            opt_l = opt_l + '='
        short_opt = short_opt + opt_s
        long_opt.append(opt_l)

    help_message = help_message + '\n' + footer
    try:
        opts, args = getopt(args, short_opt, long_opt)
        for optname, optval in opts:
            if optname in opt_cond:
                options[opt_cond[optname]] = optval
        return options
    except GetoptError as err:
        from sys import stderr, exit
        print >>stderr, 'ERROR:', str(err)
        print >>stderr, '\n', help_message, '\n'
        exit(1)


def get_platform():
    return ['x86_64']


def override_installer(platforms, installer, spec):
    from glob import glob
    from yaml import load as yaml_load
    from os.path import basename, isfile
    from copy import deepcopy

    default_yaml = path_join(spec, '_default.yaml')
    if isfile(default_yaml):
        yaml = yaml_load(file(default_yaml).read())
        default = yaml.get('default', {})
        map(lambda x: x in yaml and default.update(yaml[x]), platforms)
    else:
        default = {}

    installer['_default'].update(default)

    for filename in glob(path_join(spec, '[a-z0-9A-Z]*.yaml')):
        name = basename(filename)[0:-len('.yaml')]
        yaml = yaml_load(file(filename).read())
        result = deepcopy(installer['_default'])
        result.update(yaml.get('default', {}))
        map(lambda x: x in yaml and result.update(yaml[x]), platforms)

        if name in installer:
            installer[name].update(result)
        else:
            installer[name] = result

    return installer


def install(options):
    platforms = get_platform()
    installer = dict(_default={})

    # read data from default installer
    spec = path_join(options['base'], 'installers', 'default')
    override_installer(platforms, installer, spec)

    # update with specified installer
    spec = path_join(options['base'], 'installers', options['installer'])
    override_installer(platforms, installer, spec)

    for name, spec in installer.items():

        if name.startswith('_'):
            # skip internal node
            continue

        try:
            # force install via command line option
            if 'force' in options:
                spec['force'] = 1
            do_install(name, spec)
        except CampError as e:
            error('[%s]: %s' % (name, e))


def runcmd(cmd, reason):
    from os import system
    verbose("RUNCMD: " + cmd)
    retval = system(cmd)
    if retval >> 8:
        raise CommandError(reason)
    return retval


def do_install(name, spec):

    from hashlib import sha224 as do_hash
    from re import match as re_match
    from tempfile import mkstemp
    from os.path import dirname, isdir, isfile
    from os import close, makedirs, unlink

    fd, tempfile = mkstemp(prefix='camp-tmp-')
    close(fd)

    try:
        # Step 1. Get source
        source = spec['base'].strip('/') + '/' + spec['source'].strip('/')
        match = re_match('([^:]+)://(.+)', source)
        if not match:
            raise SpecificationError('invalid source')
        schema, path = match.groups()
        if schema not in spec['download']:
            raise SpecificationError('invalid source schema')
        cmd = spec['download'][schema] % dict(source=path, target=tempfile)
        runcmd(cmd, '[%s]: cannot get source file' % name)

        # Step 2. Check
        cmd = spec['check'] % dict(target=tempfile)
        runcmd(cmd, '[%s]: source file has syntax errors' % name)

        # Step 3. run pre-install script
        runcmd(spec['preinst'], '[%s]: preinst script failed' % name)

        # Step 4. Install into target location

        force_install = False

        # Step 4.1 check if file changed
        if isfile(spec['target']):
            local_hash = do_hash(file(spec['target']).read()).hexdigest()
            current_hash = do_hash(file(tempfile).read()).hexdigest()

            if local_hash == current_hash and not spec['force']:
                info('[%s] unchanged, no install needed' % name)
                return
            elif spec['force']:
                force_install = True

        # Step 4.2 install if file do have some changes
        cmd = spec['install'] % dict(source=tempfile, target=spec['target'])
        path = dirname(spec['target'])
        if not isdir(path):
            makedirs(path)
        runcmd(cmd, '[%s]: cannot install source to location' % name)

        # Step 5. run post-install script
        runcmd(spec['postinst'], '[%s]: postinst script failed' % name)

        if force_install:
            info('[%s] force installed' % name)
        else:
            info('[%s] installed' % name)
    except KeyError as e:
        raise SpecificationError('key "%s" not exists in spec' % e.args[0])
    except OSError as e:
        from errno import EEXIST
        if e.errno == EEXIST:
            raise FileError('target "%s" cannot be override' % e.filename)
    except CampError:
        raise
    except Exception as e:
        raise FatalError('unknown error encountered.')
    finally:
        unlink(tempfile)

if __name__ == '__main__':
    from sys import argv
    from os.path import dirname, abspath
    basedir = abspath(path_join(dirname(argv[0]), '..'))
    options = dict(base=basedir, installer='dot1q')
    opt_spec = """b|base=Base directory (default=%s)
i|installer=Install using this installer
f|force:Force install files even if unchanged
v|verbose:Run with verbose messages
h|help:Display this help""" % options['base']
    parse_option(argv[1:], opt_spec, options=options,
                 header="Usage: %s [options]" % argv[0])

    if 'verbose' in options:
        _verbose = True

    install(options)
