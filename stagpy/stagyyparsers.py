"""Parsers of StagYY output files.

Note:
    These functions are low level utilities. You should not use these unless
    you know what you are doing. To access StagYY output data, use an instance
    of :class:`~stagpy.stagyydata.StagyyData`.
"""
from functools import partial
from itertools import product, repeat
from operator import itemgetter
from xml.etree import ElementTree as xmlet
import re
import struct
import numpy as np
import pandas as pd
import h5py
from .error import ParsingError


def time_series(timefile, colnames):
    """Read temporal series text file.

    If :data:`colnames` is too long, it will be truncated. If it is too short,
    additional numeric column names from 0 to N-1 will be attributed to the N
    extra columns present in :data:`timefile`.

    Args:
        timefile (:class:`pathlib.Path`): path of the time.dat file.
        colnames (list of names): names of the variables expected in
            :data:`timefile`.

    Returns:
        :class:`pandas.DataFrame`:
            Time series, with the variables in columns and the time steps in
            rows.
    """
    if not timefile.is_file():
        return None
    data = pd.read_csv(timefile, delim_whitespace=True, dtype=str,
                       header=None, skiprows=1, index_col=0,
                       engine='c', memory_map=True,
                       error_bad_lines=False, warn_bad_lines=False)
    data = data.apply(pd.to_numeric, raw=True, errors='coerce')

    # detect useless lines produced when run is restarted
    rows_to_del = []
    irow = len(data) - 1
    while irow > 0:
        iprev = irow - 1
        while iprev >= 0 and data.index[irow] <= data.index[iprev]:
            rows_to_del.append(iprev)
            iprev -= 1
        irow = iprev
    if rows_to_del:
        rows_to_keep = set(range(len(data))) - set(rows_to_del)
        data = data.take(list(rows_to_keep), convert=False)

    ncols = data.shape[1]
    data.columns = colnames[:ncols] + list(range(0, ncols - len(colnames)))

    return data


def _extract_rsnap_isteps(rproffile):
    """Extract istep and compute list of rows to delete"""
    step_regex = re.compile(r'^\*+step:\s*(\d+) ; time =\s*(\S+)')
    isteps = []  # list of (istep, time, nz)
    rows_to_del = set()
    line = ' '
    with rproffile.open() as stream:
        while line[0] != '*':
            line = stream.readline()
        match = step_regex.match(line)
        istep = int(match.group(1))
        time = float(match.group(2))
        nlines = 0
        iline = 0
        for line in stream:
            if line[0] == '*':
                isteps.append((istep, time, nlines))
                match = step_regex.match(line)
                istep = int(match.group(1))
                time = float(match.group(2))
                nlines = 0
                # remove useless lines produced when run is restarted
                nrows_to_del = 0
                while isteps and istep <= isteps[-1][0]:
                    nrows_to_del += isteps.pop()[-1]
                rows_to_del = rows_to_del.union(
                    range(iline - nrows_to_del, iline))
            else:
                nlines += 1
                iline += 1
        isteps.append((istep, time, nlines))
    return isteps, rows_to_del


def rprof(rproffile, colnames):
    """Extract radial profiles data

    If :data:`colnames` is too long, it will be truncated. If it is too short,
    additional numeric column names from 0 to N-1 will be attributed to the N
    extra columns present in :data:`timefile`.

    Args:
        rproffile (:class:`pathlib.Path`): path of the rprof.dat file.
        colnames (list of names): names of the variables expected in
            :data:`rproffile`.

    Returns:
        tuple of :class:`pandas.DataFrame`: (profs, times)
            :data:`profs` are the radial profiles, with the variables in
            columns and rows double-indexed with the time step and the radial
            index of numerical cells.

            :data:`times` is the dimensionless time indexed by time steps.
    """
    if not rproffile.is_file():
        return None, None
    data = pd.read_csv(rproffile, delim_whitespace=True, dtype=str,
                       header=None, comment='*',
                       engine='c', memory_map=True,
                       error_bad_lines=False, warn_bad_lines=False)
    data = data.apply(pd.to_numeric, raw=True, errors='coerce')

    isteps, rows_to_del = _extract_rsnap_isteps(rproffile)
    if rows_to_del:
        rows_to_keep = set(range(len(data))) - rows_to_del
        data = data.take(list(rows_to_keep), convert=False)

    id_arr = [[], []]
    for istep, _, n_z in isteps:
        id_arr[0].extend(repeat(istep, n_z))
        id_arr[1].extend(range(n_z))

    data.index = id_arr

    ncols = data.shape[1]
    data.columns = colnames[:ncols] + list(range(0, ncols - len(colnames)))

    df_times = pd.DataFrame(list(map(itemgetter(1), isteps)),
                            index=map(itemgetter(0), isteps))
    return data, df_times


def _readbin(fid, fmt='i', nwords=1, file64=False):
    """Read n words of 4 or 8 bytes with fmt format.

    fmt: 'i' or 'f' (integer or float)
    4 or 8 bytes: depends on header

    Return an array of elements if more than one element.

    Default: read 1 word formatted as an integer.
    """
    if file64:
        nbytes = 8
        fmt = fmt.replace('i', 'q')
        fmt = fmt.replace('f', 'd')
    else:
        nbytes = 4
    elts = np.array(struct.unpack(fmt * nwords, fid.read(nwords * nbytes)))
    if len(elts) == 1:
        elts = elts[0]
    return elts


def fields(fieldfile, only_header=False, only_istep=False):
    """Extract fields data.

    Args:
        fieldfile (:class:`pathlib.Path`): path of the binary field file.
        only_header (bool): when True (and :data:`only_istep` is False), only
            :data:`header` is returned.
        only_istep (bool): when True, only :data:`istep` is returned.

    Returns:
        depends on flags.: :obj:`int`: istep
            If :data:`only_istep` is True, this function returns the time step
            at which the binary file was written.
        :obj:`dict`: header
            Else, if :data:`only_header` is True, this function returns a dict
            containing the header informations of the binary file.
        :class:`numpy.array`: fields
            Else, this function returns the tuple :data:`(header, fields)`.
            :data:`fields` is an array of scalar fields indexed by variable,
            x-direction, y-direction, z-direction, block.
    """
    # something to skip header?
    if not fieldfile.is_file():
        return None
    header = {}
    with fieldfile.open('rb') as fid:
        readbin = partial(_readbin, fid)
        magic = readbin()
        if magic > 8000:  # 64 bits
            magic -= 8000
            readbin()  # need to read 4 more bytes
            readbin = partial(readbin, file64=True)

        # check nb components
        nval = 1
        if magic > 400:
            nval = 4
        elif magic > 300:
            nval = 3

        magic %= 100

        # extra ghost point in horizontal direction
        header['xyp'] = int(magic >= 9 and nval == 4)

        # total number of values in relevant space basis
        # (e1, e2, e3) = (theta, phi, radius) in spherical geometry
        #              = (x, y, z)            in cartesian geometry
        header['nts'] = readbin(nwords=3)

        # number of blocks, 2 for yinyang or cubed sphere
        header['ntb'] = readbin() if magic >= 7 else 1

        # aspect ratio
        header['aspect'] = readbin('f', 2)

        # number of parallel subdomains
        header['ncs'] = readbin(nwords=3)  # (e1, e2, e3) space
        header['ncb'] = readbin() if magic >= 8 else 1  # blocks

        # r - coordinates
        # rgeom[0:self.nrtot+1, 0] are edge radial position
        # rgeom[0:self.nrtot, 1] are cell-center radial position
        if magic >= 2:
            header['rgeom'] = readbin('f', header['nts'][2] * 2 + 1)
        else:
            header['rgeom'] = np.array(range(0, header['nts'][2] * 2 + 1))\
                * 0.5 / header['nts'][2]
        header['rgeom'].resize((header['nts'][2] + 1, 2))

        header['rcmb'] = readbin('f') if magic >= 7 else None

        header['ti_step'] = readbin() if magic >= 3 else 0
        if only_istep:
            return header['ti_step']
        header['ti_ad'] = readbin('f') if magic >= 3 else 0
        header['erupta_total'] = readbin('f') if magic >= 5 else 0
        header['bot_temp'] = readbin('f') if magic >= 6 else 1

        if magic >= 4:
            header['e1_coord'] = readbin('f', header['nts'][0])
            header['e2_coord'] = readbin('f', header['nts'][1])
            header['e3_coord'] = readbin('f', header['nts'][2])
        else:
            # could construct them from other info
            raise ParsingError(fieldfile,
                               'magic >= 4 expected to get grid geometry')

        if only_header:
            return header

        # READ FIELDS
        # number of points in (e1, e2, e3) directions PER CPU
        npc = header['nts'] // header['ncs']
        # number of blocks per cpu
        nbk = header['ntb'] // header['ncb']
        # number of values per 'read' block
        npi = (npc[0] + header['xyp']) * (npc[1] + header['xyp']) * npc[2] * \
            nbk * nval

        header['scalefac'] = readbin('f') if nval > 1 else 1

        flds = np.zeros((nval,
                         header['nts'][0] + header['xyp'],
                         header['nts'][1] + header['xyp'],
                         header['nts'][2],
                         header['ntb']))

        # loop over parallel subdomains
        for icpu in product(range(header['ncb']),
                            range(header['ncs'][2]),
                            range(header['ncs'][1]),
                            range(header['ncs'][0])):
            # read the data for one CPU
            data_cpu = readbin('f', npi) * header['scalefac']

            # icpu is (icpu block, icpu z, icpu y, icpu x)
            # data from file is transposed to obtained a field
            # array indexed with (x, y, z, block), as in StagYY
            flds[:,
                 icpu[3] * npc[0]:(icpu[3] + 1) * npc[0] + header['xyp'],  # x
                 icpu[2] * npc[1]:(icpu[2] + 1) * npc[1] + header['xyp'],  # y
                 icpu[1] * npc[2]:(icpu[1] + 1) * npc[2],  # z
                 icpu[0] * nbk:(icpu[0] + 1) * nbk  # block
                 ] = np.transpose(data_cpu.reshape(
                     (nbk, npc[2], npc[1] + header['xyp'],
                      npc[0] + header['xyp'], nval)))
    return header, flds


def _read_group_h5(filename, groupname):
    """Return group content.

    Args:
        filename (:class:`pathlib.Path`): path of hdf5 file.
        groupname (str): name of group to read.
    Returns:
        :class:`numpy.array`: content of group.
    """
    with h5py.File(filename, 'r') as h5f:
        data = h5f[groupname].value
    return data  # need to be reshaped


def _make_3d(field, twod):
    """Add a dimension to field if necessary.

    Args:
        field (numpy.array): the field that need to be 3d.
        twod (str): 'XZ', 'YZ' or None depending on what is relevant.
    Returns:
        numpy.array: reshaped field.
    """
    shp = list(field.shape)
    if twod and 'X' in twod:
        shp.insert(1, 1)
    elif twod:
        shp.insert(0, 1)
    return field.reshape(shp)


def _ncores(meshes, twod):
    """Compute number of nodes in each direction."""
    nnpb = len(meshes)  # number of nodes per block
    nns = [1, 1, 1]  # number of nodes in x, y, z directions
    if twod is None or 'X' in twod:
        while (nnpb > 1 and
               meshes[nns[0]]['X'][0, 0, 0] ==
               meshes[nns[0] - 1]['X'][-1, 0, 0]):
            nns[0] += 1
            nnpb -= 1
    if twod is None or 'Y' in twod:
        while (nnpb > 1 and
               meshes[nns[1]]['Y'][0, 0, 0] ==
               meshes[nns[1] - 1]['Y'][0, -1, 0]):
            nns[1] += 1
            nnpb -= 1
    while (nnpb > 1 and
           meshes[nns[2]]['Z'][0, 0, 0] ==
           meshes[nns[2] - 1]['Z'][0, 0, -1]):
        nns[2] += 1
        nnpb -= 1
    return np.array(nns)


def _read_coord_h5(files, shapes, header, twod):
    """Read all coord hdf5 files of a snapshot.

    Args:
        files (list of pathlib.Path): list of NodeCoordinates files of
            a snapshot.
        shapes (list of (int,int)): shape of mesh grids.
        header (dict): geometry info.
        twod (str): 'XZ', 'YZ' or None depending on what is relevant.
    """
    meshes = []
    for h5file, shape in zip(files, shapes):
        meshes.append({})
        with h5py.File(h5file, 'r') as h5f:
            for coord, mesh in h5f.items():
                # for some reason, the array is transposed!
                meshes[-1][coord] = mesh.value.reshape(shape).T
                meshes[-1][coord] = _make_3d(meshes[-1][coord], twod)

    header['ncs'] = _ncores(meshes, twod)
    header['e1_coord'] = meshes[0]['X'][:, 0, 0]
    header['e2_coord'] = meshes[0]['Y'][0, :, 0]
    header['e3_coord'] = meshes[0]['Z'][0, 0, :]
    ncores = header['ncs'][0]
    icore = 0
    while ncores > 1:
        icore += 1
        ncores -= 1
        header['e1_coord'] = np.append(header['e1_coord'][:-1],
                                       meshes[icore]['X'][:, 0, 0])
    ncores = header['ncs'][1]
    while ncores > 1:
        icore += 1
        ncores -= 1
        header['e2_coord'] = np.append(header['e2_coord'][:-1],
                                       meshes[icore]['Y'][0, :, 0])
    ncores = header['ncs'][2]
    while ncores > 1:
        icore += 1
        ncores -= 1
        header['e3_coord'] = np.append(header['e3_coord'][:-1],
                                       meshes[icore]['Z'][0, 0, :])
    if twod is None or 'X' in twod:
        header['e1_coord'] = header['e1_coord'][:-1]
    if twod is None or 'Y' in twod:
        header['e2_coord'] = header['e2_coord'][:-1]
    header['e3_coord'] = header['e3_coord'][:-1]
    header['nts'] = (len(header['e1_coord']), len(header['e2_coord']),
                     len(header['e3_coord']))


def read_geom_h5(xdmf_file, snapshot):
    """Extract geometry information from hdf5 files.

    Args:
        xdmf_file (:class:`pathlib.Path`): path of the xdmf file.
        field (str): name of field to extract.
        snapshot (int): snapshot number.
    Returns:
        (dict, root): geometry information and root of xdmf document.
    """
    header = {}
    xdmf_root = xmlet.parse(xdmf_file).getroot()

    # Domain, Temporal Collection, Snapshot
    # should check that this is indeed the required snapshot
    elt_snap = xdmf_root[0][0][snapshot]
    header['ti_ad'] = float(elt_snap.find('Time').get('Value'))
    header['ntb'] = 1
    coord_h5 = []  # all the coordinate files
    coord_shape = []  # shape of meshes
    twod = None
    for elt_subdomain in elt_snap.findall('Grid'):
        if elt_subdomain.get('Name').startswith('meshYang'):
            header['ntb'] = 2
            break  # iterate only through meshYin
        elt_geom = elt_subdomain.find('Geometry')
        if elt_geom.get('Type') == 'X_Y' and twod is None:
            twod = ''
            for data_item in elt_geom.findall('DataItem'):
                coord = data_item.text.strip()[-1]
                if coord in 'XYZ':
                    twod += coord
        data_item = elt_geom.find('DataItem')
        coord_shape.append(
            tuple(map(int, data_item.get('Dimensions').split())))
        coord_h5.append(
            xdmf_file.parent / data_item.text.strip().split(':/', 1)[0])
    _read_coord_h5(coord_h5, coord_shape, header, twod)
    return header, xdmf_root
