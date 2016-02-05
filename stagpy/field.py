"""plot fields"""

import numpy as np
from . import constants, misc
from .stagdata import BinData


def plot_scalar(args, stgdat, var):
    """var: one of the key of constants.FIELD_VAR_LIST"""
    plt = args.plt
    if var == 's':
        fld = stgdat.calc_stream()
    else:
        fld = stgdat.fields[var]

    # adding a row at the end to have continuous field
    if stgdat.geom == 'annulus':
        if stgdat.par_type == 'vp':
            if var != 's':
                fld = fld[:, :, 0]
        else:
            newline = fld[:, 0, 0]
            fld = np.vstack([fld[:, :, 0].T, newline]).T
        ph_coord = np.append(
            stgdat.ph_coord, stgdat.ph_coord[1] - stgdat.ph_coord[0])

    xmesh, ymesh = np.meshgrid(
        np.array(ph_coord), np.array(stgdat.r_coord) + stgdat.rcmb)

    fig, axis = plt.subplots(ncols=1, subplot_kw={'projection': 'polar'})
    if stgdat.geom == 'annulus':
        if var == 'n':
            surf = axis.pcolormesh(xmesh, ymesh, fld,
                                   norm=args.mpl.colors.LogNorm(),
                                   cmap='jet_r',
                                   rasterized=not args.pdf,
                                   shading='gouraud')
        elif var == 'd':
            surf = axis.pcolormesh(xmesh, ymesh, fld, cmap='bwr_r',
                                   vmin=0.96, vmax=1.04,
                                   rasterized=not args.pdf,
                                   shading='gouraud')
        else:
            surf = axis.pcolormesh(xmesh, ymesh, fld, cmap='jet',
                                   rasterized=not args.pdf,
                                   shading='gouraud')
        cbar = plt.colorbar(surf, shrink=args.shrinkcb)
        cbar.set_label(constants.FIELD_VAR_LIST[var].name)
        plt.axis([stgdat.rcmb, np.amax(xmesh), 0, np.amax(ymesh)])
        plt.axis('off')

    return fig, axis


def plot_stream(args, fig, axis, x_1, x_2, v_1, v_2):
    """use of streamplot to plot stream lines

    only works in cartesian with regular grids
    """
    v_tot = np.sqrt(v_1**2 + v_2**2)
    lwd = 2*v_tot/v_tot.max()
    axis.streamplot(x_1, x_2, v_1, v_2, density=0.8, color='k', linewidth=lwd)


def field_cmd(args):
    """extract and plot field data"""
    for timestep in range(*args.timestep):
        for var, meta in constants.FIELD_VAR_LIST.items():
            if misc.get_arg(args, meta.arg):
                # will read vp many times!
                stgdat = BinData(args, var, timestep)
                fig, axis = plot_scalar(args, stgdat, var)
                args.plt.figure(fig.number)
                args.plt.tight_layout()
                args.plt.savefig(
                    misc.out_name(args, var).format(stgdat.step) + '.pdf',
                    format='PDF')
                args.plt.close(fig)
