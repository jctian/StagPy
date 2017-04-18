"""definition of each subcommands"""

from inspect import getdoc
from . import constants, misc, field, rprof, time_series, plates, stagyydata
from . import __version__


def field_cmd(args):
    """plot snapshots of fields"""
    misc.plot_backend(args)
    field.field_cmd(args)


def rprof_cmd(args):
    """plot radial profiles"""
    misc.plot_backend(args)
    rprof.rprof_cmd(args)


def time_cmd(args):
    """plot time series"""
    misc.plot_backend(args)
    time_series.time_cmd(args)


def plates_cmd(args):
    """plate analysis"""
    misc.plot_backend(args)
    if args.plot is not None:
        for var, meta in constants.PLATES_VAR_LIST.items():
            misc.set_arg(args, meta.arg, var in args.plot)
    plates.plates_cmd(args)


def info_cmd(args):
    """Print basic information about StagYY run"""
    sdat = stagyydata.StagyyData(args.path)
    lsnap = sdat.snaps.last
    lstep = sdat.steps.last
    lfields = []
    for fvar in constants.FIELD_VARS:
        if lsnap.fields[fvar] is not None:
            lfields.append(fvar)
    print('StagYY run in {}'.format(sdat.path))
    print('Last timestep:',
          '  istep: {}'.format(lstep.istep),
          '  time:  {}'.format(lstep.timeinfo['t']),
          '  <T>:   {}'.format(lstep.timeinfo['Tmean']),
          sep='\n')
    print('Last snapshot (istep {}):'.format(lsnap.istep),
          '  isnap: {}'.format(lsnap.isnap),
          '  time:  {}'.format(lsnap.timeinfo['t']),
          '  output fields: {}'.format(','.join(lfields)),
          sep='\n')


def var_cmd(_):
    """display a list of available variables"""
    print('field:')
    print(*('{}: {}'.format(v, m.description)
          for v, m in constants.FIELD_VARS.items()), sep='\n')
    print(*('{}: {}'.format(v, getdoc(m.description))
          for v, m in constants.FIELD_VARS_EXTRA.items()), sep='\n')
    print()
    print('rprof:')
    print(*('{}: {}'.format(v, m.description)
          for v, m in constants.RPROF_VARS.items()), sep='\n')
    print(*('{}: {}'.format(v, getdoc(m.description))
          for v, m in constants.RPROF_VARS_EXTRA.items()), sep='\n')
    print()
    print('time:')
    print(*('{}: {}'.format(v, m.description)
          for v, m in constants.TIME_VARS.items()), sep='\n')
    print(*('{}: {}'.format(v, getdoc(m.description))
          for v, m in constants.TIME_VARS_EXTRA.items()), sep='\n')
    print()
    print('plates:')
    print(*('{}: {}'.format(v, m.name)
          for v, m in constants.PLATES_VAR_LIST.items()), sep='\n')


def version_cmd(_):
    """print current version"""
    print('stagpy version: {}'.format(__version__))
